"""Stream a portable bundle to a ZIP, publishing only after successful completion."""
import argparse
import hashlib
from pathlib import Path
import zipfile

p = argparse.ArgumentParser()
p.add_argument('folder', type=Path)
p.add_argument('archive', type=Path)
a = p.parse_args()
partial = a.archive.with_suffix('.zip.partial')
if a.archive.exists() or partial.exists(): raise FileExistsError(a.archive)
with zipfile.ZipFile(partial, 'x', zipfile.ZIP_DEFLATED, compresslevel=5) as z:
    for i, file in enumerate(sorted(a.folder.rglob('*'))):
        if file.is_file():
            z.write(file, a.folder.name + '/' + file.relative_to(a.folder).as_posix())
        if i and i % 2000 == 0: print('Packaged entries:', i, flush=True)
partial.rename(a.archive)
with a.archive.open('rb') as f: checksum = hashlib.file_digest(f, 'sha256').hexdigest()
print(a.archive, a.archive.stat().st_size, checksum)
