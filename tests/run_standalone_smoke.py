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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "engine_support"), str(ROOT / "engine_support" / "backend"), str(ROOT / "engine_support" / "desktop_client")]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--tool", required=True)
    parser.add_argument("--home", required=True, type=Path)
    parser.add_argument("--kit", required=True, type=Path)
    args = parser.parse_args()
    os.environ["STUDIO_VALIDATION_ENGINE_KIT"] = str(args.kit.resolve())

    from python_core import engine
    from python_core.core import Core
    from python_core.tasks import TaskManager

    engine.engine_root = lambda: args.kit.resolve()
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
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result["status"] != "SUCCESS":
            raise RuntimeError(result.get("error", "real task failed"))
    finally:
        manager.close()


if __name__ == "__main__":
    main()
