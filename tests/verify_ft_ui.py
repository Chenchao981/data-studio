"""Native file picker, FT chooser, real DVDS execution and restart history."""
import argparse,json,multiprocessing,sys,time
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--source',type=Path,required=True);a=p.parse_args()
    root=a.output.resolve();root.mkdir(parents=True,exist_ok=True);source=a.source.resolve()
    from apps.desktop.rendering import configure_rendering
    configure_rendering('software')
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from apps.desktop.security import register_scheme
    register_scheme();app=QApplication([])
    from apps.desktop.input_sources import InputSourceDialog
    from apps.desktop.shell import StudioWindow
    from python_core.engine import digest
    exports=root/'output';exports.mkdir(exist_ok=True)
    w=StudioWindow(root/'workspace',PROJECT/'apps/web/dist');w.core.set_output_directory(str(exports));w.resize(1440,960);w.show()
    def wait(fn,timeout=45):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            app.processEvents()
            if fn():return
            time.sleep(.01)
        raise AssertionError('UI timeout')
    def js(code):
        result=[];w.page.runJavaScript(code,result.append);wait(lambda:bool(result));return result[0]
    def click(text):
        wait(lambda:js("(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==="+json.dumps(text)+");if(!b||b.disabled)return false;b.click();return true})()"))
    def select_stage(stage):
        code='(()=>{const b=document.querySelector('+json.dumps('[data-stage='+stage+']')+');if(!b||b.disabled)return false;b.click();return true})()'
        wait(lambda:js(code))
    def screenshot(name):
        until=time.monotonic()+.5
        while time.monotonic()<until:app.processEvents();time.sleep(.01)
        w.grab().save(str(root/name))
    try:
        wait(lambda:js('!!document.querySelector("#input-paths")'))
        assert js('!!document.querySelector("[aria-label=其他分析操作] .operation-card")')
        select_stage('FT')
        wait(lambda:js('!!document.querySelector("[data-factory=JIEMIN]")'))
        js('document.querySelector("[data-factory=JIEMIN]").click()')
        wait(lambda:js('!!document.querySelector("[data-tool=LOCAL_FT_JIEMIN_DVDS_V1]")'))
        names=json.loads(js('JSON.stringify([...document.querySelectorAll(".chooser-operation .operation-card")].map(b=>b.textContent.trim()))'))
        assert names==['DC','DVDS','RG','PAT（原始数据）'],names
        wait(lambda:js('!!document.querySelector("[data-tool=LOCAL_FT_JIEMIN_RAW_PAT_V1]")'))
        extra=json.loads(js('JSON.stringify([...document.querySelectorAll(".operation-card")].map(b=>b.dataset.tool))'))
        assert len(extra)==5 and 'JIEMIN_FT_QUICK_PAT_EXISTING::CHART' in extra
        assert 'JIEMIN_FT_QUICK_PAT_EXISTING::CLEAN' not in extra and 'JIEMIN_FT_QUICK_PAT_EXISTING::PAT' not in extra
        click('DVDS')
        def import_source(path):
            timer=QTimer();timer.setInterval(60);finished=[]
            def choose():
                dialog=app.activeModalWidget()
                if isinstance(dialog,InputSourceDialog):
                    timer.stop();dialog.path_edit.setText(str(path));dialog.go_button.click();finished.append(True)
            timer.timeout.connect(choose);timer.start();click('选择数据源');wait(lambda:bool(finished));timer.stop()
            wait(lambda:js('document.querySelector("#input-paths").value')==str(path))
        import_source(source)
        select_stage('CP')
        wait(lambda:js('document.querySelector("#input-paths").value')=='')
        assert not js('!!document.querySelector(".content [data-stage]")')
        js('document.querySelector("[data-factory=JETECH]").click()')
        fixture=root/'workspace-draft.txt';fixture.write_text('UI input isolation fixture',encoding='utf8')
        import_source(fixture)
        js('document.querySelector(".check-label input").click()')
        screenshot('00-cp-workbench.png')
        for _ in range(3):
            select_stage('FT')
            wait(lambda:js('document.querySelector("#input-paths").value')==str(source))
            assert js('document.querySelector("[data-tool=LOCAL_FT_JIEMIN_DVDS_V1]").getAttribute("aria-pressed")==="true"')
            assert js('document.querySelector(".check-label input").checked')
            select_stage('CP')
            wait(lambda:js('document.querySelector("#input-paths").value')==str(fixture))
            assert js('document.querySelector("[data-factory=JETECH]").getAttribute("aria-pressed")==="true"')
            assert not js('document.querySelector(".check-label input").checked')
        click('清空列表');wait(lambda:js('document.querySelector("#input-paths").value')=='')
        select_stage('FT')
        wait(lambda:js('document.querySelector("#input-paths").value')==str(source))
        screenshot('01-jiemin-chooser.png');click('清洗');wait(lambda:len(w.core.history())==1)
        task_id=w.core.history()[0]['id']
        wait(lambda:js('!!document.querySelector(".task-log")'))
        assert js('[...document.querySelectorAll(".history-filters button")].some(b=>b.textContent==="处理中"&&b.getAttribute("aria-pressed")==="true")')
        wait(lambda:js('document.querySelector(".log-stream")?.textContent.includes("上海捷敏 DVDS：读取")'),120)
        live_status=w.core.task(task_id)['status'];assert live_status=='RUNNING',live_status
        screenshot('02-live-log.png')
        wait(lambda:w.core.task(task_id)['status'] in {'SUCCESS','FAILED'},240)
        wait(lambda:js('document.querySelector(".task-log .log-state")?.textContent==="已完成"'))
        assert js('document.querySelector(".log-stream").textContent.length>30')
        screenshot('03-completed-log.png')
        task=w.core.task(task_id);assert task['status']=='SUCCESS',task['error']
        assert task['toolCode']=='LOCAL_FT_JIEMIN_DVDS_V1'
        click('查看结果');wait(lambda:js('document.body.innerText.includes("清洗文件保存在")'))
        assert not js('!!document.querySelector(".ag-root")')
        assert not js('document.body.innerText.includes("演示")')
        files=list(Path(task['publishedDirectory']).rglob('*.xlsx'));assert len(files)==1
        artifact=next(x for x in task['artifacts'] if x['name'].endswith('.xlsx'));assert digest(files[0])==digest(artifact['path'])
        screenshot('02-real-dvds-result.png')
        w.close();app.processEvents();w=StudioWindow(root/'workspace',PROJECT/'apps/web/dist');w.show()
        wait(lambda:js('!!document.querySelector("#input-paths")'));assert not w.core.workspace_files()
        select_stage('FT');wait(lambda:js('document.querySelector("#input-paths").value')=='')
        click('历史记录');wait(lambda:js('document.body.innerText.includes("DVDS 数据清洗")'))
        screenshot('03-restarted-history.png')
        (root/'evidence.json').write_text(json.dumps({'status':'PASS','task':task_id,'operations':names,'output':str(files[0]),'startupEmpty':True,'historyRetained':True,'liveLogStatus':live_status,'autoProcessing':True,'workbenchDraftsIsolated':True,'workspaceSwitchRestoresConfiguration':True},ensure_ascii=False,indent=2),encoding='utf8')
        print('PASS: native picker, Jiemin DC/DVDS/RG/PAT, DVDS clean, history')
    except Exception:
        screenshot('failure.png')
        (root/'failure-dom.txt').write_text(js('document.body.innerText') or '',encoding='utf8')
        raise
    finally:w.close();app.processEvents()

if __name__=='__main__':multiprocessing.freeze_support();main()
