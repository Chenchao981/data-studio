import json
from pathlib import Path
import time

import pytest

from python_core.core import Core


def test_pasted_inputs_normalize_quotes_deduplicate_and_fail_atomically(tmp_path):
    core = Core(tmp_path / 'home')
    folder = tmp_path / '中文 空格'; folder.mkdir()
    first = folder / 'first.txt'; first.write_text('original')
    second = folder / 'second.txt'; second.write_text('original2')
    rows = core.apply_input_paths(f' "{first}"\r\n\n{second}\n{first}')
    assert [r['path'] for r in rows] == [str(first), str(second)]
    assert core.settings()['inputDirectory'] == str(folder)
    before = core.settings()
    for text in [f'{folder}\n{tmp_path / "missing"}', 'relative.txt', r'\\server\share\file.txt', None, ['x'], 'x' * 64001, '\n'.join([str(first)] * 101)]:
        with pytest.raises(ValueError):
            core.apply_input_paths(text)
        assert core.settings() == before
    rows = core.apply_input_paths(str(folder))
    assert len(rows) == 1 and rows[0]['folder']
    assert core.apply_input_paths(' \n ') == []
    assert not core.workspace_files()
    assert first.read_text() == 'original' and second.read_text() == 'original2'
    assert core.registered_sources([r['id'] for r in rows])


def test_pasted_output_is_persistent_and_invalid_edits_preserve_default(tmp_path):
    core = Core(tmp_path / 'home')
    output = tmp_path / '输出 空格'; output.mkdir()
    assert core.apply_output_path(f' "{output}" ') == str(output)
    assert Core(core.root).settings()['outputDirectory'] == str(output)
    file = tmp_path / 'file.txt'; file.write_text('source')
    for text in ['', None, 'relative', r'\\server\share', str(file), str(core.root), str(tmp_path / 'missing'), f'{output}\n{output}']:
        with pytest.raises((ValueError, OSError)):
            core.apply_output_path(text)
        assert core.settings()['outputDirectory'] == str(output)


def test_typed_path_bridge_remains_trusted_and_registers_ids(tmp_path):
    from PySide6.QtCore import QCoreApplication
    from apps.desktop.bridge import Bridge
    from python_core.tasks import TaskManager
    app = QCoreApplication.instance() or QCoreApplication([])
    core = Core(tmp_path / 'home'); manager = TaskManager(core)
    bridge = Bridge(core, manager, None, lambda: False)
    replies = {}
    bridge.response.connect(lambda rid, raw: replies.update({rid: json.loads(raw)}))
    source = tmp_path / 'raw.txt'; source.write_text('original')
    output = tmp_path / 'out'; output.mkdir()
    try:
        for method in ['applyInputPaths', 'applyOutputPath']:
            bridge.request(method, method, json.dumps({'text': str(source)}))
            assert not replies[method]['ok'] and '可信' in replies[method]['error']
        assert not core.workspace_files()
        bridge.trusted = lambda: True
        for rid, method, text in [('input', 'applyInputPaths', str(source)), ('output', 'applyOutputPath', str(output))]:
            bridge.request(rid, method, json.dumps({'text': text}))
            end = time.monotonic() + 5
            while rid not in replies and time.monotonic() < end:
                app.processEvents(); time.sleep(.01)
            assert replies[rid]['ok'], replies.get(rid)
        assert replies['input']['value'][0]['id'] == core.workspace_files()[0]['id']
        assert core.settings()['outputDirectory'] == str(output)
    finally:
        bridge.close(); manager.close()
