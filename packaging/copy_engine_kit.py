"""Copy only pinned engine files into a fresh distribution, verifying every byte."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('target', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    target = args.target.resolve()
    target.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((source / 'manifest.json').read_text(encoding='utf8'))
    files={**manifest['files'],**manifest.get('viewer',{}).get('files',{})}
    for name, expected in files.items():
        src = (source / name).resolve(); dst = (target / name).resolve()
        if not src.is_relative_to(source) or not dst.is_relative_to(target):
            raise ValueError('Engine manifest path escapes bundle')
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        with dst.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                raise ValueError('Engine file changed: ' + name)
    for name in ['manifest.json', 'runtime/runtime-manifest.json']:
        shutil.copyfile(source / name, target / name)
    print('Engine distribution verified:', len(files), 'files')


if __name__ == '__main__': main()
