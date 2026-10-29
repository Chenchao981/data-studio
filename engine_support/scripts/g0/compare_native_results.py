"""Compare real CP/FT run results across runtimes without changing source data.

Only generated filename timestamps are normalized. Business identifiers remain
strings, including leading zeros. Formula text and numeric Excel formats are
compared. Numeric measurement tolerance: rtol=1e-10, atol=1e-15.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import itertools
import json
import math
from numbers import Real
from pathlib import Path
import re


def equal(a, b):
    if type(a) is type(b) and a == b:
        return True
    if isinstance(a, Real) and isinstance(b, Real) and not isinstance(a, bool) and not isinstance(b, bool):
        return math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-15)
    # CSV keeps identity text exact: do not coerce plain integer strings.
    if isinstance(a, str) and isinstance(b, str) and any(ch in a+b for ch in '.eE'):
        try:
            return math.isclose(float(a), float(b), rel_tol=1e-10, abs_tol=1e-15)
        except ValueError:
            pass
    return False


def tables(home, row):
    result = {}
    for item in row.get('result', {}).get('artifacts', []):
        name = item['path']
        if Path(name).suffix.lower() not in {'.csv', '.xlsx'}:
            continue
        key = re.sub(r'_20\d{6}_?\d{4,6}(?=[./]|$)', '', name)
        path = home / 'tasks' / row['id'] / 'result' / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256'], 'Changed artifact'
        assert key not in result, 'Normalized output name collision'
        result[key] = path
    return result


def compare_rows(left, right, label, formats=False):
    missing = object()
    count = 0
    identifiers = set()
    for index, (a, b) in enumerate(itertools.zip_longest(left, right, fillvalue=missing), 1):
        assert a is not missing and b is not missing, f'{label}: row count differs at {index}'
        assert len(a) == len(b), f'{label}: column count differs at row {index}'
        if index == 1 and not formats:
            identifiers = {i for i, value in enumerate(a, 1) if str(value).lower() in {'lot_id', 'wafer_id', 'lot', 'wafer', 'product', 'product_id', 'product_name', 'parameter', 'parameter_name', 'name', 'unit', 'units'}}
        for col, (x, y) in enumerate(zip(a, b), 1):
            if formats:
                assert x.number_format == y.number_format, f'{label}: number format differs at {index},{col}'
                x, y = x.value, y.value
            matches = (type(x) is type(y) and x == y) if col in identifiers else equal(x, y)
            assert matches, f'{label}: value differs at row {index}, column {col}: {str(x)[:100]!r} != {str(y)[:100]!r}'
            count += 1
    return count


def compare(left_home, right_home):
    left = {r['title']: r for r in json.loads((left_home/'validation.json').read_text(encoding='utf8'))}
    right = {r['title']: r for r in json.loads((right_home/'validation.json').read_text(encoding='utf8'))}
    assert left.keys() == right.keys(), 'Case sets differ'
    records = []
    for name, a in left.items():
        b = right[name]
        record = {'case': name, 'status': 'PASS', 'tables': 0, 'cells': 0}
        try:
            assert a['status'] == b['status'], f"Task states differ: {a['status']} != {b['status']}"
            if a['status'] == 'SUCCESS':
                for field in ['package_sha256', 'source_files', 'source_bytes', 'record_count', 'business_identity']:
                    # Parent workbooks contain creation timestamps/ZIP metadata.
                    # Their complete table contents are reconciled in the parent case.
                    if field == 'source_bytes' and a.get('parent_id') and b.get('parent_id'):
                        parent_a = next(r['title'] for r in left.values() if r['id'] == a['parent_id'])
                        parent_b = next(r['title'] for r in right.values() if r['id'] == b['parent_id'])
                        assert parent_a == parent_b, 'Parent source case differs'
                        continue
                    assert a['result'].get(field) == b['result'].get(field), f'Result {field} differs'
                aa, bb = tables(left_home, a), tables(right_home, b)
                assert aa.keys() == bb.keys(), f'Table sets differ: {list(aa)} vs {list(bb)}'
                assert aa, 'Success without comparable tables'
                for key, path in aa.items():
                    if path.suffix.lower() == '.csv':
                        with path.open(encoding='utf-8-sig', newline='') as x, bb[key].open(encoding='utf-8-sig', newline='') as y:
                            record['cells'] += compare_rows(csv.reader(x), csv.reader(y), key)
                    else:
                        import openpyxl
                        x = openpyxl.load_workbook(path, read_only=True, data_only=False)
                        y = openpyxl.load_workbook(bb[key], read_only=True, data_only=False)
                        try:
                            assert x.sheetnames == y.sheetnames, f'{key}: sheets differ'
                            for sheet in x.sheetnames:
                                record['cells'] += compare_rows(x[sheet].iter_rows(), y[sheet].iter_rows(), key+'/'+sheet, True)
                        finally:
                            x.close(); y.close()
                    record['tables'] += 1
            else:
                assert a['status'] == 'FAILED', 'Unexpected baseline non-success'
                assert not b.get('result'), 'Failed task exposed result'
        except AssertionError as exc:
            record.update(status='FAIL', error=str(exc))
        records.append(record)
        print(json.dumps(record, ensure_ascii=False), flush=True)
    return records


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--left', type=Path, required=True)
    parser.add_argument('--right', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    rows = compare(args.left, args.right)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf8')
    raise SystemExit(int(any(r['status'] != 'PASS' for r in rows)))
