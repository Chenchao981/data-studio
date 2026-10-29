"""Exercise CP result/history buttons with a private, preseeded real history.

Only native dialogs and external opening are intercepted. React, QWebChannel,
original-file export and the owned CP Cockpit process all run normally.
"""
import argparse,json,multiprocessing,sys,time
from pathlib import Path
from urllib.request import build_opener,ProxyHandler
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def main():
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True);export=a.output/'export';export.mkdir(exist_ok=True)
    from apps.desktop.rendering import configure_rendering
    configure_rendering('software')
    from PySide6.QtWidgets import QApplication,QFileDialog
    from PySide6.QtGui import QDesktopServices
    from apps.desktop.security import register_scheme
    register_scheme();app=QApplication([])
    from apps.desktop.shell import StudioWindow
    w=StudioWindow(a.home,ROOT/'apps/web/dist');w.resize(1440,960);w.show()
    completed=[t for t in w.core.history(real_only=True) if t['status']=='SUCCESS']
    assert len(completed)==1 and completed[0].get('parameters',{}).get('stage')=='CP' and completed[0]['parameters'].get('operation')=='QUICK_CLEAN', 'Use an isolated home containing exactly one successful CP cleaning task'
    task=completed[0]
    expected=[x for x in task['artifacts'] if x['name'].startswith('files/') and x['name'].endswith('.csv')]
    assert len(expected)==3, 'This check requires the standard cleaned/yield/spec CP contract'
    opened=[];original_open=QDesktopServices.openUrl;original_dialog=QFileDialog.getExistingDirectory
    QDesktopServices.openUrl=lambda u:opened.append(u.toString()) or True
    QFileDialog.getExistingDirectory=lambda *args,**kwargs:str(export.resolve())
    def wait(f,timeout=90):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            app.processEvents()
            if f():return
            time.sleep(.01)
        raise AssertionError('UI condition timed out')
    def js(code):
        value=[];w.page.runJavaScript(code,value.append);wait(lambda:bool(value));return value[0]
    def click(text):
        query="[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==="+json.dumps(text)+")"
        wait(lambda:js('Boolean('+query+'&&!('+query+').disabled)'))
        js('('+query+').click()')
    url=None
    try:
        click('历史记录');click('查看结果');wait(lambda:js('!!document.querySelector(".result-directory")'))
        assert not js('!!document.querySelector(".ag-root, .preview-panel")')
        w.grab().save(str(a.output/'cp-result.png'))
        click('打开结果文件夹');wait(lambda:bool(opened));assert opened[-1].startswith('file:')
        click('另存清洗文件夹');wait(lambda:len(list(export.rglob('*.csv')))==3)
        from python_core.engine import digest
        for item in expected:
            copied=list(export.rglob(Path(item['path']).name));assert len(copied)==1 and digest(copied[0])==item['sha256']
        click('查看CP图表');wait(lambda:any(x.startswith('http:') for x in opened));url=next(x for x in opened if x.startswith('http:'))
        opener=build_opener(ProxyHandler({}))
        with opener.open(url+'/_stcore/health',timeout=5) as r:assert r.status==200
        click('查看CP图表');wait(lambda:len([x for x in opened if x.startswith('http:')])==2)
        assert [x for x in opened if x.startswith('http:')]==[url,url]
        (a.output/'evidence.json').write_text(json.dumps({'status':'PASS','url':url,'csvFiles':3,'records':task.get('receipt',{}).get('records'),'exported':3,'reused':True,'noPreview':True,'chartScope':'HTTP readiness and owned process lifecycle; rendered charts require verify-cp-charts.mjs'},indent=2),encoding='utf8')
    finally:
        w.close();app.processEvents();QDesktopServices.openUrl=original_open;QFileDialog.getExistingDirectory=original_dialog
    if url:
        try:opener.open(url+'/_stcore/health',timeout=1)
        except OSError:pass
        else:raise AssertionError('Chart server survived client close')
    print('PASS: old history, result actions, export, reused charts and close lifecycle')

if __name__=='__main__':multiprocessing.freeze_support();main()
