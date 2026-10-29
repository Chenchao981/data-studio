"""Own a real CP chart session while the rendered browser acceptance runs."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from urllib.request import build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--kit', type=Path, help='Validation-only explicit standalone engine kit')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    from python_core.core import Core
    from python_core.viewers import Viewers
    from python_core.engine import configuration, digest
    if args.kit:
        from python_core import engine
        kit = args.kit.resolve(strict=True)
        engine.engine_root = lambda: kit
    import psutil
    core = Core(args.home)
    tasks = [t for t in core.history(real_only=True) if t['status'] == 'SUCCESS'
             and t.get('parameters', {}).get('stage') == 'CP'
             and t['parameters'].get('operation') == 'QUICK_CLEAN']
    assert len(tasks) == 1, 'Use an isolated home with exactly one successful real CP cleaning task'
    task = tasks[0]
    viewers = Viewers(core)
    root, manifest = configuration()
    before = {a['path']: digest(a['path']) for a in task['artifacts']}
    url = None
    try:
        url = viewers.open(task['id'])
        assert viewers.open(task['id']) == url
        session = viewers.sessions[task['id']]
        children = [psutil.Process(session['process'].pid), *psutil.Process(session['process'].pid).children(recursive=True)]
        processes = [dict(pid=p.pid, executable=p.exe(), command=p.cmdline()) for p in children]
        (args.output/'processes.json').write_text(json.dumps(processes, indent=2), encoding='utf8')
        python_processes = [p for p in processes if Path(p['executable']).name.lower().startswith('python')]
        assert len(python_processes) >= 2
        assert all(Path(p['executable']).resolve() == (root/'runtime/python.exe').resolve() for p in python_processes)
        executable = subprocess.run(['where.exe', 'node'], capture_output=True, text=True, check=True).stdout.splitlines()[0]
        result = subprocess.run([executable, str(ROOT/'apps/web/tests/verify-cp-charts.mjs'), url, str(args.output.resolve())],
                                cwd=ROOT, capture_output=True, text=True, encoding='utf8', timeout=900)
        (args.output/'browser.log').write_text(result.stdout+'\n'+result.stderr, encoding='utf8')
        if result.returncode:
            raise AssertionError(result.stdout+'\n'+result.stderr)
        assert all(digest(path) == sha for path, sha in before.items())
        (args.output/'engine-evidence.json').write_text(json.dumps(dict(
            taskId=task['id'], engineVersion=manifest['version'], manifestSha256=digest(root/'manifest.json'),
            cpPackageSha256=digest(root/'packages/cp.pyz'),
            processes=processes,
            session=str(session['folder']), originalArtifactsUnchanged=True, reused=True), indent=2), encoding='utf8')
    finally:
        viewers.close()
    try:
        build_opener(ProxyHandler({})).open(url+'/_stcore/health', timeout=1)
    except OSError:
        pass
    else:
        raise AssertionError('Chart service survived owner exit')
    print('PASS: rendered CP default/optional charts, draft/apply, export, fixed runtime and lifecycle')


if __name__ == '__main__':
    main()
