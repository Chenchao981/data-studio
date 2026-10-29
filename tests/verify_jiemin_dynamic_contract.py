"""Validate the released FT package against the original synthetic fixtures.

Run separately: legacy factories use process-global module names. This checks
the documented dynamic schema and failure cleanup without changing old tests
or relaxing parser validation. No business data is stored by this script.
"""
import argparse
import json
from pathlib import Path
import runpy
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.package.resolve()))
    fixture = runpy.run_path(str(args.fixtures))
    make_source, change = fixture['make_source'], fixture['change_cell']
    from factories.jiemin.parser import parse_jiemin_file, JieminFormatError
    from factories.jiemin.pat_cleaner import generate_raw_pat, build_raw_pat
    import factories.jiemin.parser as module
    assert str(args.package.resolve()) in module.__file__
    results = []
    with tempfile.TemporaryDirectory(prefix='studio-dynamic-contract-') as directory:
        root = Path(directory)
        for index, (label, value, expected) in enumerate([
            ('Item Name', '7 IDSS_NEW', 'IDSS_NEW'),
            ('Bias1', 'VDS=50.00V', 'IDSS50'),
            ('Max Limit', '200 uA', 'IDSS60_1(uA)'),
        ]):
            source = make_source(root / str(index))
            change(source, label, 9, value)
            parsed = parse_jiemin_file(source)
            columns = [c for c in parsed.data if expected in c]
            assert len(columns) == 1, (expected, columns)
            assert len(parsed.data) == 3
            assert parsed.data.loc[0, columns[0]] == 7.125
            results.append({'case': label + ':' + value, 'status': 'PASS'})
        for index, (label, value) in enumerate([
            ('Min Limit', '0 V'), ('Max Limit', 'garbage')
        ]):
            source = make_source(root / ('bad' + str(index)))
            change(source, label, 9, value)
            try:
                parse_jiemin_file(source)
            except JieminFormatError:
                results.append({'case': 'reject ' + label + ':' + value, 'status': 'PASS'})
            else:
                raise AssertionError('Invalid specification accepted: ' + value)
        raw = root / 'pat'
        make_source(raw)
        second = make_source(raw, 'NCEG50000002')
        change(second, 'Bias1', 9, 'VDS=59.00V')
        pat = build_raw_pat(raw).iloc[1:].set_index('统计量')
        assert len(pat) == 36
        assert pat.loc['IDSS59(nA)', '总计数'] == 2
        assert pat.loc['IDSS60_1(nA)', '总计数'] == 4
        assert pat.loc['IDSS60_2(nA)', '总计数'] == 2
        results.append({'case': 'distinct conditions remain separate in PAT', 'status': 'PASS'})
        change(second, 'Max Limit', 9, 'garbage')
        try:
            generate_raw_pat(raw, root / 'out')
        except JieminFormatError:
            assert not list((root / 'out').iterdir())
            results.append({'case': 'invalid source leaves no partial PAT', 'status': 'PASS'})
        else:
            raise AssertionError('Invalid PAT source accepted')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2), encoding='utf8')
    print(f'PASS: {len(results)} dynamic-schema and fail-closed checks')


if __name__ == '__main__':
    main()
