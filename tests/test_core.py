import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from python_core.core import Core
from python_core.tasks import TaskManager


@pytest.fixture
def core(tmp_path):
    return Core(tmp_path / "工作区")


def test_bounded_preview_sort_search_filter(core):
    request = dict(dataset="demo_clean", start=0, end=100, search="DEMO-2", sort=[dict(colId="bv", sort="desc")], filters={"bv": dict(type="greaterThan", filter=600)})
    first = core.preview(request)
    second = core.preview({**request, "start": 100, "end": 200})
    assert 100 < first["total"] < 25000
    assert all(row["lot"] == "DEMO-2" and row["bv"] > 600 for row in first["rows"])
    assert first["rows"][-1]["bv"] >= second["rows"][0]["bv"]
    assert len({r["id"] for r in first["rows"]+second["rows"]}) == 200
    assert len(core.preview(dict(dataset="demo_raw", start=99990, end=100090))["rows"]) == 10


@pytest.mark.parametrize("patch", [dict(start=-1), dict(end=10000), dict(dataset="C:/secret.csv"), dict(sort=[dict(colId='id; DROP TABLE demo', sort='asc')]), dict(filters={"bv": dict(type="greaterThan", filter="1 OR 1=1")}), dict(filters={"bad": {}})])
def test_preview_rejects_invalid_queries(core, patch):
    with pytest.raises(ValueError):
        core.preview(dict(dict(dataset="demo_clean", start=0, end=100), **patch))


def test_histogram_reconciles_to_full_population(core):
    all_rows = core.chart("bv")
    lot = core.chart("leakage", "DEMO-3")
    assert all_rows["count"] == 100000 and lot["count"] == 25000
    for data in [all_rows, lot]:
        assert sum(b["count"] for b in data["histogram"]) == data["count"]
        assert data["min"] <= data["mean"] <= data["max"]
        assert len(data["points"]) <= 2000
    assert all((p[0]-1)%4 == 2 for p in lot["points"])


def test_register_100_and_preserve_unknown_identity(core, tmp_path):
    paths=[]
    for i in range(100):
        path=tmp_path/f"real_CP_{i}.csv"
        path.write_text("must remain untouched", encoding="utf8")
        paths.append(str(path))
    result=core.register(paths)
    assert len(result)==100 and all(f["kind"]=="UNKNOWN" and not f["demo"] for f in result)
    assert core.register(paths)[0]["id"]==result[0]["id"]
    assert len(core.files())==103
    with pytest.raises(ValueError):core.register(paths+paths)
    with pytest.raises(ValueError):core.create_task("../../file")
    assert Path(paths[0]).read_text()=="must remain untouched"


def test_persistent_settings_history_and_recovery(core):
    core.save_settings({"theme":"dark"})
    t=core.create_task("demo-cp")
    t["status"]="RUNNING";core.save_task(t)
    again=Core(core.root);again.recover()
    assert again.settings()["theme"]=="dark"
    assert again.task(t["id"])["status"]=="CANCELLED"
    assert again.history("Wafer")[0]["id"]==t["id"]
    with pytest.raises(ValueError):again.save_settings({"output":"C:/"})


def wait(manager, predicate, timeout=15):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        manager.tick()
        if predicate():return
        time.sleep(.08)
    raise AssertionError("Task timeout")


def test_process_success_failure_cancel_export_integrity(core):
    manager=TaskManager(core)
    try:
        task=core.create_task("demo-cp");manager.start(task["id"])
        wait(manager,lambda:core.task(task["id"])["status"]=="SUCCESS")
        path=core.output(task["id"])
        assert "NOT_PRODUCTION_DATA" in path.read_text(encoding="utf-8-sig")
        path.write_text("changed")
        with pytest.raises(ValueError):core.output(task["id"])
        failed=core.create_task("demo-fail");manager.start(failed["id"])
        wait(manager,lambda:core.task(failed["id"])["status"]=="FAILED")
        assert "模拟格式冲突" in core.task(failed["id"])["error"]
        cancelled=core.create_task("demo-ft");manager.start(cancelled["id"])
        wait(manager,lambda:core.task(cancelled["id"])["status"]=="RUNNING")
        manager.cancel(cancelled["id"])
        wait(manager,lambda:core.task(cancelled["id"])["status"]=="CANCELLED")
        with pytest.raises(ValueError):manager.start(failed["id"])
    finally:manager.close()


def test_close_cancels_only_owned_simulations(core):
    manager=TaskManager(core)
    tasks=[core.create_task("demo-ft") for _ in range(2)]
    for task in tasks:manager.start(task["id"])
    manager.tick();process=manager.active[1]
    manager.close()
    assert all(core.task(t["id"])["status"]=="CANCELLED" for t in tasks)
    assert manager.active is None and not manager.waiting
