# Synced archive transport from cp_data_ansys; no raw-format parsing is performed here.
"""Read RAR members through installed 7-Zip, without restoring archive paths."""

from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryFile


class RarInputError(ValueError):
    pass


def find_7zip() -> str:
    candidates = [shutil.which(name) for name in ("7z", "7zz")]
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        root = os.environ.get(variable)
        if root:
            candidates.append(str(Path(root) / "7-Zip" / "7z.exe"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise RarInputError("读取RAR需要安装7-Zip（标准安装目录或PATH），安装后重新启动程序")


@dataclass(frozen=True)
class RarMember:
    filename: str
    size: int
    directory: bool


class RarArchive:
    def __init__(self, path: Path):
        self.path = path.resolve()
        with self.path.open("rb") as source:
            signature = source.read(8)
        if not (signature.startswith(b"Rar!\x1a\x07\x00") or signature == b"Rar!\x1a\x07\x01\x00"):
            raise RarInputError(f"RAR文件签名无效: {path.name}")
        self.executable = find_7zip()
        self.process_options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}

    def members(self) -> list[RarMember]:
        result = subprocess.run(
            [self.executable, "l", "-slt", "-ba", "-sccUTF-8", "-p-", "--", str(self.path)],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=120,
            **self.process_options,
        )
        if result.returncode != 0:
            raise RarInputError(f"无法读取RAR目录（损坏、加密或分卷缺失）: {self.path.name}")
        members = []
        seen = set()
        listing = result.stdout.decode("utf-8", errors="strict").replace("\r\n", "\n")
        for block in listing.strip().split("\n\n"):
            fields = dict(line.split(" = ", 1) for line in block.splitlines() if " = " in line)
            name = fields.get("Path")
            if not name:
                continue
            if fields.get("Encrypted") == "+":
                raise RarInputError(f"RAR已加密，无法读取: {self.path.name}")
            if fields.get("Symbolic Link") or fields.get("Hard Link"):
                raise RarInputError(f"RAR包含链接，无法读取: {name}")
            key = name.replace("\\", "/").casefold()
            if key in seen:
                raise RarInputError(f"RAR包含重复路径: {name}")
            seen.add(key)
            size = int(fields.get("Size", "0"))
            if size < 0:
                raise RarInputError(f"RAR成员大小无效: {name}")
            members.append(RarMember(name, size, fields.get("Folder") == "+"))
        return members

    @contextmanager
    def open(self, member: RarMember):
        # e -so emits only bytes. Archive names never become filesystem paths.
        with TemporaryFile() as errors:
            process = subprocess.Popen(
                [self.executable, "e", "-so", "-y", "-spd", "-p-", "-sccUTF-8",
                 "-i!" + member.filename, "--", str(self.path)],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=errors,
                **self.process_options,
            )
            try:
                with process.stdout as stream:
                    yield stream
                if process.wait(timeout=120) != 0:
                    raise RarInputError(f"RAR成员解压或CRC校验失败: {self.path.name} / {member.filename}")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
