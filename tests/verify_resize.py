"""Native window geometry stress, not browser viewport emulation."""
import argparse,json,multiprocessing,os,sys,time
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))

def main():
    p=argparse.ArgumentParser();p.add_argument('--software',action='store_true');p.add_argument('--home',type=Path);p.add_argument('--recovery',action='store_true');p.add_argument('--charts',action='store_true');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.software:
        os.environ['QTWEBENGINE_CHROMIUM_FLAGS']='--disable-gpu'
        os.environ['QT_QUICK_BACKEND']='software'
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from apps.desktop.security import register_scheme
    register_scheme();app=QApplication([])
    from apps.desktop.shell import StudioWindow
    a.output.mkdir(parents=True,exist_ok=True)
    w=StudioWindow(a.home or a.output/'home',PROJECT/'apps/web/dist');w.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating);w.show()
    crashes=[];w.page.renderProcessTerminated.connect(lambda s,c:crashes.append((str(s),c)))
    def pump(seconds):
        end=time.perf_counter()+seconds
        while time.perf_counter()<end:app.processEvents();time.sleep(.002)
    def js(code):
        result=[];w.page.runJavaScript(code,result.append);end=time.perf_counter()+15
        while not result and time.perf_counter()<end:pump(.005)
        assert result,code
        return result[0]
    def wait_js(code,timeout=20):
        end=time.perf_counter()+timeout
        while time.perf_counter()<end:
            if js(code):return
            pump(.05)
        raise AssertionError(code)
    def click(text):
        assert js("(()=>{let b=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==="+json.dumps(text)+");if(!b||b.disabled)return false;b.click();return true})()")
    try:
        pump(3);assert js('!!document.querySelector("#input-paths")')
        if a.home:
            click('历史记录');wait_js("[...document.querySelectorAll('button')].some(b=>b.textContent.trim()==='查看结果')");click('查看结果');wait_js("!!document.querySelector('.result-directory')")
        if a.charts:
            click('清洗结果');click('演示数据');click('演示统计');wait_js("document.querySelectorAll('.chart-canvas canvas').length===2")
        js('window.resizeSentinel=123;window.gaps=[];window.last=performance.now();window.watch=setInterval(()=>{let n=performance.now();gaps.push(n-last);last=n},20)')
        start=time.perf_counter();blank=[];durations=[]
        for i in range(100):
            now=time.perf_counter();w.resize(920+(i%20)*29,620+(i%20)*16);pump(.025);durations.append((time.perf_counter()-now)*1000)
            if i%10==0:
                image=w.view.grab().toImage()
                colors=[image.pixelColor(x*image.width()//10,y*image.height()//10).name() for x in range(1,10) for y in range(1,10)]
                blank.append(len(set(colors))<3)
        for i in range(4):w.showMaximized();pump(.15);w.showNormal();pump(.15)
        screens=[]
        for screen in app.screens():
            w.windowHandle().setScreen(screen);w.move(screen.availableGeometry().topLeft());pump(.65)
            actual=w.windowHandle().screen();assert actual==screen,(actual.name(),screen.name())
            screens.append(dict(name=screen.name(),dpi=screen.logicalDotsPerInch(),dpr=screen.devicePixelRatio(),actualWindowScreen=actual.name(),actualWindowDpr=w.devicePixelRatioF()))
        pump(.4);gaps=json.loads(js('clearInterval(window.watch);JSON.stringify(window.gaps)'))
        if a.charts:
            sizes=json.loads(js("JSON.stringify([...document.querySelectorAll('.chart-canvas')].map(e=>({host:e.clientWidth,canvas:e.querySelector('canvas').getBoundingClientRect().width})))"));assert all(abs(i['host']-i['canvas'])<2 for i in sizes),sizes
        assert js('window.resizeSentinel===123'), 'Resize must not reload the interface'
        w.grab().save(str(a.output/'window.png'))
        result=dict(software=a.software,resize100seconds=time.perf_counter()-start,maxQtCycleMs=max(durations),maxJsGapMs=max(gaps),blankSamples=sum(blank),crashes=list(crashes),screens=screens)
        if a.recovery:
            def ready():
                end=time.perf_counter()+20
                while time.perf_counter()<end:
                    pump(.05)
                    if w._page_ready and w.surface.currentWidget()==w.view:
                        wait_js('!!document.querySelector("#input-paths")');return
                raise AssertionError('Interface recovery timed out')
            task=w.core.create_task('demo-cp');w.tasks.start(task['id']);w.tick()
            worker_pid=w.tasks.active[1].pid;renderer_pid=w.page.renderProcessPid()
            assert renderer_pid>0 and worker_pid!=renderer_pid
            os.kill(renderer_pid,9);pump(.15)
            w.grab().save(str(a.output/'recovering.png'));ready()
            deadline=time.monotonic()+15
            while w.core.task(task['id'])['status'] not in {'SUCCESS','FAILED','CANCELLED'} and time.monotonic()<deadline:pump(.1)
            assert w.core.task(task['id'])['status']=='SUCCESS'
            assert len([t for t in w.core.history() if t['id']==task['id']])==1
            w.core.output(task['id'])
            # A repeated fault must stop automatic retries and expose a working button.
            os.kill(w.page.renderProcessPid(),9);pump(1.2)
            assert w.surface.currentWidget()==w.recovery_panel and w.recovery_button.isEnabled()
            w.recovery_button.click();ready()
            # Exercise overdue-response and load timeout branches without hanging a CPU.
            w._pending_probe=(w._probe_serial,time.monotonic()-16);w.check_renderer()
            assert w.surface.currentWidget()==w.recovery_panel
            w.recovery_button.click();ready()
            w.load_started();w._loading_since=time.monotonic()-21;w.check_renderer()
            assert w.recovery_button.isEnabled() and w.surface.currentWidget()==w.recovery_panel
            w.recovery_button.click();ready()
            result['recovery']={'actualRendererTerminations':len(crashes),'backgroundTask':w.core.task(task['id'])['status'],'duplicateTasks':False,'manualRetry':True,'timeoutPaths':True}
            w.grab().save(str(a.output/'recovered.png'))
        assert not result['blankSamples']
        assert not result['crashes'], 'Unexpected renderer termination during window resize'
        print(json.dumps(result),flush=True);(a.output/'evidence.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    finally:w.close();pump(.1)

if __name__=='__main__':multiprocessing.freeze_support();main()
