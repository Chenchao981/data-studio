"""CP source adapter; every statistic/report cell is calculated by the FT engine.

The CP readers remain authoritative for identity, measurement and spec decoding.
Only compatible products/parameter schemas may enter one PAT population.
"""
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path


def _number(value):
    if str(value).strip().lower() in {'', 'n/a', 'nan', 'none'}:
        return None
    import math
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('CP规格包含非有限限值')
    return number


def read_specs(path):
    import pandas as pd
    with path.open(encoding='utf-8-sig', newline='') as f:
        header = next(csv.reader(f))
    if len(header) != len(set(header)):
        raise ValueError('CP规格参数重名：'+path.name)
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding='utf-8-sig')
    if 'Parameter' not in frame:
        raise ValueError('CP规格缺少Parameter列：'+path.name)
    matrix = frame['Parameter'].str.strip().str.lower().isin(['unit', 'limitl', 'limitu', 'limit_low', 'limit_high']).any()
    result = {}
    if matrix:
        keys = frame['Parameter'].str.strip().str.lower()
        if keys.duplicated().any():
            raise ValueError('CP规格元数据行重复：'+path.name)
        records = [(name, dict(zip(keys, frame[name]))) for name in frame.columns if name != 'Parameter']
    else:
        records = [(str(row['Parameter']), {str(k).strip().lower(): v for k,v in row.items() if k != 'Parameter'})
                   for row in frame.to_dict('records')]
    for name, metadata in records:
        if name in {'TEST_NUM','SITE_NUM','T_TIME','NUM','Lot_ID','LotID','Wafer_ID','WaferID','Seq','Bin','X','Y'}:
            continue
        if not name or name == 'NO_PARAMETERS' or name in result:
            raise ValueError('CP规格参数缺失或重复：'+path.name)
        unit = str(metadata.get('unit', '')).strip()
        lower = _number(metadata.get('limitl', metadata.get('lsl', metadata.get('limit_low', ''))))
        upper = _number(metadata.get('limitu', metadata.get('usl', metadata.get('limit_high', ''))))
        if lower is not None and upper is not None and lower > upper:
            raise ValueError('CP规格上下限颠倒：'+name)
        # Preserve every condition/extra metadata field in the compatibility gate.
        result[name] = dict(unit=unit, lsl=lower, usl=upper, metadata=metadata)
    if not result:
        raise ValueError('CP规格没有声明可统计参数')
    return result


def generate_cp_ft_pat(factory, intermediate, output):
    import numpy as np
    import pandas as pd
    from local_pat_common import ft_pat_engine
    engine, provenance = ft_pat_engine()
    from shared.excel_utils import write_excel_fast

    cleaned = sorted(intermediate.rglob('*_cleaned_*.csv'))
    specs = sorted(intermediate.rglob('*_spec_*.csv'))
    if not cleaned or not specs:
        raise ValueError('CP原读取器没有生成标准测量数据和规格')
    profiles = [read_specs(path) for path in specs]
    parameters = profiles[0]
    if any(list(p) != list(parameters) or p != parameters for p in profiles[1:]):
        raise ValueError('CP参数、单位、规格或条件不兼容，不能合并PAT')

    lots = set()
    source_rows = 0
    for path in cleaned:
        header = pd.read_csv(path, nrows=0, encoding='utf-8-sig').columns
        identity = [c for c in ('Lot_ID','LotID') if c in header]
        if len(identity) != 1:
            raise ValueError('CP标准数据的Lot字段缺失或有歧义')
        lot_column = identity[0]
        for chunk in pd.read_csv(path, usecols=[lot_column], dtype=str, keep_default_na=False,
                                 encoding='utf-8-sig', chunksize=100000):
            if chunk[lot_column].str.strip().eq('').any():
                raise ValueError('CP数据缺少真实Lot_ID')
            lots.update(chunk[lot_column]); source_rows += len(chunk)
    products = set()
    known_lots = set()
    for path in intermediate.rglob('*_yield_*.csv'):
        frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding='utf-8-sig')
        if {'Lot_ID', 'Product_Name'} <= set(frame.columns):
            selected = frame[frame['Lot_ID'].isin(lots)]
            products.update(v.strip() for v in selected['Product_Name'] if v.strip())
            known_lots.update(selected.loc[selected['Product_Name'].str.strip().ne(''), 'Lot_ID'])
    if len(products) > 1 or (len(lots) > 1 and (len(products) != 1 or known_lots != lots)):
        raise ValueError('多批次PAT缺少一致产品身份，不能合并')

    # FT reports round display values to six decimals. Represent small SI units
    # explicitly in engineering units before calling that same FT function; do
    # not turn e.g. 20 nA into zero by rounding the equivalent 0.00000002 A.
    engineering = {'A': ('nA', 1e9), 'F': ('pF', 1e12), 's': ('ns', 1e9), 'H': ('nH', 1e9)}
    columns = {}
    for name, p in parameters.items():
        display_unit, factor = engineering.get(p['unit'], (p['unit'], 1.0))
        p.update(display_unit=display_unit, display_factor=factor)
        # Some original CP headers already include their physical unit.
        columns[name] = name if display_unit and (name.endswith(f'[{display_unit}]') or name.endswith(f'({display_unit})')) else name + (f' ({display_unit})' if display_unit else '')
    if len(set(columns.values())) != len(columns):
        raise ValueError('CP参数显示名重复')

    def extract(path):
        raw = pd.read_csv(path, encoding='utf-8-sig', usecols=list(parameters))
        values = {}
        for name,p in parameters.items():
            numeric = pd.to_numeric(raw[name], errors='coerce') * p['display_factor']
            if np.isinf(numeric.to_numpy()).any():
                raise ValueError('CP测量值含无穷大：'+name)
            values[columns[name]] = numeric
        return pd.DataFrame(values)

    result = engine.build_spooled_raw_pat(
        [engine.RawPatGroup(factory, tuple(cleaned), extract)],
        spool_dir=output.parent, factory_label=factory)
    if len(result) - 1 != len(parameters):
        raise ValueError('CP参数没有有效测量值，未发布不完整PAT报告')
    for name,p in parameters.items():
        mask = result['统计量'].eq(columns[name])
        for source_key,target in [('lsl','LCL\n更新前'),('usl','UCL\n更新前')]:
            result.loc[mask,target] = None if p[source_key] is None else p[source_key]*p['display_factor']
    report = output/f'PAT_CP_{factory}_{datetime.now():%Y%m%d_%H%M%S}.xlsx'
    if not write_excel_fast(result, report, sheet_name='PAT', index=False) or not report.is_file():
        raise ValueError('FT Excel组件未能保存CP PAT报告')
    files = {}
    for path in [*cleaned, *specs]:
        with path.open('rb') as f:
            files[path.relative_to(intermediate).as_posix()] = hashlib.file_digest(f,'sha256').hexdigest()
    manifest = {**provenance, 'factory':factory, 'record_count':source_rows,
                'parameter_count':len(parameters), 'products':sorted(products), 'lots':sorted(lots),
                'population':'all CP reader measurements; no Bin or IQR filtering',
                'parameters':parameters, 'standard_csv_sha256':files,
                'report':report.name, 'automatic_spec_update':False}
    (output.parent/'PAT_source_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    return {'record_count':source_rows,'parameter_count':len(parameters)}
