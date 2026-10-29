"""Real Qt picker + React + HuaHong cleaning, confined to a private test home."""
import argparse,json,multiprocessing,sys,time
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--source',type=Path,required=True);a=p.parse_args()
    root=a.output.resolve();root.mkdir(parents=True,exist_ok=True)
    source=a.source.resolve();exports=root/'用户选择的输出';exports.mkdir(exist_ok=True)
    raw=root/'输入路径测试';raw.mkdir(exist_ok=True);(raw/'recursive').mkdir(exist_ok=True)
    (raw/'sample.TXT').write_text('picker-only fixture',encoding='utf8')
    from apps.desktop.rendering import configure_rendering
    configure_rendering('software')
    from PySide6.QtCore import QTimer,QItemSelectionModel,QStandardPaths
    from PySide6.QtWidgets import QApplication,QFileDialog
    from apps.desktop.security import register_scheme
    register_scheme();app=QApplication([])
    from apps.desktop.input_sources import InputSourceDialog
    from apps.desktop.shell import StudioWindow
    from python_core.engine import digest
    from python_core.paths import desktop_directory
    w=StudioWindow(root/'workspace',PROJECT/'apps/web/dist');w.resize(1440,960);w.show()
    def wait(fn,timeout=45):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            app.processEvents()
            if fn():return
            time.sleep(.01)
        raise AssertionError('Timed out')
    def js(code):
        answer=[];w.page.runJavaScript(code,answer.append);wait(lambda:bool(answer));return answer[0]
    def click(text):
        wait(lambda:js("(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==="+json.dumps(text)+");if(!b||b.disabled)return false;b.click();return true})()"))
    def screenshot(name):
        until=time.monotonic()+.6
        while time.monotonic()<until:app.processEvents();time.sleep(.01)
        w.grab().save(str(root/name))
    def pick(callback):
        # Exercise the actual modal created by Bridge, without replacing it.
        errors=[];finished=[];timer=QTimer();timer.setInterval(60)
        def drive():
            dialog=app.activeModalWidget()
            if isinstance(dialog,InputSourceDialog):
                timer.stop()
                try:callback(dialog)
                except Exception as exc:errors.append(repr(exc));dialog.reject()
                finished.append(True)
        timer.timeout.connect(drive);timer.start();click('选择数据源');wait(lambda:bool(finished));timer.stop()
        assert not errors,errors
        wait(lambda:js('!document.querySelector(".path-control-row button").disabled'))
    evidence={}
    try:
        wait(lambda:js('!!document.querySelector("#input-paths")'))
        assert Path(desktop_directory())==Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation))
        assert Path(js('document.querySelector("#output-directory").value'))==Path(desktop_directory())
        screenshot('01-default-desktop.png')
        def mixed(dialog):
            dialog._set_current_directory(raw)
            wait(lambda:dialog.model.rowCount(dialog.model.index(str(raw)))==2)
            for path in [raw/'sample.TXT',raw/'recursive']:
                index=dialog.model.index(str(path));assert index.isValid()
                dialog.source_view.selectionModel().select(index,QItemSelectionModel.SelectionFlag.Select|QItemSelectionModel.SelectionFlag.Rows)
            assert dialog.ok_button.isEnabled()
            dialog.grab().save(str(root/'02-unified-picker.png'));dialog.ok_button.click()
        pick(mixed)
        assert 'sample.TXT' in js('document.querySelector("#input-paths").value')
        assert 'recursive' in js('document.querySelector("#input-paths").value')
        assert not js('document.querySelector(".check-label input").checked')
        assert not js('document.body.innerText.includes("演示") || document.body.innerText.includes("真实分析结果")')
        assert len(w.core.workspace_files())==2
        js("document.querySelector('button[aria-label=\"移除 sample.TXT\"]').click()")
        wait(lambda:len(w.core.workspace_files())==1)
        assert (raw/'sample.TXT').read_text()=='picker-only fixture'
        click('清空列表');wait(lambda:not w.core.workspace_files())
        assert (raw/'recursive').is_dir()
        prior=w.core.settings()
        pick(lambda d:(d._set_current_directory(source.parent),d.reject()))
        assert w.core.settings()['inputDirectory']==prior['inputDirectory']
        pick(lambda d:(d.path_edit.setText(str(source)),d.go_button.click()))
        wait(lambda:js('document.querySelector("#input-paths").value')==str(source))
        assert w.core.settings()['inputDirectory']==str(source.parent)
        assert len(w.core.workspace_files())==1
        original=QFileDialog.getExistingDirectory
        QFileDialog.getExistingDirectory=lambda *args,**kwargs:str(exports)
        try:
            click('设置');wait(lambda:js('document.body.innerText.includes("更改输出目录")'))
            click('更改输出目录');wait(lambda:w.core.settings()['outputDirectory']==str(exports))
            screenshot('03-settings-default-output.png')
            QFileDialog.getExistingDirectory=lambda *args,**kwargs:''
            click('更改输出目录');wait(lambda:js('![...document.querySelectorAll("button")].find(b=>b.textContent.includes("更改输出目录")).disabled'))
            assert w.core.settings()['outputDirectory']==str(exports)
            js('document.querySelector("[data-stage=CP]").click()');wait(lambda:js('document.querySelector("#output-directory")?.value')==str(exports))
        finally:QFileDialog.getExistingDirectory=original
        screenshot('03-paths-selected.png')
        # Restart the full window, then verify persisted controls and native browse start.
        w.close();app.processEvents();w=StudioWindow(root/'workspace',PROJECT/'apps/web/dist');w.resize(1440,960);w.show()
        wait(lambda:js('!!document.querySelector("#input-paths")'))
        assert not js('document.querySelector("#input-paths").value')
        assert not w.core.workspace_files()
        assert js('document.querySelector("#output-directory").value')==str(exports)
        def check_start(dialog):assert dialog.current_directory==source.parent;dialog.reject()
        pick(check_start)
        pick(lambda d:(d.path_edit.setText(str(source)),d.go_button.click()))
        wait(lambda:js('document.querySelector("#input-paths")?.value')==str(source))
        click('DCP / TXT 数据清洗')
        click('开始清洗');wait(lambda:len(w.core.history())==1);task_id=w.core.history()[0]['id']
        # New settings must not redirect an already queued/running task.
        alternate=root/'下次输出';alternate.mkdir(exist_ok=True);w.core.set_output_directory(str(alternate))
        wait(lambda:w.core.task(task_id)['status'] in {'SUCCESS','FAILED','CANCELLED'},600)
        task=w.core.task(task_id);assert task['status']=='SUCCESS',task.get('error')
        assert not task.get('warning'),task.get('warning')
        saved=Path(task['publishedDirectory']);assert saved.parent==exports
        files=list(saved.glob('*.csv'));assert len(files)==3
        for item in task['artifacts']:
            if item['name'].startswith('files/'):assert digest(saved/Path(item['path']).name)==item['sha256']
        assert not list(alternate.iterdir())
        wait(lambda:js('[...document.querySelectorAll("button")].some(b=>b.textContent.trim()==="查看结果")'))
        click('查看结果');wait(lambda:js('document.querySelector(".result-directory")?.innerText.includes('+json.dumps(str(saved))+')'))
        assert not js('document.body.innerText.includes("演示") || document.body.innerText.includes("真实分析结果")')
        screenshot('04-auto-saved-result.png')
        js('document.querySelector("[data-stage=CP]").click()');wait(lambda:js('!!document.querySelector(".source-actions")'))
        click('清空列表');wait(lambda:not w.core.workspace_files())
        assert w.core.task(task_id)['status']=='SUCCESS' and saved.is_dir()
        w.close();app.processEvents();w=StudioWindow(root/'workspace',PROJECT/'apps/web/dist');w.show()
        wait(lambda:js('!!document.querySelector("#input-paths")'))
        assert not js('document.querySelector("#input-paths").value')
        assert js('document.querySelector("#output-directory").value')==str(alternate)
        click('历史记录');wait(lambda:js('[...document.querySelectorAll("button")].some(b=>b.textContent.trim()==="查看结果")'))
        click('查看结果');wait(lambda:js('!!document.querySelector(".result-directory")'))
        evidence=dict(status='PASS',taskId=task_id,source=str(source),output=str(saved),files=[p.name for p in files],records=task.get('receipt',{}).get('records'),checks=['redirected Desktop default','real native mixed file/folder chooser','cancel preserves previous input','full input/output display','restart clears inputs but preserves folder preferences','native picker starts at remembered folder','output location frozen per task','real HuaHong clean','3 CSV output SHA match immutable history','result view shows actual saved location','remove/clear only current list','no demo UI','settings default output and cancellation','cleared list stays empty after restart; history remains'])
        (root/'evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(evidence,ensure_ascii=False),flush=True)
    finally:w.close();app.processEvents()

if __name__=='__main__':multiprocessing.freeze_support();main()
