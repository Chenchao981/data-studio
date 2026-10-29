"""Copy selected private verification receipts without moving data or history.

The destination is local-only and ignored by Git. Original path references in
copied records are preserved; this is an evidence archive, not a runnable home.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RECEIPTS = {'receipt.json', 'outcome.json', 'request.json', 'validation-engine.json',
            'PAT_source_manifest.json', 'native-summary.json', 'input-fingerprint.json'}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def archive(output):
    output = output.resolve()
    # Keeping the archive in this explicit ignored tree avoids accidentally
    # collecting private evidence into a tracked documentation directory.
    if not output.is_relative_to(ROOT / 'local-evidence'):
        raise ValueError('Evidence destination must be inside local-evidence/')
    output.mkdir(parents=True, exist_ok=False)
    rows, missing = [], []

    def copy(source, target):
        if not source.is_file():
            missing.append(str(source))
            return
        target = output / target
        if target.exists():
            raise ValueError('Duplicate evidence target: ' + str(target))
        before = digest(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if digest(target) != before or digest(source) != before:
            raise ValueError('Evidence changed while copying: ' + str(source))
        rows.append(dict(source=str(source), archived=str(target.relative_to(output)),
                         bytes=target.stat().st_size, sha256=before))

    temp = Path(tempfile.gettempdir())
    for label, name in [('huahong', 'DataStudio-standalone-huahong-pat-20261029'),
                        ('jiemin', 'DataStudio-standalone-jiemin-ft-20261029c')]:
        copy(temp / (name + '.log'), Path('baseline') / label / 'task.log')
        source = temp / name / 'results'
        if not source.is_dir():
            missing.append(str(source))
        else:
            for path in sorted(source.rglob('*')):
                if path.is_file() and (path.name in RECEIPTS or path.name == 'execution.log'):
                    copy(path, Path('baseline') / label / 'results' / path.relative_to(source))
    for label, source in [('desktop-ui', temp / 'DataStudio-standalone-desktop-ui-20261029'),
                          ('installer', ROOT / 'build/installer-validation/0b401f09')]:
        if not source.is_dir():
            missing.append(str(source))
        else:
            for path in sorted(source.rglob('*')):
                if path.is_file() and (path.name == 'evidence.json' or path.suffix == '.png'):
                    copy(path, Path('baseline') / label / path.relative_to(source))
    for name in ['installer-uat-0.3.3.log', 'publish-0.3.3.log']:
        copy(ROOT / 'build' / name, Path('baseline') / name)
    p02 = ROOT / 'build/p0-2-20261029'
    for name in ['summary.json', 'reconciliation.json', 'project-cp.log', 'project-ft.log',
                 'installer-cp.log', 'installer-ft.log', 'tampered-cp.log', 'tampered-ft.log']:
        copy(p02 / name, Path('p0-2') / name)
    for path in sorted(p02.glob('*-v2/results/*/validation-engine.json')):
        copy(path, Path('p0-2') / path.relative_to(p02))
    # Historical independent statistical reconciliation, metadata only.
    previous = Path('F:/CP-FT数据分析/outputs/huahong_product_pat_20261028')
    for name in ['final-reconciliation.json', 'published-reconciliation.json']:
        copy(previous / name, Path('baseline/huahong-independent') / name)
    record = dict(schema=1, archivedUtc=datetime.now(timezone.utc).isoformat(),
                  scope='Selected original receipts and screenshots; no raw inputs, reports, databases, engines or installers',
                  files=rows, missingSources=missing)
    (output / 'archive-manifest.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(dict(files=len(rows), missingSources=missing, output=str(output)), ensure_ascii=False))
    return bool(missing)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New directory inside local-evidence/')
    raise SystemExit(archive(parser.parse_args().output))
