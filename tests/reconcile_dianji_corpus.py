"""Reconcile Studio workbooks with the original tool's explicit sample corpus.

The original validate_dianji_marker_samples.py independently checks raw cells,
row identities, Bin counts and retention. Here we require its receipt to match
the selected input hash, then compare every exported cell and number format.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine_support/scripts/g0'))
from compare_native_results import compare_rows, tables


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def main():
    parser = argparse.ArgumentParser()
    for name in ['baseline', 'studio', 'provenance', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    baseline = read(args.baseline)
    provenance = read(args.provenance)
    studio = {r['title']: r for r in read(args.studio / 'validation.json')}
    assert len(baseline) == len(provenance) == len(studio)
    results = []
    for original, source in zip(baseline, provenance):
        assert original['status'] == 'PASS'
        path = Path(source['path'])
        assert original['file'] == path.name
        assert original['folder'] == source['selection']['folder']
        assert original['source_sha256'] == source['sha256']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source['sha256']
        if 'archive' in source['selection']:
            import zipfile
            with zipfile.ZipFile(source['selection']['archive']) as archive:
                content = archive.read(source['selection']['member'])
                assert hashlib.sha256(content).hexdigest() == source['sha256']
        row = studio[source['case']]
        assert row['status'] == 'SUCCESS'
        workbooks = list(tables(args.studio, row).values())
        assert len(workbooks) == 1
        left = openpyxl.load_workbook(original['workbook'], read_only=True, data_only=False)
        right = openpyxl.load_workbook(workbooks[0], read_only=True, data_only=False)
        cells = 0
        try:
            assert left.sheetnames == right.sheetnames
            for name in left.sheetnames:
                cells += compare_rows(left[name].iter_rows(), right[name].iter_rows(), source['case'] + '/' + name, formats=True)
        finally:
            left.close()
            right.close()
        results.append({'case': source['case'], 'status': 'PASS', 'cells': cells,
                        'source_rows': original['source_rows'], 'kept_rows': original['kept_rows'],
                        'independent_raw_cells': original['cells_checked']})
        args.output.write_text(json.dumps(results, indent=2), encoding='utf8')
        print(source['case'], cells, 'cells PASS', flush=True)


if __name__ == '__main__':
    main()
