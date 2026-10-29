"""Bounded reads of a registered task's own execution log."""
from __future__ import annotations

import codecs
from pathlib import Path

CHUNK = 64 * 1024


def read_task_log(core, task_id, source="", offset=0):
    task = core.task(task_id)
    if not isinstance(source, str) or len(source) > 240:
        raise ValueError("无效日志来源")
    if type(offset) is not int or offset < 0:
        raise ValueError("无效日志位置")
    base = core.results.resolve()
    root = (base / task['id']).resolve()
    if root == base or not root.is_relative_to(base):
        raise ValueError("日志不属于本地任务")

    def checked(path):
        resolved = path.resolve()
        if not resolved.is_relative_to(root):
            raise ValueError("日志不能指向任务以外的位置")
        return resolved

    # The native controller writes the cleaner's live stdout/stderr here.
    # Do not recursively scan inputs/results, or accept a path supplied by JS.
    directory = checked(root / 'engine-work' / 'tasks')
    candidates = []
    if directory.is_dir():
        for child in directory.iterdir():
            path = checked(child / 'execution.log')
            if path.is_file():
                candidates.append(path)
            if len(candidates) > 1:
                raise ValueError("任务日志来源不唯一")
    path = candidates[0] if candidates else checked(root / 'execution.log')
    key = path.relative_to(root).as_posix()
    response = dict(source=key, offset=0, text='', reset=source != key,
                    truncated=False, more=False, status=task['status'])
    if not path.is_file():
        return response
    with path.open('rb') as stream:
        size = stream.seek(0, 2)
        reset = source != key or offset > size
        start = max(0, size - CHUNK) if reset else offset
        stream.seek(start)
        data = stream.read(CHUNK)
        decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        text = decoder.decode(data, final=task['status'] in {'SUCCESS', 'FAILED', 'CANCELLED'} and start + len(data) >= size)
        consumed = len(data) - len(decoder.getstate()[0])
        if reset and start:
            text = text.partition('\n')[2] if '\n' in text else text
        response.update(offset=start + consumed, text=text, reset=reset,
                        truncated=reset and start > 0, more=start + len(data) < size)
    return response
