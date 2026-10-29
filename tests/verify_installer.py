"""Install/reinstall/uninstall the real EXE in a disposable Chinese-path folder."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid
import winreg

KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\NCE.DataStudio"
ROOT = Path(__file__).resolve().parents[1]


def registration():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as key:
            return {name: winreg.QueryValueEx(key, name)[0] for name in ["InstallLocation", "DisplayVersion", "UninstallString"]}
    except FileNotFoundError:
        return None


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("setup", type=Path)
    parser.add_argument("--home", type=Path, required=True, help="Private UI-test workspace containing a completed HuaHong PAT task")
    args = parser.parse_args()
    if registration():
        raise RuntimeError("An installed Data Studio is already registered; this test will not replace it")
    desktop = Path(subprocess.check_output(["powershell.exe", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"], text=True).strip())
    shortcut = desktop / "Data Studio.lnk"
    if shortcut.exists():
        raise RuntimeError("A Data Studio shortcut already exists; preserve it before running this isolated test")
    token = uuid.uuid4().hex[:8]
    install = Path(tempfile.gettempdir()).resolve() / f"DataStudio-UAT-{token} 安装验证"
    assert install.parent == Path(tempfile.gettempdir()).resolve() and not install.exists()
    output = ROOT / "build/installer-validation" / token
    output.mkdir(parents=True)
    personal = Path(os.environ["LOCALAPPDATA"]) / "NCE/DesktopDataStudio-M0"
    personal.mkdir(parents=True, exist_ok=True)
    sentinel = personal / f"installer-uat-{token}.keep"
    sentinel.write_text(token)
    report = {"installationPath": str(install), "checks": []}
    # NSIS /D= must be the last unquoted argument, including a path with spaces.
    command = f'"{args.setup.resolve()}" /S /D={install}'
    try:
        print("Installing real package in disposable Chinese-path directory", flush=True)
        subprocess.run(command, check=True, timeout=900)
        info = registration()
        manifest = json.loads((install / "install-manifest.json").read_text(encoding="utf8"))
        assert Path(info["InstallLocation"]).resolve() == install
        assert info["DisplayVersion"] == manifest["version"]
        assert shortcut.exists()
        assert (Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Data Studio/Data Studio.lnk").is_file()
        for name, expected in manifest["files"].items():
            path = (install / name).resolve()
            assert path.is_relative_to(install) and digest(path) == expected, name
        report["installedFilesVerified"] = len(manifest["files"])
        report["checks"].append("Actual installer, Chinese path, full payload hashes, HKCU registration and shortcuts")
        own_file = install / "user-added-file.keep"
        own_file.write_text(token)
        print("Reinstalling to verify update and personal-file retention", flush=True)
        subprocess.run(command, check=True, timeout=900)
        assert own_file.read_text() == token and sentinel.read_text() == token
        report["checks"].append("Reinstall preserves personal history sentinel and unowned installation file")
        print("Checking frozen installed application through local Qt interface", flush=True)
        subprocess.run(["node", str(ROOT / "apps/web/tests/verify-huahong-pat-ui.mjs"), str(install / "DesktopDataStudio.exe"), str(args.home.resolve()), str(output / "ui")], env={**os.environ, "STUDIO_EXPECTED_VERSION": manifest["version"]}, check=True, timeout=180)
        report["ui"] = json.loads((output / "ui/evidence.json").read_text())
        report["checks"].append("Installed EXE: isolated PATH, CP/FT navigation, HuaHong PAT, real history, no Excel preview")
        print("Uninstalling and checking retention", flush=True)
        subprocess.run([str(install / "Uninstall.exe"), "/S"], check=True, timeout=120)
        deadline = time.monotonic() + 180
        while registration() is not None and time.monotonic() < deadline:
            time.sleep(0.5)
        assert registration() is None
        assert not (install / "DesktopDataStudio.exe").exists()
        assert not shortcut.exists()
        assert own_file.read_text() == token and sentinel.read_text() == token
        report["checks"].append("Uninstall removes owned program files/registration/shortcuts and retains user files/history")
        own_file.unlink()
        install.rmdir()  # Deliberately not recursive: unexpected leftovers must fail.
        report["status"] = "PASS"
        (output / "evidence.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    finally:
        # This exact sentinel was created above; never remove a personal folder.
        sentinel.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
