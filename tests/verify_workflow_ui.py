"""Actual Qt/React workflow, large-input interaction and private real samples.

The OS file picker return is controlled by this test; processing, drag/drop,
QWebChannel, queue, folder-only results, export and history are real implementations.
"""
import argparse
import json
import multiprocessing
from pathlib import Path
import sys
import time

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cp',type=Path)
    parser.add_argument('--cp-tool',default='LOCAL_CP_HUAHONG_TD_V1')
    parser.add_argument('--ft',type=Path)
    parser.add_argument('--layout-only',action='store_true')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    if not args.layout_only and (not args.cp or not args.ft):parser.error('--cp and --ft are required unless --layout-only is used')
    from apps.desktop.rendering import configure_rendering
    configure_rendering('software')
    from PySide6.QtCore import Qt,QPointF,QMimeData,QUrl
    from PySide6.QtGui import QDropEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication,QMessageBox,QFileDialog
    from apps.desktop.security import register_scheme
    register_scheme();app=QApplication([])
    from apps.desktop.shell import StudioWindow
    w=StudioWindow(args.output/'workspace',PROJECT/'apps/web/dist')
    fixture=args.output/'layout-inputs';fixture.mkdir()
    fixture_paths=[]
    for i in range(100):
        path=fixture/f'INPUT_{i:04d}.xlsx';path.write_text('layout-only fixture',encoding='utf8');fixture_paths.append(path.resolve())
    exports=args.output/'selected-output';exports.mkdir(exist_ok=True);w.core.set_output_directory(str(exports.resolve()))
    w.resize(1440,960);w.show()
    def wait(fn,timeout=40):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            app.processEvents()
            if fn():return
            time.sleep(.005)
        raise AssertionError('Qt condition timed out')
    def js(code):
        result=[];w.page.runJavaScript(code,result.append);wait(lambda:bool(result));return result[0]
    def click(text):
        wait(lambda:js("(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==="+json.dumps(text)+");if(!b||b.disabled)return false;b.click();return true})()"))
    def selector(query):
        assert js("(()=>{let b=document.querySelector("+json.dumps(query)+");if(!b||b.disabled)return false;b.click();return true})()"),query
    def key(code):
        # Dispatch to the focused DOM element: background automation must not
        # steal the user's foreground window to exercise keyboard handlers.
        name='Escape' if code==Qt.Key.Key_Escape else 'ArrowDown'
        js('(document.activeElement||document.body).dispatchEvent(new KeyboardEvent("keydown",{key:'+json.dumps(name)+',bubbles:true}))')
    def shot(name):
        end=time.monotonic()+.7
        while time.monotonic()<end:app.processEvents();time.sleep(.01)
        w.grab().save(str(args.output/name))
    evidence={'checks':[]}
    try:
        wait(lambda:js('!!document.querySelector("#input-paths")'))
        assert js('document.querySelectorAll(".file-table tbody tr").length')==0
        from apps.desktop import input_sources
        original=input_sources.select_input_sources
        input_sources.select_input_sources=lambda *a,**k:tuple(fixture_paths)
        try:click('选择数据源');wait(lambda:js('document.querySelectorAll(".file-table tbody tr").length')==50)
        finally:input_sources.select_input_sources=original
        wait(lambda:js('document.querySelectorAll(".file-table tbody tr").length')==50)
        js('window.uiErrors=[];window.addEventListener("error",e=>window.uiErrors.push(e.message))')
        js('window.samples=[];window.done=false;(async()=>{for(let i=0;i<20;i++){let s=performance.now();document.querySelector(`[data-stage="${i%2?"CP":"FT"}"]`).click();await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));window.samples.push(performance.now()-s)}window.done=true})()')
        wait(lambda:js('window.done'))
        evidence.update(stageSwitchMs=json.loads(js('JSON.stringify(window.samples)')),domNodes=js('document.querySelectorAll("*").length'),renderedInputs=js('document.querySelectorAll(".file-table tbody tr").length'))
        assert js('document.querySelectorAll("select").length')==0
        shot('workspace.png')
        click('取消勾选');selector('[aria-label="选择本页输入"]');click('下一页');selector('[aria-label="选择本页输入"]')
        assert js('document.querySelector(".file-panel .panel-bottom").innerText.includes("已选 100 项")')
        click('取消勾选')
        evidence['checks'].append('Startup empty; explicit import of 100 fixtures, bounded 50-row DOM and cross-page selection')
        selector('[data-stage=FT]')
        wait(lambda:js('document.querySelector("[data-stage=FT]").getAttribute("aria-pressed")==="true"'))
        selector('[data-factory=DIANJI]')
        assert js('document.querySelector("[data-tool=LOCAL_FT_DIANJI_FT_ALL_V1]").getAttribute("aria-pressed")==="true"')
        evidence['checks'].append('direct stage switching and unambiguous factory cleaning selection')
        if args.layout_only:
            for width,height in [(1000,760),(920,620)]:
                w.resize(width,height);QTest.qWait(350);shot(f'workspace-{width}.png')
                assert js('document.documentElement.scrollWidth<=window.innerWidth')
            selector('button[title="切换明暗主题"]');wait(lambda:js('document.documentElement.dataset.theme==="dark"'));shot('workspace-dark.png')
        else:
            selector('[data-stage=CP]');selector('[data-factory=HUAHONG]');selector('[data-tool='+args.cp_tool+']')
            from apps.desktop import input_sources
            original=input_sources.select_input_sources
            input_sources.select_input_sources=lambda *a,**k:(args.cp.resolve(),)
            try:click('选择数据源');wait(lambda:js('document.querySelector(".file-panel .panel-bottom").innerText.includes("已选 1 项")'))
            finally:input_sources.select_input_sources=original
            shot('cp-ready.png');click('开始清洗')
            wait(lambda:bool(w.core.history()));cp_id=w.core.history()[0]['id']
            wait(lambda:w.core.task(cp_id)['status'] in {'SUCCESS','FAILED'},600)
            assert w.core.task(cp_id)['status']=='SUCCESS',w.core.task(cp_id)['error']
            wait(lambda:js('[...document.querySelectorAll("button")].some(b=>b.textContent.trim()==="查看结果")'))
            click('已完成');click('查看结果');wait(lambda:js('!!document.querySelector(".result-directory")'))
            assert not js('!!document.querySelector(".ag-root, .preview-panel")')
            shot('cp-result.png')
            evidence['checks'].append('Real CP cleaning and folder-only results without preview')
            click('← 返回历史');click('新建清洗');selector('[data-stage=FT]');selector('[data-factory=JIEMIN]');selector('[data-tool=LOCAL_FT_JIEMIN_FT_ALL_V1]')
            mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(args.ft.resolve()))])
            w.view.dropEvent(QDropEvent(QPointF(300,300),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier))
            wait(lambda:js('document.querySelector(".file-panel .panel-bottom").innerText.includes("已选 1 项")') and js('document.querySelector(".file-table tbody tr").innerText.includes('+json.dumps(args.ft.name)+')'))
            click('开始清洗');wait(lambda:len(w.core.history())==2);ft_id=w.core.history()[0]['id']
            wait(lambda:w.core.task(ft_id)['status'] in {'SUCCESS','FAILED'},600)
            assert w.core.task(ft_id)['status']=='SUCCESS',w.core.task(ft_id)['error']
            click('历史记录')
            selector('[aria-label="历史测试阶段"] button:last-child')
            wait(lambda:js('document.querySelectorAll(".history-list article").length')==1)
            click('查看结果');wait(lambda:js('!!document.querySelector(".result-directory")'));shot('ft-result.png')
            selector('[aria-label="选择分析任务"]');wait(lambda:js('document.querySelectorAll("[role=option]").length')==2)
            key(Qt.Key.Key_Escape)
            exported=args.output/'exported.zip';original=QFileDialog.getSaveFileName
            QFileDialog.getSaveFileName=lambda *a,**k:(str(exported.resolve()),'')
            try:click('完整归档ZIP');wait(exported.exists,60)
            finally:QFileDialog.getSaveFileName=original
            from python_core.engine import digest
            wait(lambda:exported.stat().st_size==Path(w.core.task(ft_id)['output']).stat().st_size)
            assert digest(exported)==w.core.task(ft_id)['sha256']
            selector('button[title="切换明暗主题"]');wait(lambda:js('document.documentElement.dataset.theme==="dark"'));shot('ft-result-dark.png')
            from python_core.core import Core
            reopened=Core(w.core.root)
            for task_id in [cp_id,ft_id]:assert reopened.task(task_id)['status']=='SUCCESS';reopened.output(task_id)
            evidence.update(cpTask=cp_id,ftTask=ft_id)
            evidence['checks'].append('FT XLSX OS drop auto-selection, real clean, history filter, export checksum, dark theme and reopened history')
        evidence['status']='PASS'
        assert json.loads(js('JSON.stringify(window.uiErrors)'))==[]
        (args.output/'evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf8');print(json.dumps(evidence),flush=True)
    finally:
        print('UI errors:',js('JSON.stringify(window.uiErrors||[])'),flush=True)
        QMessageBox.question=lambda *a,**k:QMessageBox.StandardButton.Yes
        w.close();app.processEvents()


if __name__=='__main__':multiprocessing.freeze_support();main()
