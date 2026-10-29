# Run from project root: .venv-cpython/Scripts/python -m PyInstaller packaging/studio.spec
from pathlib import Path
root = Path(SPECPATH).parent
a = Analysis(
    [str(root / 'apps/desktop/main.py')],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / 'apps/web/dist'), 'web'), (str(root / 'docs/PLAN.md'), 'docs'), (str(root / 'README.md'), '.'), (str(root/'build/notices'), 'third-party-notices')],
    hiddenimports=['win32api', 'win32job', 'python_core.tasks'],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['PyQt5','PyQt6','PySide2','tkinter','pytest','pandas','numpy','openpyxl'],
    noarchive=False,
)
# Reject DLL contamination from globally installed developer tools.
allowed = [root.resolve(), Path(__import__('sys').base_prefix).resolve(), Path(__import__('os').environ['SystemRoot']).resolve()]
for destination, source, kind in a.binaries:
    if not any(Path(source).resolve().is_relative_to(base) for base in allowed):
        raise RuntimeError(f'Unexpected external runtime binary: {destination} from {source}; build with isolated PATH')
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='DesktopDataStudio', debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False, icon=str(root/'packaging/studio.ico'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='DesktopDataStudio')
