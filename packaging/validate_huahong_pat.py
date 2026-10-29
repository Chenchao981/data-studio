"""Independent raw ZIP -> PAT workbook reconciliation; no production adapter imports."""
import argparse
from collections import defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

import numpy as np
import openpyxl


def validate(source, result, manifest_path=None):
    manifest = json.loads((manifest_path or result.parent / 'PAT_source_manifest.json').read_text(encoding='utf8'))
    assert manifest['group_by'] == 'product'
    groups = defaultdict(list)
    profiles = {}
    zip_hashes = {}
    for archive in sorted(source.rglob('*.zip')):
        zip_hashes[str(archive.relative_to(source))] = hashlib.sha256(archive.read_bytes()).hexdigest()
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                if not name.lower().endswith(('.txt', '.dcp')):
                    continue
                raw = z.read(name)
                rows = list(csv.reader(io.StringIO(raw.decode('gb18030')), delimiter='\t'))
                start = next(i for i, row in enumerate(rows) if row and row[0] == 'No.U')
                meta = {r[0]: r[1] for r in rows[:start] if len(r) >= 2}
                station = meta['Lot number'].rsplit('@', 1)[1]
                product, lot_station = archive.stem.split('_', 1)
                lot, name_station = lot_station.rsplit('@', 1)
                assert product.startswith('NCE') and name_station == station
                assert meta['Lot number'].startswith(lot + '-') or meta['Lot number'].startswith(lot + '@')
                key = product
                names = rows[start][4:]
                upper = next(r for r in rows[start+1:] if r and r[0] == 'LimitU')[4:]
                lower = next(r for r in rows[start+1:] if r and r[0] == 'LimitL')[4:]
                data = [r for r in rows[start+1:] if r and r[0].isdigit()]
                values = []
                for row in data:
                    numbers = []
                    for v in row[4:]:
                        try:
                            numbers.append(float(v))
                        except ValueError:
                            numbers.append(float('nan'))
                    values.append(numbers)
                groups[key].append(np.asarray(values))
                profiles.setdefault(key, {'files': [], 'names': names, 'upper': upper, 'lower': lower,
                                          'lots': set(), 'stations': set(), 'programs': set()})
                p = profiles[key]
                assert (names, upper, lower) == (p['names'], p['upper'], p['lower'])
                p['files'].append((Path(name).name, hashlib.sha256(raw).hexdigest(), len(data)))
                p['lots'].add(lot); p['stations'].add(station); p['programs'].add(meta['Program name'])
    checked = []
    assert len(manifest['groups']) == len(groups)
    exported = {p.relative_to(result).as_posix() for p in result.rglob('*') if p.is_file()}
    assert exported == {g['report'] for g in manifest['groups']}
    assert all(Path(name).suffix == '.xlsx' for name in exported)
    for group in manifest['groups']:
        key = group['product']
        p = profiles[key]
        assert group['lots'] == sorted(p['lots'])
        assert group['stations'] == sorted(p['stations'])
        assert group['programs'] == sorted(p['programs'])
        assert sorted((s['file'], s['sha256'], s['rows']) for s in group['sources']) == sorted(p['files'])
        data = np.concatenate(groups[key])
        assert data.shape == (group['record_count'], group['parameter_count'])
        workbook = openpyxl.load_workbook(result / group['report'], data_only=True)
        assert workbook.sheetnames == ['PAT']
        rows = list(workbook.active.values)
        assert len(rows) == len(p['names']) + 2 and len(rows[0]) == 17 and rows[1][0] == '变量'
        for index, row in enumerate(rows[2:]):
            # This real source family declares V and nA; do not guess new units.
            upper = re.fullmatch(r'([-+\d.eE]+)(V|nA)', p['upper'][index])
            lower = re.fullmatch(r'([-+\d.eE]+)(V|nA)', p['lower'][index])
            assert upper and lower and upper[2] == lower[2]
            unit = upper[2]
            values = data[:, index]
            values = values[~np.isnan(values)] / (1e-9 if unit == 'nA' else 1)
            q1, median, q3 = np.quantile(values, [.25, .5, .75], method='linear')
            sigma = (q3-q1)/1.35
            expected = [len(values), values.mean(), values.std(ddof=1), values.min(), q1,
                        median, q3, values.max(), sigma, median-6*sigma, median+6*sigma]
            assert row[0] == p['names'][index] + ' (' + unit + ')'
            for actual, value in zip(row[1:12], expected):
                assert np.isclose(actual, round(float(value), 6), rtol=0, atol=1e-6), (key, row[0], actual, value)
            assert row[12:14] == (float(lower[1]), float(upper[1]))
            assert row[14:] == (None, None, None)
        workbook.close()
        checked.append({'product': key, 'lots': len(p['lots']), 'stations': group['stations'], 'files': len(p['files']),
                        'rows': len(data), 'parameters': data.shape[1], 'verified_numeric_cells': data.shape[1]*13})
    assert all(hashlib.sha256((source / name).read_bytes()).hexdigest() == digest for name, digest in zip_hashes.items())
    return {'status': 'PASS', 'archives': len(zip_hashes), 'groups': checked, 'source_archive_sha256': zip_hashes}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('result', type=Path)
    parser.add_argument('receipt', type=Path)
    parser.add_argument('--manifest', type=Path, help='Internal task provenance; never published beside Excel')
    args = parser.parse_args()
    receipt = validate(args.source, args.result, args.manifest)
    args.receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps({k: v for k, v in receipt.items() if k != 'source_archive_sha256'}, ensure_ascii=False))
