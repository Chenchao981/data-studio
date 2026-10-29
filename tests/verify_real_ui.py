"""Drive the actual Qt/React workflow with a caller-supplied private CP sample."""
import argparse
import json
import multiprocessing
from pathlib import Path
import sys
import time

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', required=True)
    p.add_argument('--tool', default='LOCAL_CP_HUAHONG_TD_V1')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); a.output.mkdir(parents=True)
    from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog
    from apps.desktop.security import register_scheme
    register_scheme(); app = QApplication([])
    from apps.desktop.shell import StudioWindow
    w = StudioWindow(a.output / 'workspace', PROJECT / 'apps/web/dist')
    w.core.register([a.source]); w.resize(1400, 900); w.show()

    def wait(check, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            app.processEvents()
            if check(): return
            time.sleep(.02)
        raise AssertionError('Qt condition timed out')

    def js(code):
        value = []; w.page.runJavaScript(code, value.append); wait(lambda: bool(value))
        return value[0]

    def click(label):
        assert js("(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===" + json.dumps(label) + ");if(!b||b.disabled)return false;b.click();return true})()"), label

    def shot(name):
        until = time.monotonic() + .7
        while time.monotonic() < until: app.processEvents(); time.sleep(.02)
        w.grab().save(str(a.output / name))

    responses = {}
    w.bridge.response.connect(lambda i, r: responses.update({i: json.loads(r)}))
    def rpc(method, params):
        rid = str(time.monotonic_ns()); w.bridge.request(rid, method, json.dumps(params))
        wait(lambda: rid in responses, 120)
        result = responses.pop(rid); assert result['ok'], result
        return result['value']

    try:
        wait(lambda: js("!!document.querySelector('.file-table tbody tr')"))
        spec=next(t for t in w.core.bootstrap()['engines']['tools'] if t['tool_code']==a.tool)
        js("document.querySelector('[data-stage="+spec['test_stage']+"]').click()")
        wait(lambda:js("!!document.querySelector('[data-factory="+spec['factory_code']+"]')"))
        js("document.querySelector('[data-factory="+spec['factory_code']+"]').click()")
        if not js("!!document.querySelector('[data-tool="+a.tool+"]')"):js("document.querySelector('.more-operations').click()")
        js("document.querySelector('[data-tool="+a.tool+"]').click()")
        js("document.querySelector('input[aria-label=选择本页输入]').click()")
        shot('workspace-ready.png');click('开始清洗')
        wait(lambda: bool(w.core.history()))
        task_id = w.core.history()[0]['id']
        js("window.gaps=[];let last=performance.now();window.beat=setInterval(()=>{window.gaps.push(performance.now()-last);last=performance.now()},25)")
        wait(lambda: w.core.task(task_id)['status'] in {'SUCCESS', 'FAILED'}, 600)
        task = w.core.task(task_id); assert task['status'] == 'SUCCESS', task['error']
        wait(lambda: js("document.body.innerText.includes('查看结果')")); shot('history.png')
        click('查看结果'); wait(lambda: js("document.querySelectorAll('.ag-row').length>0")); shot('result.png')
        assert 'DEMO-IGBT' not in js('document.body.innerText')
        assert js("!!document.querySelector('button[aria-label=结果工作表]')")
        exported = a.output / 'exported.zip'
        original_dialog = QFileDialog.getSaveFileName
        QFileDialog.getSaveFileName = lambda *args, **kw: (str(exported.resolve()), '')
        try: assert rpc('exportResult', {'id': task_id})
        finally: QFileDialog.getSaveFileName = original_dialog
        from python_core.engine import digest
        assert digest(exported) == task['sha256']
        rpc('saveSettings', {'theme': 'dark'}); w.bridge.changed.emit()
        wait(lambda: js("document.documentElement.dataset.theme==='dark'")); shot('result-dark.png')
        evidence = dict(status='PASS', taskId=task_id, tables=len(task['tables']),
                        maxHeartbeatGapMs=js('Math.max(...window.gaps)'),
                        checks=['Actual React rule selection and task submission', 'Real CP engine process',
                                'Original result worksheets through QWebChannel', 'Asynchronous result export with hash equality',
                                'Dark theme', 'Persistent completed history'])
        js('clearInterval(window.beat)')
        (a.output / 'evidence.json').write_text(json.dumps(evidence, indent=2), encoding='utf8')
        print(json.dumps(evidence, indent=2))
    finally:
        QMessageBox.question = lambda *a, **k: QMessageBox.StandardButton.Yes
        w.close(); app.processEvents()


if __name__ == '__main__': multiprocessing.freeze_support(); main()
