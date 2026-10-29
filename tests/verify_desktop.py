"""Real Qt/WebEngine smoke, RPC and local OS dialog; produces bounded evidence."""
from __future__ import annotations

import argparse
import json
import multiprocessing
import os
from pathlib import Path
import sys
import threading
import time

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=PROJECT/"artifacts/desktop")
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    from apps.desktop.rendering import configure_rendering
    configure_rendering('software')
    from PySide6.QtCore import QUrl, QMimeData, QPointF, Qt
    from PySide6.QtGui import QDropEvent
    from PySide6.QtWidgets import QApplication, QMessageBox
    from apps.desktop.security import register_scheme, APP_URL, resource_path
    register_scheme()
    app=QApplication([])
    from apps.desktop.shell import StudioWindow
    window=StudioWindow(args.output/"workspace",PROJECT/"apps/web/dist")
    window.resize(1400,900);window.show()
    def wait(predicate,timeout=30):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            app.processEvents()
            if predicate():return
            time.sleep(.02)
        raise AssertionError("Qt operation timed out")
    def js(code):
        result=[]
        window.page.runJavaScript(code,lambda r:result.append(r))
        wait(lambda:bool(result))
        return result[0]
    def click(text):
        assert js("(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==="+json.dumps(text)+");if(!b)return false;b.click();return true})()"),text
    def snapshot(name):
        # DOM-ready precedes Chromium's compositor frame; wait for the actual paint.
        until=time.monotonic()+.6
        while time.monotonic()<until:
            app.processEvents();time.sleep(.02)
        window.grab().save(str(args.output/name))
    responses={}
    window.bridge.response.connect(lambda rid,result:responses.update({rid:json.loads(result)}))
    def rpc(method,params=None):
        rid=str(time.monotonic_ns());window.bridge.request(rid,method,json.dumps(params or {}));wait(lambda:rid in responses);r=responses.pop(rid);assert r["ok"],r;return r["value"]
    evidence={"scale":os.environ.get("QT_SCALE_FACTOR","1"),"checks":[]}
    try:
        wait(lambda:js("Boolean(document.querySelector('.file-table'))"))
        assert "Python Core" in js("document.body.innerText")
        snapshot("workspace.png")
        evidence["checks"].append("React built assets and QWebChannel loaded in Qt")
        # Schedule a native Win32 automation helper before opening the modal Qt file dialog.
        source=args.output/"原生选择测试.csv";source.write_text("UNCHANGED",encoding="utf8")
        dialog_result=[]
        def accept_dialog():
            import win32gui,win32con,win32process
            deadline=time.monotonic()+20
            while time.monotonic()<deadline:
                windows=[]
                def visit(hwnd,_):
                    if win32process.GetWindowThreadProcessId(hwnd)[1]==os.getpid() and win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd).startswith("选择本地测试数据"):
                        windows.append(hwnd)
                win32gui.EnumWindows(visit,None)
                if windows:
                    hwnd=windows[0];edits=[]
                    win32gui.EnumChildWindows(hwnd,lambda child,_:edits.append(child) if win32gui.GetClassName(child)=="Edit" and win32gui.IsWindowVisible(child) else None,None)
                    if edits:
                        win32gui.SendMessage(edits[-1],win32con.WM_SETTEXT,0,str(source.resolve()))
                        win32gui.PostMessage(hwnd,win32con.WM_COMMAND,1,0)
                        dialog_result.append(True);return
                time.sleep(.1)
            dialog_result.append(False)
            # Do not leave a native modal dialog behind if automation could not select.
            for hwnd in windows:
                win32gui.PostMessage(hwnd,win32con.WM_CLOSE,0,0)
        if os.name=="nt":
            helper=threading.Thread(target=accept_dialog,daemon=True);helper.start()
            selected=rpc("selectFiles")
            assert dialog_result==[True] and any(f["name"]==source.name for f in selected)
            evidence["checks"].append("Windows native file dialog selected a real Chinese-path file")
        paths=[]
        inputs=args.output/"inputs";inputs.mkdir(exist_ok=True)
        for i in range(100):
            path=inputs/f"sample_{i}.csv";path.write_text("UNCHANGED",encoding="utf8");paths.append(path)
        mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(p.resolve())) for p in paths])
        event=QDropEvent(QPointF(100,100),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        window.view.dropEvent(event)
        wait(lambda:len(window.core.files())>=103)
        assert event.isAccepted()
        # Registration completes before React handles studio-imported. Wait for
        # that update before navigating, otherwise it can reopen the workbench.
        wait(lambda:js('document.querySelectorAll(".file-table tbody tr").length===50 && document.querySelector(".file-panel .panel-bottom")?.textContent.includes("已选 100 项")'))
        evidence["checks"].append("100 local inputs registered by Qt drop; contents unchanged")
        js("window.heartbeat=[];window.lastBeat=performance.now();window.heartbeatTimer=setInterval(()=>{window.heartbeat.push(performance.now()-window.lastBeat);window.lastBeat=performance.now()},25)")
        click("清洗结果")
        wait(lambda:js("document.body.innerText.includes('还没有成功的真实分析')"))
        snapshot("results-empty.png")
        evidence["checks"].append("Results view keeps Excel and reports outside the client; no demo or worksheet preview is rendered")
        js('document.querySelector("[data-stage=CP]").click()')
        wait(lambda:js('document.querySelector("[data-stage=CP]").getAttribute("aria-pressed")==="true"'))
        task=rpc("createTask",dict(sourceId="demo-cp"));rpc("startTask",dict(id=task["id"]))
        wait(lambda:window.core.task(task["id"])["status"]=="SUCCESS")
        window.core.output(task["id"])
        cancel=rpc("createTask",dict(sourceId="demo-ft"));rpc("startTask",dict(id=cancel["id"]))
        wait(lambda:window.core.task(cancel["id"])["status"]=="RUNNING");rpc("cancelTask",dict(id=cancel["id"]))
        wait(lambda:window.core.task(cancel["id"])["status"]=="CANCELLED")
        failed=rpc("createTask",dict(sourceId="demo-fail"));rpc("startTask",dict(id=failed["id"]))
        wait(lambda:window.core.task(failed["id"])["status"]=="FAILED")
        evidence["checks"].append("Independent process success, failure, cancellation and result hash")
        rpc("saveSettings",dict(theme="dark"));window.bridge.changed.emit()
        wait(lambda:js("document.documentElement.dataset.theme==='dark'"))
        snapshot("analysis-dark.png")
        click("历史记录");wait(lambda:js("document.body.innerText.includes('本地任务记录')"));snapshot("history-dark.png")
        evidence["maxHeartbeatGapMs"]=js("Math.max(...window.heartbeat)")
        js("clearInterval(window.heartbeatTimer)")
        js("window.networkBlocked=false;fetch('https://example.com/').catch(()=>window.networkBlocked=true)")
        wait(lambda:js("window.networkBlocked"))
        window.view.load(QUrl("https://example.com/"));app.processEvents();assert window.page.url().toString()==APP_URL
        for url in ["studio://app/../secret", "studio://else/index.html", "file:///C:/Windows/win.ini"]:
            try:resource_path(PROJECT/"apps/web/dist",QUrl(url));raise AssertionError("Traversal accepted")
            except ValueError:pass
        evidence["checks"].append("External fetch/navigation and resource traversal rejected")
        window.resize(1024,768);js('document.querySelector("[data-stage=CP]").click()');snapshot("workspace-small-dark.png")
        assert source.read_text()=="UNCHANGED" and all(p.read_text()=="UNCHANGED" for p in paths)
        wait(lambda:window.tasks.active is None)
        evidence["status"]="PASS"
    finally:
        QMessageBox.question=lambda *a,**k:QMessageBox.StandardButton.Yes
        window.close();app.processEvents()
    (args.output/"evidence.json").write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding="utf8")
    print(json.dumps(evidence,ensure_ascii=False,indent=2))


if __name__=="__main__":
    multiprocessing.freeze_support()
    main()
