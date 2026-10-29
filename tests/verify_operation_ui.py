"""Check visible operation targets and layout in the actual Qt workbench."""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    from apps.desktop.rendering import configure_rendering
    configure_rendering('software')
    from PySide6.QtWidgets import QApplication
    from apps.desktop.security import register_scheme
    register_scheme()
    app = QApplication([])
    from apps.desktop.shell import StudioWindow
    window = StudioWindow(args.output / 'home', ROOT / 'apps/web/dist')
    window.resize(1440, 960)
    window.show()

    def wait(check, timeout=30):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            app.processEvents()
            if check():
                return
            time.sleep(.01)
        raise AssertionError('Operation UI timeout')

    def js(code):
        values = []
        window.page.runJavaScript(code, values.append)
        wait(lambda: bool(values))
        return values[0]

    def settle():
        until = time.monotonic() + .2
        while time.monotonic() < until:
            app.processEvents()
            time.sleep(.01)

    rows = []
    try:
        wait(lambda: js('!!document.querySelector(".operation-groups")'))
        js('window.uiErrors=[];window.addEventListener("error",e=>uiErrors.push(e.message))')
        for stage in ['CP', 'FT']:
            js(f'document.querySelector("[data-stage={stage}]").click()')
            settle()
            factories = json.loads(js('JSON.stringify([...document.querySelectorAll("[data-factory]")].map(e=>e.dataset.factory))'))
            assert len(factories) >= (4 if stage == 'CP' else 6), factories
            for factory in factories:
                js(f'document.querySelector("[data-factory={factory}]").click()')
                settle()
                codes = json.loads(js('JSON.stringify([...document.querySelectorAll(".operation-card")].filter(e=>!e.disabled).map(e=>e.dataset.tool))'))
                assert codes
                for code in codes:
                    query = '[data-tool=' + json.dumps(code) + ']'
                    before = js('JSON.stringify([...document.querySelectorAll(".operation-card")].map(e=>({x:e.offsetLeft,y:e.offsetTop,w:e.offsetWidth,h:e.offsetHeight})))')
                    js('document.querySelector(' + json.dumps(query) + ').click()')
                    settle()
                    assert js('document.querySelector(' + json.dumps(query) + ').getAttribute("aria-pressed")==="true"')
                    assert js('document.querySelectorAll(".operation-card.selected").length') == 1
                    after = js('JSON.stringify([...document.querySelectorAll(".operation-card")].map(e=>({x:e.offsetLeft,y:e.offsetTop,w:e.offsetWidth,h:e.offsetHeight})))')
                    assert before == after, (factory, code, 'selection changed layout')
                rows.append(dict(stage=stage, factory=factory, selectableOperations=len(codes)))
            for width, height in [(1440, 960), (920, 620)]:
                for theme in ['light', 'dark']:
                    # Use representative CP/FT factories with multiple groups.
                    factory = 'HUAHONG' if stage == 'CP' else 'RIYUEXIN'
                    js(f'document.querySelector("[data-factory={factory}]").click()')
                    window.resize(width, height)
                    window.core.save_settings({'theme': theme})
                    window.bridge.changed.emit()
                    wait(lambda: js('document.documentElement.dataset.theme') == theme)
                    settle()
                    js('document.querySelector(".operation-card").click()')
                    settle()
                    assert js('document.documentElement.scrollWidth<=innerWidth')
                    assert js('[...document.querySelectorAll(".operation-card")].every(e=>e.offsetHeight>=42&&e.offsetWidth>=96&&e.scrollWidth<=e.clientWidth+1)')
                    if width == 1440 and stage == 'CP':
                        assert js('document.querySelector(".chooser-operation").offsetHeight<90')
                    assert not js('!!document.querySelector(".input-guide, .source-hint, .path-start, .path-field small")')
                    window.grab().save(str(args.output / f'{stage}-{width}-{theme}.png'))
        assert len(rows) >= 10
        assert not window.core.history()
        assert not js('window.uiErrors.length')
        result = dict(status='PASS', factories=rows, tasksCreated=0,
                      checks=['Every enabled operation selectable', 'No layout shift on selection',
                              '42px targets and compact CP function row', 'Light/dark and 920px/1440px layouts', 'Repeated hints removed'])
        (args.output / 'evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
        print(json.dumps(result, ensure_ascii=False))
    finally:
        window.close()
        app.processEvents()


if __name__ == '__main__':
    main()
