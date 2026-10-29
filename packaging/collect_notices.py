"""Collect shipped runtime notices, never input files, caches or account data."""
from pathlib import Path
import importlib.metadata as md
import json
import shutil
import sys

root=Path(__file__).resolve().parents[1]
out=root/'build/notices'
out.mkdir(parents=True,exist_ok=True)
lines=['Desktop Data Studio - Third-party notices', 'Libraries are distributed unmodified; their original license terms apply.', 'Qt/PySide6: https://www.qt.io/licensing/open-source-lgpl-obligations', 'Chromium notices: https://doc.qt.io/qt-6/qtwebengine-licensing.html', '']
for name in ['PySide6','PySide6-Essentials','PySide6-Addons','shiboken6','pywin32']:
    distribution=md.distribution(name)
    lines.append(f'{distribution.metadata["Name"]} {distribution.version}')
    for file in distribution.files or []:
        if any(p.lower().startswith(('license','copying','notice')) for p in file.parts) and distribution.locate_file(file).is_file():
            target=out/name/Path(*file.parts)
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(distribution.locate_file(file),target)
lock=json.loads((root/'apps/web/package-lock.json').read_text())
for name,info in lock['packages'].items():
    if not name or info.get('dev'):continue
    package=root/'apps/web'/name
    lines.append(f'{name} {info.get("version")} {info.get("license","")}')
    for file in package.iterdir():
        if file.is_file() and file.name.lower().startswith(('license','copying','notice')):
            target=out/'npm'/name.replace('node_modules/','')/file.name
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(file,target)
license_file=Path(sys.base_prefix)/'LICENSE.txt'
for distribution in md.distributions(path=[str(root/'engines/viewer-packages')]):
    name=distribution.metadata['Name']
    lines.append(f'CP viewer: {name} {distribution.version}')
    for file in distribution.files or []:
        if '..' in file.parts:continue
        if any(p.lower().startswith(('license','copying','notice')) for p in file.parts) and distribution.locate_file(file).is_file():
            target=out/'cp-viewer'/name/Path(*file.parts)
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(distribution.locate_file(file),target)
if license_file.is_file():shutil.copyfile(license_file,out/'CPython-LICENSE.txt')
(out/'THIRD_PARTY_NOTICES.txt').write_text('\n'.join(lines),encoding='utf-8')
print('Third-party notices collected')
