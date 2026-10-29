from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from app.domain.cleaner_capabilities import (
    capability_allowed_suffixes,
    validate_capability_contract,
)
from app.domain.cleaner_registry import CleanerRelease
from app.infrastructure.child_process_environment import isolated_child_environment

ProcessRunner = Callable[..., subprocess.CompletedProcess[str]]
INPUT_REQUIRED_PREFIX = "TMS_INPUT_REQUIRED_JSON="
INPUT_REQUIRED_EXIT_CODE = 42


class CleanerInputRequired(RuntimeError):
    """A released Cleaner proved that user input is the only missing identity."""

    def __init__(self, *, field_code: str, files: tuple[str, ...], message: str) -> None:
        super().__init__(message)
        self.field_code = field_code
        self.files = files
        self.message = message


@dataclass(frozen=True, slots=True)
class CleanerArtifact:
    role: str
    path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ExistingCleanerRunResult:
    test_stage: str
    factory: str
    output_root: str
    artifacts: tuple[CleanerArtifact, ...]
    stdout_tail: str

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["artifacts"] = [asdict(item) for item in self.artifacts]
        return data


class ExistingCleanerRunner:
    """Run proven CP/FT release packages in isolated child processes."""

    def __init__(
        self,
        *,
        cp_release_dir: str | Path | None = None,
        ft_release_dir: str | Path | None = None,
        python_executable: str | Path | None = None,
        process_runner: ProcessRunner = subprocess.run,
    ) -> None:
        self.cp_release_dir = Path(
            cp_release_dir
            or os.getenv(
                "TMS_CP_CLEANER_RELEASE", r"F:\cp_data_ansys\packaging\release"
            )
        )
        self.ft_release_dir = Path(
            ft_release_dir
            or os.getenv(
                "TMS_FT_CLEANER_RELEASE",
                r"F:\data_IGBT_multiple\packaging\release",
            )
        )
        self.python_executable = Path(
            python_executable
            or os.getenv("TMS_CLEANER_PYTHON", r"D:\ProgramData\anaconda3\python.exe")
        )
        self._process_runner = process_runner

    def run(
        self,
        *,
        test_stage: str,
        factory: str,
        inputs: Sequence[str | Path],
        output_root: str | Path,
    ) -> ExistingCleanerRunResult:
        stage = test_stage.strip().upper()
        factory_code = factory.strip().lower()
        normalized_inputs = tuple(Path(item).resolve() for item in inputs)
        if not normalized_inputs:
            raise ValueError("at least one input path is required")
        missing = [str(item) for item in normalized_inputs if not item.exists()]
        if missing:
            raise FileNotFoundError(f"cleaner input does not exist: {missing[0]}")

        target = Path(output_root).resolve()
        target.mkdir(parents=True, exist_ok=True)
        cp_scripts = {
            "huahong": _CP_HUAHONG_SCRIPT,
            "hh": _CP_HUAHONG_SCRIPT,
            "华虹": _CP_HUAHONG_SCRIPT,
            "jetech": _CP_JETECH_SCRIPT,
            "jt": _CP_JETECH_SCRIPT,
            "佳泰": _CP_JETECH_SCRIPT,
            "捷特": _CP_JETECH_SCRIPT,
            "lion": _CP_LION_SCRIPT,
            "立昂微": _CP_LION_SCRIPT,
            "guoyu": _CP_GUOYU_SCRIPT,
            "国宇": _CP_GUOYU_SCRIPT,
            "国宇frd": _CP_GUOYU_SCRIPT,
        }
        if stage == "CP" and factory_code in cp_scripts:
            release_dir = self.cp_release_dir
            package = release_dir / "app.pyz"
            script = cp_scripts[factory_code]
        elif stage == "FT" and factory_code in {"riyuexin", "日月新"}:
            release_dir = self.ft_release_dir
            package = release_dir / "ft_data_cleaner.pyz"
            script = _FT_RIYUEXIN_DC_SCRIPT
        elif stage == "FT" and factory_code in {"riyueguang", "ase", "日月光"}:
            release_dir = self.ft_release_dir
            package = release_dir / "ft_data_cleaner.pyz"
            script = _FT_RIYUEGUANG_DC_SCRIPT
        elif stage == "FT" and factory_code in {"dianji", "电基"}:
            release_dir = self.ft_release_dir
            package = release_dir / "ft_data_cleaner.pyz"
            script = _FT_DIANJI_POWERTECH_SCRIPT
        else:
            raise ValueError(f"unsupported existing cleaner adapter: {stage}/{factory}")

        return self._execute_registered_inputs(
            stage=stage,
            factory_code=factory_code,
            normalized_inputs=normalized_inputs,
            target=target,
            runtime=self.python_executable,
            package=package,
            release_dir=release_dir,
            script=script,
            timeout_seconds=3600,
            max_output_bytes=10 * 1024 * 1024 * 1024,
            execution_config_json=json.dumps(
                {"outlier_method": "iqr", "convert_units": True}
            ),
            lot_overrides=None,
            ft_allowed_suffixes=(
                frozenset({".xls", ".xlsx"})
                if stage == "FT" and factory_code in {"dianji", "电基", "riyuexin", "日月新"}
                else frozenset({".xlsx"})
            ),
        )

    def run_release(
        self,
        *,
        release: CleanerRelease,
        inputs: Sequence[str | Path],
        output_root: str | Path,
        lot_overrides: dict[str, str] | None = None,
        expected_sha256: Sequence[str | None] | None = None,
        identity_overrides: dict[str, dict[str, str]] | None = None,
    ) -> ExistingCleanerRunResult:
        normalized_inputs = tuple(Path(item).resolve() for item in inputs)
        if not normalized_inputs:
            raise ValueError("at least one input path is required")
        missing = [str(item) for item in normalized_inputs if not item.exists()]
        if missing:
            raise FileNotFoundError(f"cleaner input does not exist: {missing[0]}")
        package = Path(release.artifact_uri).resolve()
        runtime = Path(release.runtime_uri).resolve()
        target = Path(output_root).resolve()
        target.mkdir(parents=True, exist_ok=True)
        validate_capability_contract(
            adapter_code=release.adapter_code,
            test_stage=release.test_stage,
            factory_code=release.factory_code,
            cleaner_code=release.cleaner_code,
            input_contract_version=release.input_contract_version,
            output_contract_version=release.output_contract_version,
            execution_config_json=release.execution_config_json,
        )
        scripts = {
            "HUAHONG_CP_PYZ": _CP_HUAHONG_SCRIPT,
            "JETECH_CP_PYZ": _CP_JETECH_SCRIPT,
            "LION_CP_PYZ": _CP_LION_SCRIPT,
            "GUOYU_CP_PYZ": _CP_GUOYU_SCRIPT,
            "RIYUEXIN_FT_PYZ": _FT_RIYUEXIN_DC_SCRIPT,
            "RIYUEGUANG_FT_PYZ": _FT_RIYUEGUANG_DC_SCRIPT,
            "DIANJI_FT_PYZ": _FT_DIANJI_POWERTECH_SCRIPT,
            "JIJIA_FT_PYZ": _registered_ft_bridge_script(),
            "JIEMIN_FT_PYZ": _registered_ft_bridge_script(),
        }
        try:
            script = scripts[release.adapter_code]
        except KeyError as exc:
            raise ValueError(
                f"unsupported released Cleaner adapter: {release.adapter_code}"
            ) from exc
        if package.is_file() and _file_sha256(package) != release.code_checksum.lower():
            raise RuntimeError(
                f"Cleaner package checksum differs from released contract: {package}"
            )
        return self._execute_registered_inputs(
            stage=release.test_stage,
            factory_code=release.factory_code.lower(),
            normalized_inputs=normalized_inputs,
            target=target,
            runtime=runtime,
            package=package,
            release_dir=package.parent,
            script=script,
            timeout_seconds=release.timeout_seconds,
            max_output_bytes=release.max_output_bytes,
            execution_config_json=release.execution_config_json,
            lot_overrides=lot_overrides,
            expected_sha256=expected_sha256,
            require_registered_hash=release.test_stage == "FT",
            ft_allowed_suffixes=_ft_allowed_suffixes(release.adapter_code),
            identity_overrides=identity_overrides,
        )

    def _execute_registered_inputs(
        self,
        *,
        stage: str,
        factory_code: str,
        normalized_inputs: tuple[Path, ...],
        target: Path,
        runtime: Path,
        package: Path,
        release_dir: Path,
        script: str,
        timeout_seconds: int,
        max_output_bytes: int,
        execution_config_json: str | None,
        lot_overrides: dict[str, str] | None,
        expected_sha256: Sequence[str | None] | None = None,
        require_registered_hash: bool = False,
        ft_allowed_suffixes: frozenset[str] = frozenset({".xlsx"}),
        identity_overrides: dict[str, dict[str, str]] | None = None,
    ) -> ExistingCleanerRunResult:
        validated_hashes = _verify_expected_sha256(
            normalized_inputs,
            expected_sha256,
            required=require_registered_hash,
        )
        if stage != "FT":
            return self._execute(
                stage=stage,
                factory_code=factory_code,
                normalized_inputs=normalized_inputs,
                target=target,
                runtime=runtime,
                package=package,
                release_dir=release_dir,
                script=script,
                timeout_seconds=timeout_seconds,
                max_output_bytes=max_output_bytes,
                execution_config_json=execution_config_json,
                lot_overrides=lot_overrides,
            )

        with tempfile.TemporaryDirectory(prefix="tms_ft_registered_") as temporary:
            isolated = Path(temporary) / "inputs"
            isolated.mkdir()
            expanded: list[Path] = []
            from app.infrastructure.quick_pat_runner import _extract_ft_archive
            remaining = max(max_output_bytes * 4, 1024 ** 3)
            for index, source in enumerate(normalized_inputs):
                if source.is_file() and source.suffix.lower() in {".zip", ".7z", ".rar"}:
                    unpacked = _extract_ft_archive(source, Path(temporary) / f"archive-{index}", allowed_suffixes=tuple(ft_allowed_suffixes), max_total_bytes=remaining)
                    remaining -= sum(item.stat().st_size for item in unpacked)
                    if len(expanded) + len(unpacked) > 10000:
                        raise ValueError("单次上传解压文件超过一万个，请分批处理")
                    for item in unpacked:
                        validated_hashes[item] = _file_sha256(item)
                    expanded.extend(unpacked)
                else:
                    expanded.append(source)
            registered_files = _registered_ft_files(tuple(expanded), allowed_suffixes=ft_allowed_suffixes)
            seen_names: set[str] = set()
            for source in registered_files:
                key = source.name.casefold()
                if key in seen_names:
                    raise ValueError(
                        f"registered FT files have a duplicate filename: {source.name}"
                    )
                seen_names.add(key)
                copied = isolated / source.name
                shutil.copy2(source, copied)
                expected = validated_hashes[source]
                if expected is not None and _file_sha256(copied) != expected:
                    raise RuntimeError(
                        f"isolated FT input checksum differs from registration: {source}"
                    )
            normalized_overrides = _normalize_lot_overrides(
                lot_overrides or {}, seen_names
            )
            if identity_overrides and (factory_code != "dianji" or any(name.casefold() not in seen_names for name in identity_overrides)):
                raise ValueError("Explicit identities must reference registered Dianji input files")
            return self._execute(
                stage=stage,
                factory_code=factory_code,
                normalized_inputs=(isolated,),
                target=target,
                runtime=runtime,
                package=package,
                release_dir=release_dir,
                script=script,
                timeout_seconds=timeout_seconds,
                max_output_bytes=max_output_bytes,
                execution_config_json=execution_config_json,
                lot_overrides=normalized_overrides,
                identity_overrides=identity_overrides,
            )

    def _execute(
        self,
        *,
        stage: str,
        factory_code: str,
        normalized_inputs: tuple[Path, ...],
        target: Path,
        runtime: Path,
        package: Path,
        release_dir: Path,
        script: str,
        timeout_seconds: int,
        max_output_bytes: int,
        execution_config_json: str | None,
        lot_overrides: dict[str, str] | None,
        identity_overrides: dict[str, dict[str, str]] | None = None,
    ) -> ExistingCleanerRunResult:
        for required in (runtime, package):
            if not required.is_file():
                raise FileNotFoundError(f"cleaner runtime is unavailable: {required}")

        env = isolated_child_environment(
            {
                "TMS_EXISTING_CLEANER_PACKAGE": str(package),
                "TMS_EXISTING_CLEANER_INPUTS": json.dumps(
                    [str(item) for item in normalized_inputs], ensure_ascii=False
                ),
                "TMS_EXISTING_CLEANER_OUTPUT": str(target),
                "TMS_CLEANER_IDENTITY_MODULES": str(Path(__file__).parents[1] / "domain"),
                "TMS_CLEANER_EXECUTION_CONFIG": execution_config_json or "{}",
                "TMS_LOT_OVERRIDES_JSON": json.dumps(
                    lot_overrides or {}, ensure_ascii=False, sort_keys=True
                ),
                "TMS_SOURCE_IDENTITIES_JSON": json.dumps(identity_overrides or {}, ensure_ascii=False),
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUTF8": "1",
            }
        )
        if stage == "CP":
            # Desktop Cleaners default to D:\CPData. Server tasks own their
            # writable paths and must work on hosts without that drive.
            runtime_root = target / ".cp-runtime"
            env.update(CP_DATA_ROOT=str(runtime_root),
                       CP_LOG_DIR=str(runtime_root / "logs"),
                       CP_CONFIG_DIR=str(runtime_root / "config"))
        try:
            completed = self._process_runner(
                [str(runtime), "-c", script],
                cwd=str(release_dir),
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Cleaner timed out after {timeout_seconds}s ({stage}/{factory_code})"
            ) from exc
        input_required = _input_required_from_process(completed)
        if input_required is not None:
            if completed.returncode != INPUT_REQUIRED_EXIT_CODE:
                raise RuntimeError(
                    "Cleaner emitted an input-required marker with invalid exit code "
                    f"{completed.returncode}; expected {INPUT_REQUIRED_EXIT_CODE}"
                )
            raise input_required
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "unknown cleaner error")[
                -4000:
            ]
            raise RuntimeError(
                f"existing cleaner failed ({stage}/{factory_code}): {detail}"
            )

        artifacts = _discover_artifacts(stage, target)
        if not artifacts:
            raise RuntimeError(
                f"existing cleaner returned success without output artifacts: {target}"
            )
        _validate_artifact_contract(stage, artifacts)
        output_bytes = sum(
            path.stat().st_size for path in target.rglob("*") if path.is_file()
        )
        if output_bytes > max_output_bytes:
            raise RuntimeError(
                f"Cleaner output exceeds released limit: {output_bytes}>{max_output_bytes}"
            )
        return ExistingCleanerRunResult(
            test_stage=stage,
            factory=factory_code,
            output_root=str(target),
            artifacts=artifacts,
            stdout_tail=(completed.stdout or "")[-4000:],
        )


def _registered_ft_bridge_script() -> str:
    return Path(__file__).with_name("ft_factory_bridge_script.py").read_text(encoding="utf-8")


def _ft_allowed_suffixes(adapter_code: str) -> frozenset[str]:
    capability_suffixes = capability_allowed_suffixes(adapter_code)
    if capability_suffixes is not None:
        return capability_suffixes
    return frozenset({".xlsx"})


def _registered_ft_files(
    inputs: tuple[Path, ...], *, allowed_suffixes: frozenset[str]
) -> tuple[Path, ...]:
    if not all(
        path.is_file()
        and path.suffix.lower() in allowed_suffixes
        and not path.name.startswith("~$")
        for path in inputs
    ):
        expected = "/".join(sorted(allowed_suffixes))
        raise ValueError(
            f"FT adapter requires exact registered files with suffixes: {expected}"
        )
    files = inputs
    if not files:
        raise ValueError("FT DC adapter received no registered XLSX files")
    return files


def _verify_expected_sha256(
    inputs: tuple[Path, ...],
    expected_sha256: Sequence[str | None] | None,
    *,
    required: bool,
) -> dict[Path, str | None]:
    if expected_sha256 is None:
        if required:
            raise RuntimeError("registered FT input SHA256 values are required")
        return {path: None for path in inputs}
    expected_values = tuple(expected_sha256)
    if len(expected_values) != len(inputs):
        raise ValueError("registered input SHA256 count does not match input files")
    validated: dict[Path, str | None] = {}
    for path, raw_expected in zip(inputs, expected_values, strict=True):
        expected = str(raw_expected or "").strip().lower()
        if len(expected) != 64 or any(
            character not in "0123456789abcdef" for character in expected
        ):
            raise RuntimeError(f"registered input SHA256 is unavailable or invalid: {path}")
        if not path.is_file():
            raise RuntimeError(f"registered input is not a file: {path}")
        if _file_sha256(path) != expected:
            raise RuntimeError(
                f"registered input checksum differs from current bytes: {path}"
            )
        validated[path] = expected
    return validated


def _normalize_lot_overrides(
    overrides: dict[str, str], registered_names: set[str]
) -> dict[str, str]:
    normalized: dict[str, str] = {}
    normalized_by_name: dict[str, str] = {}
    for raw_name, raw_lot in overrides.items():
        name = Path(str(raw_name)).name
        name_key = name.casefold()
        lot = str(raw_lot).strip()
        if not name or name_key not in registered_names:
            raise ValueError(f"Lot override does not match a registered FT file: {raw_name}")
        if not lot or len(lot) > 128:
            raise ValueError(f"Lot override is invalid for registered FT file: {name}")
        previous = normalized_by_name.get(name_key)
        if previous is not None and previous != lot:
            raise ValueError(f"conflicting Lot overrides for registered FT file: {name}")
        normalized_by_name[name_key] = lot
        normalized[name] = lot
    return normalized


def _input_required_from_process(
    completed: subprocess.CompletedProcess[str],
) -> CleanerInputRequired | None:
    marked_lines = [
        line[len(INPUT_REQUIRED_PREFIX) :]
        for output in (completed.stderr or "", completed.stdout or "")
        for line in output.splitlines()
        if line.startswith(INPUT_REQUIRED_PREFIX)
    ]
    if not marked_lines:
        return None
    if len(marked_lines) != 1:
        raise RuntimeError("Cleaner emitted multiple input-required markers")
    try:
        payload = json.loads(marked_lines[0])
    except json.JSONDecodeError as exc:
        raise RuntimeError("Cleaner input-required marker is invalid JSON") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "field_code",
        "files",
        "message",
    }:
        raise RuntimeError("Cleaner input-required marker has an invalid schema")
    field_code = str(payload["field_code"] or "").strip().upper()
    message = str(payload["message"] or "").strip()
    raw_files = payload["files"]
    if (
        field_code != "LOT_ID"
        or not message
        or not isinstance(raw_files, list)
        or not raw_files
    ):
        raise RuntimeError("Cleaner input-required marker has invalid values")
    if any(not isinstance(item, dict) or set(item) != {"original_file_name"} for item in raw_files):
        raise RuntimeError("Cleaner input-required files have an invalid schema")
    files = tuple(str(item["original_file_name"]).strip() for item in raw_files)
    if any(not item or Path(item).name != item for item in files):
        raise RuntimeError("Cleaner input-required files must be plain original filenames")
    if len({item.casefold() for item in files}) != len(files):
        raise RuntimeError("Cleaner input-required files are duplicated")
    return CleanerInputRequired(field_code=field_code, files=files, message=message)


def _discover_artifacts(stage: str, output_root: Path) -> tuple[CleanerArtifact, ...]:
    roles = {
        "CP": (
            ("cleaned", "*_cleaned_*.csv"),
            ("yield", "*_yield_*.csv"),
            ("spec", "*_spec_*.csv"),
        ),
        "FT": (
            ("cleaned", "*.xlsx"),
            ("scatter_data", "ft_scatter_data.csv.gz"),
            ("scatter_spec", "ft_scatter_spec.csv"),
            ("scatter_manifest", "ft_scatter_manifest.json"),
            ("source_trace", "source_trace.csv.gz"),
            ("source_manifest", "source_manifest.json"),
            ("cleaning_audit", "cleaning_audit.json"),
            ("row_identity", "row_identity.csv.gz"),
        ),
    }[stage]
    found: list[CleanerArtifact] = []
    for role, pattern in roles:
        for path in sorted(
            output_root.rglob(pattern), key=lambda item: str(item).casefold()
        ):
            found.append(
                CleanerArtifact(
                    role,
                    str(path.resolve()),
                    path.stat().st_size,
                    _file_sha256(path),
                )
            )
    return tuple(found)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_artifact_contract(
    stage: str, artifacts: tuple[CleanerArtifact, ...]
) -> None:
    required = {
        "CP": {"cleaned", "yield", "spec"},
        "FT": {"cleaned", "scatter_data", "scatter_spec", "scatter_manifest"},
    }[stage]
    actual = {item.role for item in artifacts}
    missing = sorted(required - actual)
    if missing:
        raise RuntimeError(
            f"Cleaner output contract is incomplete for {stage}: missing {missing}"
        )


_CP_HUAHONG_SCRIPT = """
import json, os, sys
from pathlib import Path
sys.path.insert(0, os.environ['TMS_EXISTING_CLEANER_PACKAGE'])
from cp_data_processor.processing.archive_input import prepare_archive_input
from clean_dcp_data import process_directory
from cp_data_processor.processing.hh_td_processor import process_hh_td
inputs = [Path(item) for item in json.loads(os.environ['TMS_EXISTING_CLEANER_INPUTS'])]
output = os.environ['TMS_EXISTING_CLEANER_OUTPUT']
config = json.loads(os.environ.get('TMS_CLEANER_EXECUTION_CONFIG', '{}'))

def run(directory, files):
    suffixes = {p.suffix.lower() for p in files}
    if suffixes == {'.xlsx'}:
        process_hh_td(files, output, progress=print)
    elif suffixes == {'.txt'}:
        if not process_directory(str(directory), output_dir=output,
                outlier_method=config.get('outlier_method', 'iqr'),
                convert_units=bool(config.get('convert_units', True))):
            raise SystemExit('华虹 CP cleaner returned no result')
    else:
        raise ValueError('华虹 DCP/TXT 与 TD/XLSX 必须分开上传，且不能含未知格式')
if len(inputs) == 1 and inputs[0].is_dir():
    files = [p for p in inputs[0].rglob('*') if p.is_file() and p.suffix.lower() in ('.txt', '.xlsx')]
    run(inputs[0], files)
elif all(p.is_file() and p.suffix.lower() == '.xlsx' for p in inputs):
    process_hh_td(inputs, output, progress=print)
elif all(p.is_file() and p.suffix.lower() == '.txt' for p in inputs):
    raise SystemExit('raw TXT files require a source directory or archive preserving Product/Lot identity')
else:
    with prepare_archive_input(inputs, allowed_suffixes=('.txt', '.xlsx'),
            archive_suffixes=('.zip', '.7z'), preserve_member_paths=True,
            source_label='华虹 DCP/TD', temporary_prefix='tms_cp_hh_') as prepared:
        run(prepared.directory, prepared.data_files)
"""


_CP_JETECH_SCRIPT = """
import json, os, sys
from pathlib import Path
sys.path.insert(0, os.environ['TMS_EXISTING_CLEANER_PACKAGE'])
from cp_data_processor.processing.archive_input import prepare_archive_input
from jt_data_processor.jt_main_processor import process_jt_files
inputs = [Path(item) for item in json.loads(os.environ['TMS_EXISTING_CLEANER_INPUTS'])]
output = os.environ['TMS_EXISTING_CLEANER_OUTPUT']
if all(path.is_file() and path.suffix.lower() in ('.xls', '.xlsx') for path in inputs):
    result = process_jt_files([str(path) for path in inputs], output_dir=output, pass_bin=1)
else:
    with prepare_archive_input(
        inputs,
        allowed_suffixes=('.xls', '.xlsx'),
        source_label='JT Excel',
        temporary_prefix='tms_cp_jt_',
    ) as prepared:
        result = process_jt_files(
            [str(path) for path in prepared.data_files], output_dir=output, pass_bin=1
        )
if not result:
    raise SystemExit('Jetech CP cleaner returned no result')
"""


_CP_LION_SCRIPT = """
import gc, json, os, shutil, sys, tempfile
from pathlib import Path
sys.path.insert(0, os.environ['TMS_EXISTING_CLEANER_PACKAGE'])
sys.path.insert(0, os.environ['TMS_CLEANER_IDENTITY_MODULES'])
from lion_identity import lion_path_identity
from cp_data_processor.processing.archive_input import prepare_archive_input
from lion_batch_processor import (
    create_batch_lot,
    generate_lion_run_csvs,
    process_lion_batch_files,
)
inputs = [Path(item) for item in json.loads(os.environ['TMS_EXISTING_CLEANER_INPUTS'])]
output = os.environ['TMS_EXISTING_CLEANER_OUTPUT']
def run(paths):
    # Legacy uploads were named sources.zip. Restore verified per-file lot
    # directories before the native V1 reader derives identity from parents.
    with tempfile.TemporaryDirectory(prefix='tms_lion_identity_') as temporary:
        groups, expected = {}, {}
        for path in paths:
            path = Path(path)
            identity = lion_path_identity(path)
            key = (identity['lot_id'].casefold(), identity['wafer_id'])
            if key in expected:
                raise ValueError('Lion duplicate source lot/wafer: ' + str(key))
            target = Path(temporary) / identity['lot_id'] / path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            expected[key] = identity
            groups.setdefault(identity['lot_id'], []).append(str(target))
        lots = []
        try:
            for lot_id, files in groups.items():
                individual = process_lion_batch_files(files)
                if set(individual) != set(files):
                    raise ValueError('Lion cleaner omitted source files')
                for source, lot in individual.items():
                    identity = lion_path_identity(source)
                    if lot.lot_id.casefold() != lot_id.casefold() or {
                        str(int(w.wafer_id)) for w in lot.wafers
                    } != {identity['wafer_id']}:
                        raise ValueError('Lion native identity conflicts with source: ' + Path(source).name)
                lots.append(create_batch_lot(individual))
            if not lots or not generate_lion_run_csvs(lots, output):
                raise SystemExit('Lion CP cleaner returned no result')
        finally:
            gc.collect()
if all(path.is_file() and path.suffix.lower() in ('.xls', '.xlsx') for path in inputs):
    run(inputs)
else:
    with prepare_archive_input(
        inputs,
        allowed_suffixes=('.xls', '.xlsx'),
        source_label='Lion Excel',
        archive_suffixes=('.zip', '.rar'),
        temporary_prefix='tms_cp_lion_',
        preserve_member_paths=True,
    ) as prepared:
        try:
            run(prepared.data_files)
        finally:
            # Release unreferenced workbook cycles before Windows removes the
            # extracted files. The released reader can leave these handles open.
            gc.collect()
"""


_CP_GUOYU_SCRIPT = """
import json, os, shutil, sys, tempfile
from pathlib import Path
sys.path.insert(0, os.environ['TMS_EXISTING_CLEANER_PACKAGE'])
from cp_data_processor.processing.archive_input import prepare_archive_input
from guoyu_batch_processor import process_guoyu_directory
inputs = [Path(item) for item in json.loads(os.environ['TMS_EXISTING_CLEANER_INPUTS'])]
output = os.environ['TMS_EXISTING_CLEANER_OUTPUT']
if all(path.is_file() and path.suffix.lower() in ('.xls', '.xlsx') for path in inputs):
    with tempfile.TemporaryDirectory(prefix='tms_cp_guoyu_files_') as temporary:
        product_directories = set()
        for path in inputs:
            lot_directory = path.parent
            if lot_directory.name.upper().startswith('EDS') or lot_directory.name.upper() in ('DATA', '数据'):
                lot_directory = lot_directory.parent
            product_directory = lot_directory.parent
            product_name = product_directory.name or 'SOURCE'
            lot_name = lot_directory.name or 'SOURCE'
            product_directories.add(product_name)
            directory = Path(temporary) / product_name / lot_name / 'EDS'
            directory.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, directory / path.name)
        if len(product_directories) != 1:
            raise ValueError('Guoyu FRD single-file inputs must belong to one product directory')
        result = process_guoyu_directory(
            str(Path(temporary) / next(iter(product_directories))), output
        )
else:
    with prepare_archive_input(
        inputs,
        allowed_suffixes=('.xls', '.xlsx'),
        source_label='Guoyu FRD Excel',
        preserve_member_paths=True,
        temporary_prefix='tms_cp_guoyu_',
    ) as prepared:
        result = process_guoyu_directory(str(prepared.directory), output)
if not result:
    raise SystemExit('Guoyu FRD CP cleaner returned no result')
"""


_FT_RIYUEXIN_DC_SCRIPT = """
import json, os, sys
sys.path.insert(0, os.environ['TMS_EXISTING_CLEANER_PACKAGE'])
from factories.tms_adapters.riyuexin_dc import RiyuexinTmsDCCleaner
from factories.tms_adapters.identity import LotOverrideRequired
inputs = json.loads(os.environ['TMS_EXISTING_CLEANER_INPUTS'])
lot_overrides = json.loads(os.environ.get('TMS_LOT_OVERRIDES_JSON', '{}'))
try:
    cleaner = RiyuexinTmsDCCleaner(
        input_dir=inputs[0],
        output_dir=os.environ['TMS_EXISTING_CLEANER_OUTPUT'],
        lot_overrides=lot_overrides,
    )
    if not cleaner.process_all_dc_files():
        raise SystemExit('日月新 FT DC cleaner returned false')
except LotOverrideRequired as exc:
    payload = {
        'field_code': 'LOT_ID',
        'files': [{'original_file_name': name} for name in exc.file_names],
        'message': str(exc),
    }
    sys.stderr.write('TMS_INPUT_REQUIRED_JSON=' + json.dumps(
        payload, ensure_ascii=False, separators=(',', ':')
    ) + '\\n')
    raise SystemExit(42)
"""


_FT_RIYUEGUANG_DC_SCRIPT = """
import json, os, sys
sys.path.insert(0, os.environ['TMS_EXISTING_CLEANER_PACKAGE'])
from factories.tms_adapters.riyueguang_dc import RiyueguangTmsDCCleaner
from factories.tms_adapters.identity import LotOverrideRequired
inputs = json.loads(os.environ['TMS_EXISTING_CLEANER_INPUTS'])
lot_overrides = json.loads(os.environ.get('TMS_LOT_OVERRIDES_JSON', '{}'))
try:
    cleaner = RiyueguangTmsDCCleaner(
        input_dir=inputs[0],
        output_dir=os.environ['TMS_EXISTING_CLEANER_OUTPUT'],
        lot_overrides=lot_overrides,
    )
    if not cleaner.process_all_dc_files():
        raise SystemExit('日月光 FT DC cleaner returned false')
except LotOverrideRequired as exc:
    payload = {
        'field_code': 'LOT_ID',
        'files': [{'original_file_name': name} for name in exc.file_names],
        'message': str(exc),
    }
    sys.stderr.write('TMS_INPUT_REQUIRED_JSON=' + json.dumps(
        payload, ensure_ascii=False, separators=(',', ':')
    ) + '\\n')
    raise SystemExit(42)
"""


_FT_DIANJI_POWERTECH_SCRIPT = """
import csv, gzip, json, os, sys
from collections import Counter
from pathlib import Path, PureWindowsPath
sys.path.insert(0, os.environ['TMS_EXISTING_CLEANER_PACKAGE'])
from factories.dianji.dc_cleaner import DianjiDCCleaner
from factories.dianji.powertech_parser import (
    _locate_header_rows,
    _metadata_value,
    _read_source_text,
)
from factories.dianji.powertech_xlsx_parser import _header_metadata, _read_workbook
from factories.dianji.source_registry import parse_dianji_source_file
inputs = json.loads(os.environ['TMS_EXISTING_CLEANER_INPUTS'])
if len(inputs) != 1 or not Path(inputs[0]).is_dir():
    raise SystemExit('电基 FT Adapter 需要一个已隔离的源文件目录')
supplied_identities = json.loads(os.environ.get('TMS_SOURCE_IDENTITIES_JSON', '{}'))
cleaner_options = {'identity_overrides': supplied_identities} if supplied_identities else {}
import inspect
if 'export_artifacts' in inspect.signature(DianjiDCCleaner).parameters:
    cleaner_options['export_artifacts'] = True
cleaner = DianjiDCCleaner(
    input_dir=inputs[0],
    output_dir=os.environ['TMS_EXISTING_CLEANER_OUTPUT'],
    **cleaner_options,
)
if not cleaner.process_all():
    raise SystemExit('电基 FT-ALL cleaner returned false')
manifest_path = cleaner.last_scatter_manifest
if manifest_path is None or not Path(manifest_path).is_file():
    raise SystemExit('电基 FT-ALL cleaner did not create a scatter manifest')
manifest_path = Path(manifest_path).resolve()
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
product = str(cleaner.last_run_summary.get('product') or '').strip()
if manifest.get('factory') != '电基' or manifest.get('data_type') != 'FT-ALL' or not product:
    raise SystemExit('电基 FT-ALL output identity is incomplete')
source_identities = []
qa_records = {}
for source in cleaner.scan_source_files():
    supplied = supplied_identities.get(source.name)
    parsed = parse_dianji_source_file(source, identity_override=supplied) if supplied else parse_dianji_source_file(source)
    identity = parsed.identity
    if parsed.source_format == 'PowerTECH':
        source_text, _encoding = _read_source_text(source)
        source_rows = [
            [field.strip() for field in line.split('\\t')]
            for line in source_text.splitlines()
        ]
        labels = _locate_header_rows(source_rows, source)
        test_file_name = PureWindowsPath(_metadata_value(
            source_rows, labels['Serial#'], 'TestFileName', source
        )).name
    elif parsed.source_format == 'PowerTECH XLSX':
        test_file_name = PureWindowsPath(
            _header_metadata(_read_workbook(source))['test_file']
        ).name
    elif parsed.source_format == 'QA BIFF XLS':
        test_file_name = parsed.test_program
        qa_records[source.stem] = parsed.records
    elif parsed.source_format == 'STS8203 CSV':
        lines = source.read_text(encoding='gb18030').splitlines()
        programs = [line.split(':', 1)[1].strip() for line in lines if line.strip().startswith('Program') and ':' in line]
        if len(programs) != 1:
            raise ValueError('电基 STS8203 测试程序缺失或不唯一')
        test_file_name = PureWindowsPath(programs[0]).name
    elif parsed.source_format == 'Dianji TF CSV':
        from factories.dianji.tf_csv_parser import TF_PROGRAM
        test_file_name = TF_PROGRAM
    else:
        raise SystemExit('电基 FT Adapter 未登记该源格式')
    if not test_file_name:
        raise SystemExit('电基 FT TestFileName is missing')
    source_identities.append({
        'source_id': source.stem,
        'source_file': source.name,
        'product_name': identity.product,
        'lot_id': identity.batch,
        'manufacturing_lot': identity.manufacturing_lot,
        'test_tag': identity.test_tag,
        'test_file_name': test_file_name,
        'source_segment': identity.source_segment,
        'source_format': parsed.source_format,
        'metadata_lot': parsed.metadata_lot,
        'source_quality': {
            'source_rows': parsed.source_rows,
            'kept_rows': parsed.kept_rows,
            'dropped_rows': parsed.source_rows - parsed.kept_rows,
            'source_rows_basis': 'MATURE_FACTORY_PARSER',
            'exclusion_reason': 'ENTRY_PARAMETER_NOT_MEASURED',
            **({'raw_yield': {
                'total': parsed.source_rows,
                'passed': parsed.raw_bin_counts.get('1', 0),
                'unknown': parsed.raw_bin_counts.get('UNKNOWN', 0),
                'bin_counts': parsed.raw_bin_counts,
                'rule': 'DIANJI_POWERTECH_RAW_BIN1_V1',
            }} if parsed.source_format in {'PowerTECH', 'PowerTECH XLSX'} and getattr(parsed, 'raw_bin_counts', None) else {}),
            **({'raw_yield': parsed.raw_yield, 'exclusion_reason': 'NONE_ALL_SOURCE_RECORDS'} if parsed.source_format == 'QA BIFF XLS' else {}),
        },
    })
if (
    {item['source_id'] for item in source_identities} != set(manifest.get('sources') or [])
    or {item['lot_id'] for item in source_identities} != set(manifest.get('lots') or [])
    or {item['product_name'] for item in source_identities} != {product}
):
    raise SystemExit('电基 FT-ALL source identity reconciliation failed')
manifest['factory_code'] = 'DIANJI'
manifest['product_name'] = product
manifest['adapter_contract_version'] = ('DIANJI_REGISTERED_TMS_V2' if any(item['source_format'] in {'STS8203 CSV', 'Dianji TF CSV'} for item in source_identities) else 'DIANJI_POWERTECH_TMS_V1')
if qa_records:
    if set(qa_records) != set(manifest.get('sources') or []):
        raise SystemExit('QA record metadata must cover every source')
    manifest['adapter_contract_version'] = 'DIANJI_QA_TMS_V1'
manifest['source_identities'] = source_identities
output_root = manifest_path.parent.resolve()
data_path = (output_root / str(manifest.get('data_file') or '')).resolve()
spec_path = (output_root / str(manifest.get('spec_file') or '')).resolve()
fixed_data_path = output_root / 'ft_scatter_data.csv.gz'
fixed_spec_path = output_root / 'ft_scatter_spec.csv'
fixed_manifest_path = output_root / 'ft_scatter_manifest.json'
if (
    data_path.parent != output_root
    or spec_path.parent != output_root
    or data_path == spec_path
    or not data_path.is_file()
    or not spec_path.is_file()
):
    raise SystemExit('电基 FT-ALL scatter artifacts are incomplete')
if qa_records:
    record_fields = ('Source_Row', 'Serial', 'Part_ID', 'Pass_State', 'Hard_Bin', 'Site_ID')
    offsets = Counter()
    with gzip.open(data_path, 'rt', encoding='utf-8-sig', newline='') as original, gzip.open(fixed_data_path, 'wt', encoding='utf-8-sig', newline='') as annotated:
        reader = csv.DictReader(original)
        writer = csv.DictWriter(annotated, fieldnames=[*reader.fieldnames, *('QA_' + f for f in record_fields)])
        writer.writeheader()
        for row in reader:
            source_id = row['Source_ID']
            metadata_row = qa_records[source_id][offsets[source_id]]
            writer.writerow({**row, **{'QA_' + f: metadata_row[f] for f in record_fields}})
            offsets[source_id] += 1
    if any(offsets[k] != len(v) for k, v in qa_records.items()):
        raise SystemExit('QA record metadata counts do not reconcile')
    data_path.unlink()
else:
    data_path.replace(fixed_data_path)
spec_path.replace(fixed_spec_path)
manifest['data_file'] = fixed_data_path.name
manifest['spec_file'] = fixed_spec_path.name
fixed_manifest_path.write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8'
)
if fixed_manifest_path != manifest_path:
    manifest_path.unlink()
"""
