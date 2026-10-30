"""Normalize local HuaHong selections into the original reader's two-level layout.

No measurement parsing or cleaning rules live here. Batch folders and the
original reader's header identities are checked before invoking that reader.
"""
from contextlib import contextmanager, ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil

RAW = {'.txt', '.dcp'}
ARCHIVES = {'.zip', '.7z', '.7zip', '.rar'}


@contextmanager
def prepare_huahong_inputs(sources, temporary_parent, *, identity_scope=None):
    from cp_data_processor.processing.archive_input import prepare_archive_input
    from cp_data_processor.processing.zip_input import _looks_like_hh_batch_name
    from cp_data_processor.readers.dcp_reader import DCPReader
    from clean_dcp_data import extract_lot_id_from_folder_name

    with TemporaryDirectory(prefix='hh-input-', dir=temporary_parent) as temporary, ExitStack() as stack:
        temporary = Path(temporary)
        root = temporary / 'batches'; root.mkdir()
        entries = []
        for source in sources:
            entries.extend(sorted(source.rglob('*'), key=lambda p:str(p).casefold()) if source.is_dir() else [source])
        entries = [p for p in entries if p.is_file() and p.suffix.lower() in RAW | ARCHIVES and not p.name.startswith('~$')]
        if not entries or len(entries)>100_000:
            raise ValueError('未找到华虹DCP/TXT或压缩包，或输入超过100,000项')
        seen_paths, identities, groups = set(), set(), {}
        size = 0
        def add(path, hint=None, *, extracted=False):
            nonlocal size
            if path.is_symlink():raise ValueError('输入文件不能是链接')
            candidates = [hint, *path.parents] if hint else list(path.parents)
            batch = next((p.name for p in candidates if p and _looks_like_hh_batch_name(p.name)), None)
            if not batch:
                raise ValueError('无法确认原始批次文件夹：'+path.name+'；请保留“产品_批次@站号”文件夹，或选择原压缩包')
            _, lot = extract_lot_id_from_folder_name(batch)
            header_lot, wafer = DCPReader([str(path)])._extract_ids_from_r2c2_r2c3(str(path))
            if not header_lot or not wafer or not (header_lot==lot or header_lot.startswith(lot+'-') or header_lot.startswith(lot+'@')):
                raise ValueError('文件头与批次目录不一致，或缺少Lot/Wafer：'+path.name)
            scope = tuple(identity_scope(path, batch)) if identity_scope else ()
            key = (*scope, lot, str(int(wafer)) if wafer.isdigit() else wafer)
            if key in identities:raise ValueError('同一批次与片号重复，请勿同时选择压缩包和已解压副本：'+str(key))
            identities.add(key)
            target_dir = root / batch
            target_dir.mkdir(exist_ok=True)
            target = target_dir / path.name
            if target.exists():raise ValueError('同一批次内输入文件重名：'+path.name)
            size += path.stat().st_size
            if size>8*1024**3 or len(identities)>100_000:raise ValueError('解包数据超过本机上限')
            # Extracted files are private temporary copies. Move them into the
            # checked layout instead of writing and deleting all bytes again.
            if extracted:shutil.move(str(path),str(target))
            else:shutil.copyfile(path,target)
            groups[batch] = target_dir
        for index, entry in enumerate(entries):
            identity = str(entry.resolve()).casefold()
            if identity in seen_paths:raise ValueError('重复选择输入文件：'+entry.name)
            seen_paths.add(identity)
            if entry.suffix.lower() in RAW:
                add(entry)
            else:
                archive = entry
                if entry.suffix.lower()=='.7zip':
                    alias = temporary / ('archive-'+str(index)); alias.mkdir()
                    archive = alias / (entry.stem+'.7z');shutil.copyfile(entry,archive)
                prepared = stack.enter_context(prepare_archive_input(
                    [archive], allowed_suffixes=tuple(RAW), archive_suffixes=('.zip','.7z','.rar'),
                    source_label='华虹DCP/TXT', progress=print, preserve_member_paths=True))
                for path in prepared.data_files:add(path,path.parent,extracted=prepared.is_temporary)
        print(f'递归输入准备完成：{len(groups)} 个批次，{len(identities)} 个晶圆文件',flush=True)
        yield next(iter(groups.values())) if len(groups)==1 else root
