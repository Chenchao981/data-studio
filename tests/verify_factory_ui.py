"""Private UI-only 20-factory fixture; never changes the engine catalog on disk."""
import argparse
import json
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    from apps.desktop.rendering import configure_rendering
    configure_rendering('software')
    from PySide6.QtWidgets import QApplication
    from apps.desktop.security import register_scheme
    register_scheme()
    app = QApplication([])
    from apps.desktop.shell import StudioWindow
    window = StudioWindow(root / 'workspace', PROJECT / 'apps/web/dist')
    original = window.core.bootstrap

    def fixture():
        snapshot = original()
        tools = list(snapshot['engines']['tools'])
        for stage in ['CP', 'FT']:
            factories = {t['factory_code'] for t in tools if t['test_stage'] == stage}
            template = next(t for t in tools if t['test_stage'] == stage and t['enabled'] and not t.get('hidden'))
            for index in range(20 - len(factories)):
                tools.append({**template, 'factory_code': f'布局验证工厂{index + 1:02}', 'tool_code': f'UI_ONLY_{stage}_{index}', 'hidden': False})
        return {**snapshot, 'engines': {**snapshot['engines'], 'tools': tools}}

    window.core.bootstrap = fixture
    window.resize(1440, 960)
    window.show()

    def wait(test, timeout=25):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            app.processEvents()
            if test():
                return
            time.sleep(.01)
        raise AssertionError('Factory UI timeout')

    def js(code):
        values = []
        window.page.runJavaScript(code, values.append)
        wait(lambda: bool(values))
        return values[0]

    def search(value):
        js("(()=>{const e=document.querySelector('[aria-label=搜索工厂]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e," + json.dumps(value) + ");e.dispatchEvent(new Event('input',{bubbles:true}));})()")

    def screenshot(name):
        end = time.monotonic() + .3
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(.01)
        window.grab().save(str(root / name))

    evidence = []
    performance = []
    try:
        wait(lambda: js('document.querySelectorAll(".factory-tile").length===20'))
        for stage in ['CP', 'FT']:
            js(f'document.querySelector("[data-stage={stage}]").click()')
            wait(lambda: js('document.querySelectorAll(".factory-tile").length===20'))
            for width, height in [(1440, 960), (920, 620)]:
                window.resize(width, height)
                for dark in [False, True]:
                    js("document.documentElement.dataset.theme=" + json.dumps('dark' if dark else 'light'))
                    wait(lambda: js('document.querySelector(".factory-grid").clientHeight>0'))
                    assert js('(()=>{const g=document.querySelector(".factory-grid");return g.clientHeight<=190&&g.scrollHeight>g.clientHeight&&g.scrollWidth<=g.clientWidth+1;})()')
                    assert js('document.documentElement.scrollWidth<=innerWidth')
                    js('(()=>{const b=[...document.querySelectorAll(".factory-tile")].at(-1);b.scrollIntoView({block:"nearest"});b.focus();})()')
                    # Exercise real keyboard activation, not only a scripted click.
                    from PySide6.QtTest import QTest
                    from PySide6.QtCore import Qt
                    QTest.keyClick(window.view.focusProxy(), Qt.Key.Key_Return)
                    wait(lambda: js('document.activeElement?.getAttribute("aria-pressed")==="true"'))
                    selected = js('document.querySelector(".factory-current strong").textContent')
                    search('不存在的工厂')
                    wait(lambda: js('!!document.querySelector(".factory-no-match")'))
                    assert js('document.querySelector(".factory-current strong").textContent') == selected
                    search('华虹' if stage == 'CP' else 'shjm')
                    wait(lambda: js('document.querySelectorAll(".factory-tile").length===1'))
                    search('')
                    wait(lambda: js('document.querySelectorAll(".factory-tile").length===20'))
                    js('document.querySelector(".factory-grid").scrollTop=0;document.querySelector(".factory-browser").scrollIntoView({block:"start"})')
                    js("""void (async()=>{
                        window.factoryPerf=null;const samples=[];
                        const paint=()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
                        for(let i=0;i<20;i++){
                            const input=document.querySelector('[aria-label=搜索工厂]'),value=i%2?'':'布局验证';
                            const start=performance.now();
                            Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,value);input.dispatchEvent(new Event('input',{bubbles:true}));
                            await paint();samples.push(performance.now()-start);
                        }
                        window.factoryPerf=samples;
                    })()""")
                    wait(lambda: js('Array.isArray(window.factoryPerf)'))
                    timings = sorted(json.loads(js('JSON.stringify(window.factoryPerf)')))
                    assert len(timings) == 20
                    performance.append(dict(stage=stage,width=width,dark=dark,count=len(timings),p95Ms=timings[18],maxMs=timings[-1]))
                    assert timings[18] < 200, performance[-1]
                    screenshot(f'{stage}-{width}-{"dark" if dark else "light"}.png')
                    evidence.append(dict(stage=stage, width=width, dark=dark, factories=20))
        assert not window.core.history()
        (root / 'evidence.json').write_text(json.dumps({'status': 'PASS', 'cases': evidence, 'tasksCreated': 0, 'searchPerformance': performance}, indent=2), encoding='utf8')
        print('PASS: 20 factories per stage, search, keyboard, bounded layout, themes')
    except Exception:
        screenshot('failure.png')
        raise
    finally:
        window.close()
        app.processEvents()


if __name__ == '__main__':
    main()
