"""HuaHong DCP adapter to the pinned FT raw-PAT statistics/report engine.

Runs in the isolated native worker. Raw values are never IQR-cleaned or
filtered by Bin. Per the product report contract, compatible batches and
test stations/programs of one product contribute to one PAT population.
"""
from collections import defaultdict
from datetime import datetime
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sys


def parse_batch_name(batch):
    """NCE product precedes _, complete batch lies between _ and @."""
    match = re.fullmatch(r'(NCE[A-Za-z0-9.-]+)_([^@\s]+)@([^@\s]+)', batch)
    if not match:
        raise ValueError('批次名称应为“NCE产品_批次@站号”：' + batch)
    return match.groups()


def profile(path, batch):
    from cp_unit_converter import UnitConverter

    raw = path.read_bytes()
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('gb18030')
    rows = [line.split('\t') for line in text.splitlines() if line.strip()]
    header = next((i for i, row in enumerate(rows) if row[0].strip().upper() == 'NO.U'), None)
    if header is None:
        raise ValueError('不是受支持的华虹DCP数据（缺少No.U）：' + path.name)
    names = [v.strip() for v in rows[header]]
    if names[:4] != ['No.U', 'X', 'Y', 'Bin'] or len(names) <= 4 or len(set(names)) != len(names):
        raise ValueError('DCP参数表头重复或布局不明确：' + path.name)
    meta = {row[0].strip(): row[1].strip() for row in rows[:header] if len(row) >= 2}
    product, lot, station = parse_batch_name(batch)
    if not meta.get('Program name') or not meta.get('Lot number', '').endswith('@' + station):
        raise ValueError('测试程序或站号与批次文件夹不一致：' + path.name)
    body = rows[header + 1:]
    spec = [row for row in body if not re.fullmatch(r'\d+', row[0].strip())]
    data = [row for row in body if re.fullmatch(r'\d+', row[0].strip())]
    if not data or any(len(row) != len(names) for row in data):
        raise ValueError('DCP数据为空或列数不一致：' + path.name)
    allowed = {'LimitU', 'LimitL', *(f'Bias {i}' for i in range(1, 7))}
    if any(row[0].strip() not in allowed or len(row) != len(names) for row in spec):
        raise ValueError('DCP规格/条件行无法识别：' + path.name)
    spec_map = {row[0].strip(): [v.strip() for v in row] for row in spec}
    if len(spec_map) != len(spec) or not {'LimitU', 'LimitL'} <= spec_map.keys():
        raise ValueError('DCP规格缺失或重复：' + path.name)
    converter = UnitConverter()
    parameters = []
    for index, name in enumerate(names[4:], start=4):
        lo, lo_unit = converter.extract_value_and_unit(spec_map['LimitL'][index])
        hi, unit = converter.extract_value_and_unit(spec_map['LimitU'][index])
        supported = {'V', 'A', 'ohm', 'Ohm', 'Hz', 'F', 's', 'H'}
        if lo is None or hi is None or converter.get_base_unit(unit) not in supported or converter.get_base_unit(lo_unit) != converter.get_base_unit(unit):
            raise ValueError(f'参数 {name} 的规格/单位不明确：{path.name}')
        scale = converter.get_unit_order_change_rate(unit)
        lo = lo * converter.get_unit_order_change_rate(lo_unit) / scale
        if lo > hi:
            raise ValueError(f'参数 {name} 的规格上下限颠倒：{path.name}')
        parameters.append({'name': name, 'unit': unit, 'scale': scale, 'lsl': lo, 'usl': hi,
                           'conditions': [spec_map[k][index] for k in sorted(spec_map) if k.startswith('Bias ')]})
    return {'product': product, 'lot': lot, 'station': station, 'program': meta['Program name'],
            'source_lot': meta.get('Lot number'), 'wafer': meta.get('Wafer number'),
            'date': meta.get('Date'), 'time': meta.get('Time'), 'rows': len(data),
            'parameters': parameters, 'sha256': hashlib.sha256(raw).hexdigest(), 'file': path.name}


def generate_huahong_pat(sources, output):
    from local_cp_input import prepare_huahong_inputs
    from cp_data_processor.readers.dcp_reader import DCPReader
    import numpy as np
    import pandas as pd

    package = Path(os.environ['STUDIO_FT_PAT_PACKAGE'])
    if hashlib.sha256(package.read_bytes()).hexdigest() != os.environ['STUDIO_FT_PAT_SHA256']:
        raise ValueError('FT PAT计算包校验失败')
    sys.path.insert(0, str(package))
    from shared.pat_engine import RawPatGroup, build_spooled_raw_pat
    from shared.excel_utils import write_excel_fast

    manifest = {'formula': 'FT_MEDIAN_IQR_6SIGMA_V1', 'sigma_divisor': 1.35, 'sigma_multiplier': 6,
                'quartiles': 'pandas linear', 'population': 'all raw measurement rows, no Bin or IQR filtering',
                'display_units': 'source specification units; raw SI values divided by unit scale',
                'ft_package_sha256': os.environ['STUDIO_FT_PAT_SHA256'],
                'group_by': 'product', 'groups': []}
    # Existing cleaning keeps its stricter lot/wafer uniqueness rule. Only PAT
    # includes distinct station/program measurements in the product population,
    # but still rejects duplicated inputs from the same acquisition scope.
    def scope(path, batch):
        p = profile(path, batch)
        return p['product'], p['station'], p['program']

    logging.getLogger('cp_data_processor.readers.dcp_reader').setLevel(logging.WARNING)
    total_rows = total_parameters = 0
    with prepare_huahong_inputs(sources, output.parent, identity_scope=scope) as prepared:
        groups = defaultdict(list)
        profiles = {}
        for path in sorted(p for p in prepared.rglob('*') if p.is_file() and p.suffix.lower() in {'.txt', '.dcp'}):
            p = profile(path, path.parent.name)
            profiles[path] = p
            groups[p['product']].append(path)
        if not groups:
            raise ValueError('没有可计算PAT的DCP/TXT数据')
        print(f'华虹原始PAT：按产品汇总，{len(groups)} 个产品，每个产品输出一个Excel', flush=True)
        for product, paths in sorted(groups.items()):
            params = profiles[paths[0]]['parameters']
            if any(profiles[p]['parameters'] != params for p in paths):
                raise ValueError(f'同一产品存在不同规格、单位或测试条件，不能合并PAT：{product}')

            def extract(path):
                lot = DCPReader([str(path)]).read()
                if len(lot.wafers) != 1 or len(lot.wafers[0].chip_data) != profiles[path]['rows']:
                    raise ValueError('原CP读取器解析行数与源文件不符：' + path.name)
                raw_frame = lot.wafers[0].chip_data
                if [p.id for p in lot.params if p.id != 'No.U'] != [p['name'] for p in params]:
                    raise ValueError('原CP读取器参数与源文件不符：' + path.name)
                frame = pd.DataFrame({f"{p['name']} ({p['unit']})": raw_frame[p['name']] / p['scale'] for p in params})
                if np.isinf(frame.to_numpy()).any():
                    raise ValueError('原始测量值含无穷大：' + path.name)
                return frame

            frame = build_spooled_raw_pat([RawPatGroup(product, tuple(paths), extract)],
                                         spool_dir=output.parent, factory_label='华虹 ' + product)
            if len(frame) - 1 != len(params):
                raise ValueError('存在无有效数值的参数，PAT报告未发布：' + product)
            for p in params:
                mask = frame['统计量'] == f"{p['name']} ({p['unit']})"
                frame.loc[mask, 'LCL\n更新前'] = p['lsl']
                frame.loc[mask, 'UCL\n更新前'] = p['usl']
            report = output / (product + '_PAT_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.xlsx')
            if report.exists():
                raise ValueError('产品报告文件名冲突：' + report.name)
            if not write_excel_fast(frame, report, sheet_name='PAT', index=False) or not report.is_file():
                raise ValueError('FT Excel组件未能保存PAT报告')
            rows = sum(profiles[p]['rows'] for p in paths)
            manifest['groups'].append({'product': product,
                'stations': sorted({profiles[p]['station'] for p in paths}),
                'programs': sorted({profiles[p]['program'] for p in paths}),
                'lots': sorted({profiles[p]['lot'] for p in paths}),
                'report': report.relative_to(output).as_posix(), 'record_count': rows,
                'parameter_count': len(params), 'sources': [profiles[p] for p in paths]})
            total_rows += rows
            total_parameters += len(params)
            print(f'已保存：{report.name}；{product}，{len(paths)}个晶圆文件，{rows:,}行，{len(params)}参数', flush=True)
    # Audit metadata belongs to internal task history, outside published files/.
    (output.parent / 'PAT_source_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'record_count': total_rows, 'parameter_count': total_parameters}
