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
    from PySide6.QtWidgets import QApplication,QFileDialog
    from PySide6.QtGui import QDesktopServices
    from apps.desktop.security import register_scheme
    register_scheme();app=QApplication([])
    from apps.desktop.shell import StudioWindow
    w=StudioWindow(a.home,ROOT/'apps/web/dist');w.resize(1440,960);w.show()
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
        click('历史记录');click('查看结果');wait(lambda:js('document.querySelectorAll(".ag-row").length')>0)
        wait(lambda:js('document.body.innerText.includes("3,875")||document.body.innerText.includes("3875")'))
        js('document.querySelector("[aria-label=结果工作表]").click()')
        wait(lambda:js('document.querySelectorAll("[role=option]").length')==3)
        js('document.activeElement.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",bubbles:true}))')
        w.grab().save(str(a.output/'cp-result.png'))
        click('清洗文件夹');wait(lambda:bool(opened));assert opened[-1].startswith('file:')
        click('另存清洗文件夹');wait(lambda:len(list(export.rglob('*.csv')))==3)
        click('查看CP图表');wait(lambda:any(x.startswith('http:') for x in opened));url=next(x for x in opened if x.startswith('http:'))
        opener=build_opener(ProxyHandler({}))
        with opener.open(url+'/_stcore/health',timeout=5) as r:assert r.status==200
        click('查看CP图表');wait(lambda:len([x for x in opened if x.startswith('http:')])==2)
        assert [x for x in opened if x.startswith('http:')]==[url,url]
        (a.output/'evidence.json').write_text(json.dumps({'status':'PASS','url':url,'tables':3,'records':3875,'exported':3,'reused':True},indent=2),encoding='utf8')
    finally:
        w.close();app.processEvents();QDesktopServices.openUrl=original_open;QFileDialog.getExistingDirectory=original_dialog
    if url:
        try:opener.open(url+'/_stcore/health',timeout=1)
        except OSError:pass
        else:raise AssertionError('Chart server survived client close')
    print('PASS: old history, result actions, export, reused charts and close lifecycle')

if __name__=='__main__':multiprocessing.freeze_support();main()
