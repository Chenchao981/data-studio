"""Validate an exact Python/package profile without changing the environment."""
import argparse
import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path


def requirements(path, seen=None):
    seen = set() if seen is None else seen
    path = Path(path).resolve()
    if path in seen:
        raise ValueError('Recursive requirements include')
    seen.add(path)
    result = {}
    for line in path.read_text(encoding='utf8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('-r '):
            items = requirements(path.parent / line[3:].strip(), seen)
        else:
            name, version = line.split('==')
            items = {name.lower().replace('_', '-'): version}
        for name, version in items.items():
            if name in result and result[name] != version:
                raise ValueError(f'Conflicting pin: {name}')
            result[name] = version
    seen.remove(path)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', required=True, type=Path)
    args = parser.parse_args()
    runtime = json.loads((args.profile.parent / 'runtime-lock.json').read_text())
    errors = []
    if platform.python_implementation() != runtime['implementation'] or platform.python_version() != runtime['version']:
        errors.append('Python implementation/version mismatch')
    pins = requirements(args.profile)
    for name, version in pins.items():
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            actual = 'MISSING'
        if actual != version:
            errors.append(f'{name}: expected {version}, found {actual}')
    check = subprocess.run([sys.executable, '-m', 'pip', 'check'], capture_output=True, text=True)
    if check.returncode:
        errors.append(check.stdout + check.stderr)
    print(json.dumps({'status': 'FAIL' if errors else 'PASS', 'python': platform.python_version(), 'packages': len(pins), 'errors': errors}))
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
