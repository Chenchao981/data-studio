"""Per-workspace path preferences in the current Windows user's local history."""
import os
from pathlib import Path


def desktop_directory():
    # Windows known folders also cover OneDrive and redirected desktops.
    if os.name == 'nt':
        import ctypes,uuid
        folder=ctypes.create_string_buffer(uuid.UUID('B4BFCC3A-DB2C-424C-B029-7FE99A87C641').bytes_le)
        value=ctypes.c_wchar_p()
        try:
            if ctypes.windll.shell32.SHGetKnownFolderPath(folder,0,None,ctypes.byref(value)) == 0:
                if value.value and Path(value.value).is_dir():return str(Path(value.value).resolve())
        finally:
            if value:ctypes.windll.ole32.CoTaskMemFree(value)
    path=Path.home()/'Desktop'
    return str(path if path.is_dir() else Path.home())


def local_path(value):
    if not isinstance(value,str) or not value.strip():raise ValueError('请选择本机路径')
    value=value.strip().strip('"')
    if value.startswith(('\\\\','//')) or not Path(value).is_absolute():raise ValueError('请选择本机绝对路径')
    return Path(value).resolve(strict=True)


def output_parent(value,workspace,sources=()):
    path=local_path(value)
    if not path.is_dir():raise ValueError('输出位置必须是文件夹')
    if path.is_relative_to(Path(workspace).resolve()):raise ValueError('输出目录不能位于内部历史工作区')
    for source in sources:
        source=Path(source).resolve()
        if source.is_dir() and path.is_relative_to(source):
            raise ValueError('输出目录不能位于输入文件夹内，请选择桌面或另一个目录')
    return path
