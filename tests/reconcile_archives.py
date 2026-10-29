"""Compare original report cells, including CSV.GZ inside shared-tool ZIP output."""
import argparse
import csv
import gzip
import io
import json
from pathlib import Path
import sys
import zipfile
import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine_support'))
from scripts.g0.compare_native_results import compare_rows


def load(home):
    rows = json.loads((home / 'validation.json').read_text(encoding='utf8'))
    result = {}
    for row in rows:
        assert row['status'] == 'SUCCESS'
        for item in row['result']['artifacts']:
            path = home / 'tasks' / row['id'] / 'result' / item['path']
            if path.suffix == '.zip':
                with zipfile.ZipFile(path) as archive:
                    for name in archive.namelist():
                        if name.endswith(('.csv.gz', '.csv', '.xlsx')):
                            result[(row['title'], name)] = archive.read(name)
            elif path.suffix == '.xlsx': result[(row['title'], item['path'])] = path.read_bytes()
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for name in ['left', 'right', 'output']: p.add_argument('--'+name, required=True, type=Path)
    a = p.parse_args(); left = load(a.left); right = load(a.right)
    assert left.keys() == right.keys() and left
    cells = 0
    for key, content in left.items():
        if key[1].endswith('.xlsx'):
            x = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
            y = openpyxl.load_workbook(io.BytesIO(right[key]), read_only=True)
            try:
                assert x.sheetnames == y.sheetnames
                for sheet in x.sheetnames:
                    cells += compare_rows(x[sheet].iter_rows(), y[sheet].iter_rows(), str(key)+'/'+sheet, True)
            finally: x.close(); y.close()
        else:
            decode = lambda b: (gzip.decompress(b) if key[1].endswith('.gz') else b).decode('utf-8-sig')
            cells += compare_rows(csv.reader(io.StringIO(decode(content))), csv.reader(io.StringIO(decode(right[key]))), str(key))
    report = dict(status='PASS', tables=len(left), cells=cells)
    a.output.write_text(json.dumps(report, indent=2), encoding='utf8')
    print(report)
