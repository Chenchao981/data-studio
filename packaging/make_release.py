"""Create a versioned, offline Windows installer from a verified frozen bundle."""
from __future__ import annotations

import ast
import hashlib
import json
import re
import shutil
import subprocess
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def checked_path(root: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts or "\\" in name or ":" in name:
        raise ValueError(f"Invalid payload path: {name}")
    target = (root / name).resolve()
    if not target.is_relative_to(root.resolve()) or not target.is_file():
        raise ValueError(f"Payload file unavailable: {name}")
    return target


def application_version() -> str:
    tree = ast.parse((ROOT / "python_core/core.py").read_text(encoding="utf-8-sig"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "VERSION" for t in node.targets):
            version = ast.literal_eval(node.value)
            if not re.fullmatch(r"\d+\.\d+\.\d+", version):
                raise ValueError("Installer needs a numeric application version")
            return version
    raise ValueError("Application version unavailable")


def compiler() -> tuple[Path, dict]:
    lock = json.loads((ROOT / "packaging/nsis-lock.json").read_text())
    cache = ROOT / "build/tools"
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / f"nsis-{lock['version']}.zip"
    if not archive.is_file():
        subprocess.run(["curl.exe", "--fail", "--location", "--retry", "2", "--max-time", "120", "--output", str(archive), lock["url"]], check=True)
    if sha256(archive) != lock["sha256"]:
        raise ValueError("NSIS compiler archive checksum mismatch")
    # Re-extract the pinned compiler to a fresh build-only directory each time.
    tools = cache / ("verified-" + uuid.uuid4().hex)
    tools.mkdir()
    with zipfile.ZipFile(archive) as package:
        for entry in package.infolist():
            if not (tools / entry.filename).resolve().is_relative_to(tools.resolve()):
                raise ValueError("Compiler archive escapes build directory")
        package.extractall(tools)
    exe = tools / f"nsis-{lock['version']}" / "makensis.exe"
    actual = subprocess.check_output([str(exe), "/VERSION"], text=True).strip()
    if actual != "v" + lock["version"]:
        raise ValueError("Unexpected installer compiler version")
    return exe, lock


def bundle_payload(bundle: Path) -> tuple[dict[str, Path], dict]:
    manifest = json.loads((bundle / "engines/manifest.json").read_text(encoding="utf8"))
    if manifest["python"] != "3.13.17" or not manifest["tools"]:
        raise ValueError("Missing pinned calculation runtime")
    files = {**manifest["files"], **manifest.get("viewer", {}).get("files", {})}
    payload = {}
    for name, expected in files.items():
        source = checked_path(bundle / "engines", name)
        if sha256(source) != expected:
            raise ValueError(f"Engine file checksum mismatch: {name}")
        payload["engines/" + name] = source
    for name in ["manifest.json", "runtime/runtime-manifest.json"]:
        payload["engines/" + name] = checked_path(bundle / "engines", name)
    pins = json.loads((ROOT / "engine-pins.json").read_text())
    for name in ["cp", "native", "shared"]:
        if sha256(bundle / f"engines/packages/{name}.pyz") != pins[name]:
            raise ValueError(f"Calculation package is not pinned: {name}")
    payload["DesktopDataStudio.exe"] = checked_path(bundle, "DesktopDataStudio.exe")
    for source in (bundle / "_internal").rglob("*"):
        if source.is_file():
            if source.is_symlink() or not source.resolve().is_relative_to(bundle):
                raise ValueError("Frozen application contains an external file link")
            payload[source.relative_to(bundle).as_posix()] = source
    if "_internal/web/index.html" not in payload:
        raise ValueError("Frozen web assets missing")
    # Prevent accidentally publishing yesterday's HTML/JS after a frontend build.
    for source in (ROOT / "apps/web/dist").rglob("*"):
        if source.is_file():
            name = "_internal/web/" + source.relative_to(ROOT / "apps/web/dist").as_posix()
            if name not in payload or sha256(source) != sha256(payload[name]):
                raise ValueError("Frozen web resources differ from current built UI: " + name)
    if not any(name.startswith("_internal/third-party-notices/") for name in payload):
        raise ValueError("Third-party license notices are missing")
    return payload, manifest


def nsis(value: str | Path) -> str:
    text = str(value)
    if any(c in text for c in "\r\n\x00"):
        raise ValueError("Unexpected control character in installer path")
    return text.replace("$", "$$").replace('"', '$\\"')


def includes(payload: dict[str, Path], workspace: Path) -> tuple[Path, Path]:
    install = []
    remove = []
    folders = set()
    previous = None
    for name, source in sorted(payload.items()):
        relative = PurePosixPath(name)
        target = relative.as_posix().replace("/", "\\")
        parent = str(relative.parent).replace("/", "\\")
        if parent != previous:
            out = "$INSTDIR" if parent == "." else "$INSTDIR\\" + nsis(parent)
            install.append(f'SetOutPath "{out}"')
            previous = parent
        install.append(f'File /oname="{nsis(relative.name)}" "{nsis(source)}"')
        remove.append(f'Delete "$INSTDIR\\{nsis(target)}"')
        folders.update(p.as_posix().replace("/", "\\") for p in relative.parents if p.as_posix() != ".")
    for folder in sorted(folders, key=lambda p: (-p.count("\\"), p)):
        remove.append(f'RMDir "$INSTDIR\\{nsis(folder)}"')
    install_file, remove_file = workspace / "payload.nsh", workspace / "uninstall-files.nsh"
    install_file.write_text("\n".join(install) + "\n", encoding="utf-8-sig")
    remove_file.write_text("\n".join(remove) + "\n", encoding="utf-8-sig")
    return install_file, remove_file


def main() -> None:
    version = application_version()
    output = ROOT / "release" / ("v" + version)
    if output.exists():
        raise FileExistsError(f"Release already exists; keep it immutable and use a new version: {output}")
    bundle = (ROOT / "dist/DesktopDataStudio").resolve()
    print("Checking frozen application and calculation engine...", flush=True)
    payload, engine = bundle_payload(bundle)
    exe, toolchain = compiler()
    payload["安装使用说明.txt"] = ROOT / "packaging/user-guide.txt"
    payload["licenses/NSIS-COPYING.txt"] = exe.parent / "COPYING"
    staging = ROOT / "release" / (".v" + version + "-" + uuid.uuid4().hex)
    staging.mkdir(parents=True)
    workspace = ROOT / "build/installer" / uuid.uuid4().hex
    workspace.mkdir(parents=True)
    hashes = {name: sha256(source) for name, source in sorted(payload.items())}
    size = sum(source.stat().st_size for source in payload.values())
    install_manifest = workspace / "install-manifest.json"
    install_manifest.write_text(json.dumps(dict(version=version, engineVersion=engine["version"], files=hashes), ensure_ascii=False, indent=2), encoding="utf8")
    install, remove = includes(payload, workspace)
    setup = staging / f"DataStudio-{version}-win-x64-Setup.exe"
    defines = dict(APP_VERSION=version, SETUP_FILE=setup, ICON_FILE=ROOT / "packaging/studio.ico", PAYLOAD_INCLUDE=install, UNINSTALL_INCLUDE=remove, MANIFEST_FILE=install_manifest, INSTALLED_KB=(size + 1023) // 1024)
    command = [str(exe), "/V2", "/INPUTCHARSET", "UTF8", *[f"/D{k}={v}" for k, v in defines.items()], str(ROOT / "packaging/installer.nsi")]
    print(f"Building offline installer: {len(payload)} files, {size / 1024**3:.2f} GiB installed", flush=True)
    subprocess.run(command, check=True)
    shutil.copyfile(ROOT / "packaging/user-guide.txt", staging / "安装使用说明.txt")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    receipt = dict(version=version, architecture="win-x64", createdUtc=datetime.now(timezone.utc).isoformat(), sourceCommit=commit, python="3.13.17", engineVersion=engine["version"], operations=len(engine["tools"]), installedFiles=len(payload) + 1, installedBytes=size + install_manifest.stat().st_size, installer=dict(name=setup.name, bytes=setup.stat().st_size, sha256=sha256(setup)), toolchain=toolchain, enterpriseCodeSigned=False, userDataIncluded=False)
    (staging / "release.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf8")
    (staging / "SHA256SUMS.txt").write_text("".join(f"{sha256(p)}  {p.name}\n" for p in sorted(staging.iterdir()) if p.is_file()), encoding="utf8")
    staging.rename(output)
    print(json.dumps(dict(status="PASS", directory=str(output), installer=receipt["installer"]), ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
