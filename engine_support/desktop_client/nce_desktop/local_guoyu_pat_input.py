"""PAT-only source correction for the approved Guoyu JUNO profile.

Reuse the pinned reader's values/counts/Bin checks; locate source spec labels
instead of its historical off-by-one row offsets. LotName is authoritative.
"""
from pathlib import Path
import re
from contextlib import contextmanager
from tempfile import TemporaryDirectory
import shutil


@contextmanager
def _source_paths(sources, output):
    # The pinned archive helper accepts directories/archives. Wrap explicitly
    # selected Excel files without exposing their unselected sibling files.
    with TemporaryDirectory(prefix='guoyu-pat-input-',dir=output.parent) as temp:
        paths=[]
        for i,source in enumerate(sources):
            if source.is_file() and source.suffix.lower() in {'.xls','.xlsx'}:
                folder=Path(temp)/str(i);folder.mkdir();shutil.copy2(source,folder/source.name);paths.append(folder)
            else:
                paths.append(source)
        yield paths


def prepare_guoyu_pat(sources, output):
    import numpy as np
    import pandas as pd
    from cp_data_processor.processing.archive_input import prepare_archive_input
    from guoyu.guoyu_reader import GuoyuFRDReader, PARAMETER_NAMES, PARAMETER_UNITS, parse_engineering_value

    class PatReader(GuoyuFRDReader):
        def _extract_spec(self, raw, header_row):
            expected = ('CONT2','IR','VZ1','VZ2','DELTA','VF','IR')
            for offset,name in enumerate(expected, start=4):
                text = str(raw.iloc[header_row,offset]).strip()
                if re.sub(r'^\d+\s+', '', text).upper() != name:
                    raise ValueError('国宇PAT参数表头与已核验JUNO合同不一致')
            labels = raw.iloc[:header_row,0].fillna('').astype(str).str.strip().str.casefold()
            def row(label, required=True):
                matches = labels.index[labels.eq(label.casefold())]
                if len(matches) != 1:
                    if not required and len(matches)==0:
                        return None
                    raise ValueError('国宇规格/条件标签缺失或重复：'+label)
                return int(matches[0])
            lo,hi = row('Min Limit'),row('Max Limit')
            biases = [row(label,False) for label in ('Bias1','Bias2','Bias3')]
            spec = {}
            for offset,name in enumerate(PARAMETER_NAMES,start=4):
                unit = PARAMETER_UNITS[name]
                actual = str(raw.iloc[header_row+1,offset]).strip()
                if actual != unit and not (name=='DELTA[V]' and (not actual or actual=='nan')):
                    raise ValueError('国宇PAT测量单位与已核验合同不一致：'+name)
                def limit(index):
                    value = raw.iloc[index,offset]
                    number = parse_engineering_value(value,unit)
                    if not pd.isna(value) and str(value).strip() and not np.isfinite(number):
                        raise ValueError('国宇规格值无法解释：'+name)
                    return number
                spec[name] = {'Unit':unit,'LimitL':limit(lo),'LimitU':limit(hi),
                    'TestCond':'; '.join(str(raw.iloc[i,offset]).strip() for i in biases
                                         if i is not None and pd.notna(raw.iloc[i,offset]))}
            return pd.DataFrame(spec)

    with _source_paths(sources,output) as paths, prepare_archive_input(paths, allowed_suffixes=('.xls','.xlsx'), archive_suffixes=('.zip',),
                               preserve_member_paths=True, source_label='GUOYU PAT', progress=print) as prepared:
        seen = set()
        for i,path in enumerate(prepared.data_files):
            lot = PatReader([str(path)]).read()
            if not lot.lot_id or str(lot.lot_id).lower()=='nan':
                raise ValueError('国宇PAT缺少源文件LotName')
            wafer = lot.wafers[0]
            key = (lot.lot_id,str(wafer.wafer_id))
            if key in seen:
                raise ValueError('国宇同一批次与片号重复，不能重复计算PAT')
            seen.add(key)
            prefix = f'source_{i:05d}'
            lot.combined_data.to_csv(output/(prefix+'_cleaned_1.csv'),index=False,encoding='utf-8-sig')
            wafer.spec_data.rename_axis('Parameter').reset_index().to_csv(output/(prefix+'_spec_1.csv'),index=False,encoding='utf-8-sig')
            # The raw DeviceName is a test device/program number, not an inferred
            # product. Unknown product remains unknown; cross-lot pooling stops.
            pd.DataFrame([{'Lot_ID':lot.lot_id,'Product_Name':''}]).to_csv(output/(prefix+'_yield_1.csv'),index=False,encoding='utf-8-sig')
