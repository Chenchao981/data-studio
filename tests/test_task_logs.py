from types import SimpleNamespace

import pytest

from python_core.task_logs import CHUNK, read_task_log


@pytest.fixture
def logs(tmp_path):
    root = tmp_path / 'results' / 'job'
    root.mkdir(parents=True)
    task = {'id': 'job', 'status': 'RUNNING'}
    def lookup(task_id):
        if task_id != 'job':
            raise ValueError('任务不存在')
        return task
    return SimpleNamespace(results=root.parent, task=lookup), root, task


def test_incremental_unicode_and_native_log_switch(logs):
    core, root, task = logs
    (root / 'execution.log').write_bytes('开始校验\n'.encode('utf8'))
    first = read_task_log(core, 'job')
    assert first['text'] == '开始校验\n'
    native = root / 'engine-work/tasks/native/execution.log'
    native.parent.mkdir(parents=True)
    # A UTF-8 character split across writes must not become replacement characters.
    raw = '正在解析文件\n'.encode()
    native.write_bytes(raw[:2])
    second = read_task_log(core, 'job', first['source'], first['offset'])
    assert second['reset'] and not second['text'] and second['offset'] == 0
    with native.open('ab') as stream:
        stream.write(raw[2:])
    third = read_task_log(core, 'job', second['source'], second['offset'])
    assert third['text'] == raw.decode() and not third['reset']
    task['status'] = 'SUCCESS'
    final = read_task_log(core, 'job', third['source'], third['offset'])
    assert final['text'] == '' and final['status'] == 'SUCCESS'


def test_tail_limits_rotation_and_task_ownership(logs):
    core, root, task = logs
    path = root / 'execution.log'
    path.write_bytes(b'line\n' * 100000)
    result = read_task_log(core, 'job', '../../unrelated.log', 0)
    assert result['truncated'] and len(result['text']) <= CHUNK
    assert result['offset'] == path.stat().st_size
    path.write_bytes(b'new\n')
    result = read_task_log(core, 'job', result['source'], result['offset'])
    assert result['reset'] and result['text'] == 'new\n'
    with pytest.raises(ValueError):
        read_task_log(core, '../other')
    for invalid in (-1, '4', True):
        with pytest.raises(ValueError):
            read_task_log(core, 'job', offset=invalid)


def test_missing_log_and_terminal_utf8(logs):
    core, root, task = logs
    assert read_task_log(core, 'job')['text'] == ''
    (root / 'execution.log').write_bytes(b'error\n\xe4')
    task['status'] = 'FAILED'
    assert read_task_log(core, 'job')['text'] == 'error\n\ufffd'


def test_log_symlink_cannot_read_outside_task(logs, tmp_path):
    core, root, task = logs
    external = tmp_path / 'private.txt'
    external.write_text('secret')
    try:
        (root / 'execution.log').symlink_to(external)
    except OSError:
        pytest.skip('Windows symlink permission unavailable')
    with pytest.raises(ValueError, match='任务以外'):
        read_task_log(core, 'job')
