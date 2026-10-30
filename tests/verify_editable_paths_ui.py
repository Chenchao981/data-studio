"""Real Ctrl+V and editable-path workflow in an isolated Qt workspace."""
import argparse
import json
import multiprocessing
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cp', type=Path, required=True)
    parser.add_argument('--ft', type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve(); root.mkdir(parents=True, exist_ok=False)
    from apps.desktop.rendering import configure_rendering
    configure_rendering('software')
    from PySide6.QtCore import QMimeData, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QMessageBox
    from apps.desktop.security import register_scheme
    register_scheme(); app = QApplication([])
    from apps.desktop.shell import StudioWindow
    window = StudioWindow(root / 'home', ROOT / 'apps/web/dist')
    window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    window.resize(1440, 960); window.show()
    saved_clipboard = QMimeData()
    previous = app.clipboard().mimeData()
    if previous:
        for fmt in previous.formats(): saved_clipboard.setData(fmt, previous.data(fmt))

    def wait(check, timeout=40):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            app.processEvents()
            if check(): return
            time.sleep(.01)
        raise AssertionError('Editable paths UI timeout')

    def js(code):
        values = []; window.page.runJavaScript(code, values.append)
        wait(lambda: bool(values)); return values[0]

    def click(text):
        wait(lambda: js('(()=>{const b=[...document.querySelectorAll("button")].find(e=>e.textContent.trim()===' + json.dumps(text) + ');if(!b||b.disabled)return false;b.click();return true})()'))

    def paste(selector, text):
        wait(lambda: js('!document.querySelector(' + json.dumps(selector) + ').disabled'))
        app.clipboard().setText(text)
        js('(()=>{const e=document.querySelector(' + json.dumps(selector) + ');e.focus();e.select()})()')
        wait(lambda: js('document.activeElement===document.querySelector(' + json.dumps(selector) + ')'))
        QTest.keyClick(window.view.focusProxy(), Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
        wait(lambda: js('document.querySelector(' + json.dumps(selector) + ').value') == text)

    def shot(name):
        until = time.monotonic() + .3
        while time.monotonic() < until: app.processEvents(); time.sleep(.01)
        window.grab().save(str(root / name))

    def edit(selector, text):
        # Clipboard shortcuts are checked above. Drive subsequent stage edits
        # without depending on native focus in an inactive validation window.
        wait(lambda: js('!document.querySelector(' + json.dumps(selector) + ').disabled'))
        js('(()=>{const e=document.querySelector(' + json.dumps(selector) + ');Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,"value").set.call(e,' + json.dumps(text) + ');e.dispatchEvent(new Event("input",{bubbles:true}));})()')
        wait(lambda: js('document.querySelector(' + json.dumps(selector) + ').value') == text)

    try:
        wait(lambda: js('!!document.querySelector("#input-paths")'))
        assert js('!document.querySelector("#input-paths").readOnly&&!document.querySelector("#output-directory").readOnly')
        output = root / '用户粘贴 输出'; output.mkdir()
        paste('#output-directory', str(output))
        QTest.keyClick(window.view.focusProxy(), Qt.Key.Key_Return)
        wait(lambda: window.core.settings()['outputDirectory'] == str(output))
        fixture = root / '输入 空格'; fixture.mkdir()
        file = fixture / 'path.txt'; file.write_text('unchanged')
        paste('#input-paths', f'"{file}"\n{fixture}\n{file}')
        click('应用输入路径')
        wait(lambda: len(window.core.workspace_files()) == 2)
        wait(lambda: js('![...document.querySelectorAll("button")].some(b=>b.textContent==="应用输入路径")'))
        assert not js('document.querySelector(".check-label input").checked')
        old_ids = [f['id'] for f in window.core.workspace_files()]
        paste('#input-paths', str(root / 'missing.txt'))
        click('应用输入路径'); wait(lambda: js('!!document.querySelector("#input-paths[aria-invalid=true]")'))
        assert [f['id'] for f in window.core.workspace_files()] == old_ids
        wait(lambda: js('[...document.querySelectorAll("button")].find(b=>b.textContent.trim()==="清洗").disabled'))
        shot('invalid-input.png'); click('取消修改')
        paste('#output-directory', str(file)); click('应用输出路径')
        wait(lambda: js('!!document.querySelector("#output-directory[aria-invalid=true]")'))
        assert window.core.settings()['outputDirectory'] == str(output)
        shot('invalid-output.png'); click('取消修改')
        tasks = []
        for stage, factory, tool, source in [
            ('CP', 'HUAHONG', 'LOCAL_CP_HUAHONG_CLEAN_V1', args.cp.resolve()),
            ('FT', 'JIEMIN', 'LOCAL_FT_JIEMIN_FT_ALL_V1', args.ft.resolve()),
        ]:
            js(f'document.querySelector("[data-stage={stage}]").click()')
            wait(lambda: js(f'!!document.querySelector("[data-factory={factory}]")'))
            js(f'document.querySelector("[data-factory={factory}]").click()')
            wait(lambda: js(f'!!document.querySelector("[data-tool={tool}]")'))
            js(f'document.querySelector("[data-tool={tool}]").click()')
            edit('#input-paths', f'"{source}"')
            wait(lambda: js('[...document.querySelectorAll("button")].find(b=>b.textContent.trim()==="清洗").disabled'))
            click('应用输入路径')
            wait(lambda: js('document.querySelector("#input-paths").value') == str(source))
            shot(stage + '-ready.png'); click('清洗')
            wait(lambda: len(window.core.history()) == len(tasks) + 1)
            task_id = window.core.history()[0]['id']
            wait(lambda: window.core.task(task_id)['status'] in {'SUCCESS', 'FAILED', 'CANCELLED'}, 600)
            task = window.core.task(task_id)
            assert task['status'] == 'SUCCESS', task['error']
            assert task['sourcePaths'] == [str(source)]
            assert Path(task['outputParent']) == output and Path(task['publishedDirectory']).parent == output
            assert not task.get('warning'), task.get('warning')
            tasks.append(task_id)
        assert file.read_text() == 'unchanged'
        window.close(); app.processEvents()
        window = StudioWindow(root / 'home', ROOT / 'apps/web/dist'); window.show()
        wait(lambda: js('!!document.querySelector("#input-paths")'))
        assert js('document.querySelector("#input-paths").value') == ''
        assert js('document.querySelector("#output-directory").value') == str(output)
        assert len(window.core.history()) == 2
        shot('restart.png')
        record = dict(status='PASS', tasks=tasks, output=str(output), checks=[
            'Real Ctrl+V and Enter output save', 'Quoted/multiline inputs and duplicate paths',
            'Invalid edits preserve registered inputs/default output', 'Dirty paths block stale task submission',
            'Real CP and FT consume pasted inputs and publish to edited output',
            'Restart keeps output and history and clears inputs'])
        (root / 'evidence.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf8')
        print(json.dumps(record, ensure_ascii=False), flush=True)
    except Exception:
        (root / 'failure-dom.txt').write_text(js('document.body.innerText') or '', encoding='utf8')
        shot('failure.png'); raise
    finally:
        app.clipboard().setMimeData(saved_clipboard)
        QMessageBox.question = lambda *a, **k: QMessageBox.StandardButton.Yes
        window.close(); app.processEvents()


if __name__ == '__main__':
    multiprocessing.freeze_support(); main()
