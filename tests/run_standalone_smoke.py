"""Run one real local task against a supplied standalone engine kit.

This is a release verification helper.  It uses an explicitly supplied home so
it never changes a user's normal history or output configuration.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "engine_support"), str(ROOT / "engine_support" / "backend"), str(ROOT / "engine_support" / "desktop_client")]


def bind_validation_kit(kit: Path) -> None:
    """Validation-only hook, reinstalled when Windows spawn imports this script."""
    from python_core import engine, warm_engine
    import psutil

    kit = kit.resolve(strict=True)
    engine.engine_root = lambda: kit
    transport = engine.subprocess

    def launch(command, **kwargs):
        runtime = kit / 'runtime/python.exe'
        script=next((Path(arg).resolve() for arg in command[1:] if str(arg).endswith('.py')),None)
        if Path(command[0]).resolve() != runtime or script not in {kit/'code/studio_runner.py',kit/'code/studio_service.py'}:
            raise ValueError('Validation worker attempted to use another engine kit')
        expected_pythonpath = os.pathsep.join(map(str, [kit / 'code', kit / 'code/backend', kit / 'code/desktop_client']))
        if kwargs['env']['PYTHONPATH'] != expected_pythonpath:
            raise ValueError('Validation worker code search path differs from requested kit')
        manifest = json.loads((kit / 'manifest.json').read_text(encoding='utf8'))
        packages = {}
        for name, expected in manifest['files'].items():
            if name.startswith('packages/'):
                actual = engine.digest(kit / name)
                if actual != expected:
                    raise ValueError('Validation package checksum failed: ' + name)
                packages[name] = {'path': str(kit / name), 'sha256': actual}
        process = transport.Popen(command, **kwargs)
        try:
            executable = Path(psutil.Process(process.pid).exe()).resolve()
            if executable != runtime:
                raise ValueError('Validation runtime executable differs from requested kit')
            evidence = dict(kit=str(kit), workerPid=os.getpid(), runtimePid=process.pid,
                            executable=str(executable), command=command,
                            pythonPath=kwargs['env']['PYTHONPATH'], packages=packages,
                            manifestSha256=engine.digest(kit / 'manifest.json'))
            (Path(kwargs['cwd']) / 'validation-engine.json').write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf8')
        except BaseException:
            process.kill()
            process.wait()
            raise
        return process

    # Replace this module's transport only; do not patch global subprocess.Popen.
    engine.subprocess = types.SimpleNamespace(**{**vars(transport), 'Popen': launch})
    warm_engine.subprocess = engine.subprocess


if __name__ == '__mp_main__' and os.environ.get('STUDIO_VALIDATION_ENGINE_KIT'):
    bind_validation_kit(Path(os.environ['STUDIO_VALIDATION_ENGINE_KIT']))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--tool", required=True)
    parser.add_argument("--home", required=True, type=Path)
    parser.add_argument("--kit", required=True, type=Path)
    args = parser.parse_args()
    kit = args.kit.resolve(strict=True)
    os.environ["STUDIO_VALIDATION_ENGINE_KIT"] = str(kit)

    from python_core import engine
    from python_core.core import Core
    from python_core.tasks import TaskManager

    bind_validation_kit(kit)
    core = Core(args.home.resolve())
    exports = args.home.resolve().parent / (args.home.resolve().name + "-exports")
    exports.mkdir(parents=True, exist_ok=True)
    core.set_output_directory(str(exports))
    source = core.register([str(args.source.resolve())])[0]
    task = core.create_task(source["id"], args.tool)
    manager = TaskManager(core)
    try:
        manager.start(task["id"])
        deadline = time.monotonic() + 1800
        while core.task(task["id"])["status"] in {"READY", "QUEUED", "RUNNING"}:
            manager.tick()
            time.sleep(0.08)
            if time.monotonic() > deadline:
                raise TimeoutError(task["id"])
        result = core.task(task["id"])
        if result['status'] == 'SUCCESS':
            if result.get('computeWorker'):
                details=result['computeWorker']
                worker=manager.warm.workers[details['stage']+('-shared' if details.get('profile')=='shared' else '')]
                evidence=json.loads((worker.control/'validation-engine.json').read_text(encoding='utf8'))
                assert result['computeWorker']['pid']==evidence['runtimePid']
                (core.results/task['id']/'validation-engine.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf8')
            else:evidence = json.loads((core.results / task['id'] / 'validation-engine.json').read_text(encoding='utf8'))
            assert Path(evidence['kit']) == kit and evidence['runtimePid'] != os.getpid()
            assert Path(evidence['executable']) == kit / 'runtime/python.exe'
            spec = next(t for t in engine.configuration()[1]['tools'] if t['tool_code'] == args.tool)
            package = 'packages/' + ('cp' if spec['test_stage'] == 'CP' else spec['profile']) + '.pyz'
            assert result['receipt']['package'] == evidence['packages'][package]['sha256']
            registry = json.loads((core.results / task['id'] / 'engine-work/engines/registry.json').read_text(encoding='utf8'))
            assert Path(registry['runtime']).resolve() == kit / 'runtime/python.exe'
            for stage, name in [('CP', 'cp'), ('FT', spec['profile'])]:
                installed = registry['engines'][stage]
                expected = evidence['packages']['packages/' + name + '.pyz']['sha256']
                assert installed['sha256'] == engine.digest(installed['path']) == expected
            evidence['installedEngines'] = registry
            result['validationEngine'] = evidence
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result["status"] != "SUCCESS":
            raise RuntimeError(result.get("error", "real task failed"))
    finally:
        manager.close()


if __name__ == "__main__":
    main()
