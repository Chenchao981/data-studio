"""Contract, lineage and immutable-result tests for the native desktop bridge."""

import json
from pathlib import Path
import sys
import zipfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nce_desktop.local_engines import capabilities, request_for, paths
from nce_desktop.local_native import OPERATIONS, visible
from nce_desktop.local_results import copy_dataset
from nce_desktop.local_store import History
from nce_desktop.local_worker import source_fingerprint
from nce_desktop.storage import digest, write_json


@pytest.fixture
def home(tmp_path):
    paths()
    home = tmp_path / "home"
    (home / "engines").mkdir(parents=True)
    engines = {}
    for stage in ("CP", "FT"):
        package = home / "engines" / (stage + ".pyz")
        with zipfile.ZipFile(package, "w") as archive:
            if stage == 'FT':
                for module in ('shared/pat_engine.py', 'shared/excel_utils.py'):
                    archive.writestr(module, '# test FT PAT component\n')
            for module in sorted({s.module for s in OPERATIONS if s.stage == stage}):
                archive.writestr(module, "# test contract module\n")
        engines[stage] = {"path": str(package), "sha256": digest(package)}
    write_json(
        home / "engines/registry.json", {"runtime": sys.executable, "engines": engines}
    )
    return home


def result_task(home, members=None, factory="JIEQUN"):
    h = History(home)
    request = {
        "stage": "FT",
        "factory": factory,
        "operation": "QUICK_CLEAN",
        "title": "clean",
        "tool_code": "old-code",
        "source": str(home.parent / "raw"),
        "parameters": {},
    }
    task = h.create(request)
    h.transition(task, "RUNNING")
    folder = h.task_dir(task) / "result"
    folder.mkdir()
    report = folder / "result.zip"
    with zipfile.ZipFile(report, "w") as archive:
        for name, content in (
            members or {"lot/DC.xlsx": b"worksheet", "other.py": b"not executable"}
        ).items():
            archive.writestr(name, content)
    receipt = {
        "artifacts": [
            {
                "path": "result.zip",
                "size": report.stat().st_size,
                "sha256": digest(report),
                "primary": True,
            }
        ]
    }
    h.transition(task, "SUCCESS", result=receipt)
    return h, task, report


def test_all_native_contracts_available_and_old_history_codes_retained(home):
    tools = capabilities(home)
    native = [t for t in tools if t.tool_code.startswith("LOCAL_")]
    assert len(native) == 25 and all(t.enabled for t in native)
    assert len({t.tool_code for t in tools}) == len(tools)
    assert any(
        t.factory_code == "HUAHONG" and t.tool_code.endswith("TD_V1") for t in native
    )
    assert any(
        t.factory_code == "LION" and ".rar" in t.allowed_suffixes for t in native
    )
    old = next(t for t in tools if t.tool_code == "JIEQUN_FT_QUICK_PAT_EXISTING::CLEAN")
    assert not visible(old)  # retained for replay, replaced on the new-task form


def test_changed_package_disables_native_capability(home):
    (home / "engines/CP.pyz").write_bytes(b"modified")
    tools = capabilities(home)
    assert all(not t.enabled for t in tools if t.test_stage == "CP")


def test_jiemin_v22615_routes_keep_old_dc_code_and_add_independent_dvds(home):
    tools={t.tool_code:t for t in capabilities(home)}
    assert tools['LOCAL_FT_JIEMIN_FT_ALL_V1'].display_name=='DC 数据清洗'
    dvds=tools['LOCAL_FT_JIEMIN_DVDS_V1']
    assert dvds.entrypoint=='factories/jiemin/dvds_cleaner.py'
    assert set(dvds.allowed_suffixes)=={'.xls','.xlsx'}
    assert set(tools['LOCAL_FT_JIEMIN_RG_V1'].allowed_suffixes)=={'.csv','.xls','.xlsx'}
    chart=tools['JIEMIN_FT_QUICK_PAT_EXISTING::CHART']
    assert chart.input_kind=='directory' and set(chart.allowed_suffixes)=={'.xls','.xlsx'}


@pytest.mark.parametrize("mode", ["FT_ALL", "RAW_PAT", "DVDS", "RG"])
def test_jiemin_xlsx_is_fingerprinted_alongside_xls(home, tmp_path, mode):
    # The v2.26.10 original cleaner supports OOXML. A missing suffix silently
    # omitted XLSX in mixed folders and rejected XLSX-only input before parsing.
    source = tmp_path / "raw"
    source.mkdir()
    for name in ("old.xls", "dynamic.xlsx"):
        (source / name).write_bytes(name.encode())
    code = f"LOCAL_FT_JIEMIN_{mode}_V1"
    request_for(home, code, str(source))
    tool = next(t for t in capabilities(home) if t.tool_code == code)
    manifest, files = source_fingerprint([source], tool, tmp_path / "work")
    assert manifest.file_count == 2
    assert {Path(row["path"]).suffix for row in files} == {".xls", ".xlsx"}


def test_td_multi_selection_fingerprints_every_file_and_rejects_duplicates(
    home, tmp_path
):
    files = [tmp_path / "first.xlsx", tmp_path / "second.xlsx"]
    for file in files:
        file.write_bytes(b"data")
    req = request_for(home, "LOCAL_CP_HUAHONG_TD_V1", "; ".join(map(str, files)))
    assert req["source_paths"] == list(map(str, files))
    tool = next(t for t in capabilities(home) if t.tool_code == req["tool_code"])
    manifest, before = source_fingerprint(files, tool, tmp_path)
    files[1].write_bytes(b"edit")
    _, after = source_fingerprint(files, tool, tmp_path)
    assert manifest.file_count == 2 and before[0] == after[0] and before[1] != after[1]
    with pytest.raises(ValueError, match="重复"):
        request_for(home, tool.tool_code, f"{files[0]}; {files[0]}")
    with pytest.raises(ValueError, match="混选"):
        request_for(home, tool.tool_code, f"{files[0]}; {tmp_path}")


def test_native_inputs_validate_mode_suffix_and_managed_home(home, tmp_path):
    csv = tmp_path / "sample.csv"
    csv.touch()
    with pytest.raises(ValueError):
        request_for(home, "LOCAL_CP_HUAHONG_TD_V1", str(csv))
    with pytest.raises(ValueError, match="文件夹"):
        request_for(home, "LOCAL_FT_JIEMIN_RG_V1", str(csv))
    with pytest.raises(ValueError):
        request_for(home, "LOCAL_FT_JIEMIN_RG_V1", str(home))


def test_history_pat_validates_factory_and_keeps_lineage(home):
    h, task, report = result_task(home)
    req = request_for(home, "LOCAL_FT_JIEQUN_CLEANED_PAT_V1", "history://" + task)
    assert req["parent_id"] == task and req["source_task_id"] == task
    assert req["source_paths"] is None
    replay = request_for(
        home,
        "LOCAL_FT_JIEQUN_CLEANED_PAT_V1",
        "history://" + task,
        parent_id="previous-pat",
    )
    assert replay["parent_id"] == "previous-pat" and replay["source_task_id"] == task
    for code in [
        "LOCAL_FT_DIANJI_CLEANED_PAT_V1",
        "LOCAL_FT_RIYUEXIN_CLEANED_PAT_V1",
        "LOCAL_FT_JIEQUN_RAW_PAT_V1",
    ]:
        with pytest.raises(ValueError):
            request_for(home, code, "history://" + task)
    with pytest.raises(ValueError):
        request_for(home, "LOCAL_FT_JIEQUN_CLEANED_PAT_V1", "history://../escape")


def test_result_copy_does_not_mutate_history_and_rejects_tamper(home, tmp_path):
    h, task, report = result_task(home)
    checksum = digest(report)
    copied = copy_dataset(h, task, tmp_path / "copy")
    assert not (copied / "other.py").exists()
    (copied / "lot/DC.xlsx").write_bytes(b"modified copy")
    assert digest(report) == checksum
    report.write_bytes(b"changed result")
    with pytest.raises(ValueError, match="改变"):
        copy_dataset(h, task, tmp_path / "second")


@pytest.mark.parametrize(
    "name", ["../escape.xlsx", "C:/escape.xlsx", "nested/../../escape.xlsx"]
)
def test_result_copy_rejects_escaping_paths(home, tmp_path, name):
    h, task, _ = result_task(home, {name: b"payload"})
    with pytest.raises(ValueError, match="路径"):
        copy_dataset(h, task, tmp_path / "copy")
    assert not (tmp_path / "escape.xlsx").exists()


def test_dependency_upgrade_preserves_pinned_files_and_refuses_tamper(
    tmp_path, monkeypatch
):
    import importlib.util
    import importlib.metadata
    from types import SimpleNamespace
    from nce_desktop.local_engines import prepare_dependencies, dependency_path

    installed = tmp_path / "installed"
    for name in ("xlsxwriter", "xlrd", "py7zr", "archive_dependency"):
        folder = installed / name
        folder.mkdir(parents=True)
        (folder / "__init__.py").write_text("# installed module", encoding="utf-8")
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name: SimpleNamespace(origin=str(installed / name / "__init__.py")),
    )

    def dist(name):
        return SimpleNamespace(
            version="1.0",
            files=[Path(name) / "__init__.py"],
            requires=(
                ["archive_dependency", "ignored; extra == 'test'"]
                if name == "py7zr"
                else []
            ),
            locate_file=lambda path: installed / path,
        )

    monkeypatch.setattr(importlib.metadata, "distribution", dist)
    home = tmp_path / "home"
    folder = home / "runtime-packages"
    (folder / "xlsxwriter").mkdir(parents=True)
    pinned = folder / "xlsxwriter/__init__.py"
    pinned.write_text("# previously pinned version", encoding="utf-8")
    original = digest(pinned)
    write_json(
        folder / "manifest.json",
        {
            "schema": 1,
            "python": list(sys.version_info[:2]),
            "files": {"xlsxwriter/__init__.py": original},
        },
    )
    prepare_dependencies(home)
    assert digest(pinned) == original
    assert (dependency_path(home) / "xlrd/__init__.py").is_file()
    assert (folder / "archive_dependency/__init__.py").is_file()
    assert not (folder / "ignored").exists()
    pinned.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="改变"):
        prepare_dependencies(home)
