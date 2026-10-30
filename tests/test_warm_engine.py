"""A loaded worker must never bypass per-job engine integrity checks."""
import json,queue,threading
from types import SimpleNamespace
from python_core import engine


def test_tampering_rejected_before_warm_dispatch(tmp_path,monkeypatch):
    kit=tmp_path/'kit';kit.mkdir();package=kit/'cp.pyz';package.write_bytes(b'pinned')
    manifest={'files':{'cp.pyz':engine.digest(package)},'tools':[{'tool_code':'clean','test_stage':'CP','analysis_type':'QUICK_CLEAN','profile':'native'}]}
    (kit/'manifest.json').write_text(json.dumps(manifest),encoding='utf8')
    monkeypatch.setattr(engine,'engine_root',lambda:kit)
    task={'id':'task','engineHash':engine.digest(kit/'manifest.json'),'toolCode':'clean'}
    def forbidden(*args):raise AssertionError('Tampered package reached a loaded worker')
    warm=SimpleNamespace(workers={'CP':SimpleNamespace(run=forbidden)})
    package.write_bytes(b'tampered')
    messages=queue.Queue();engine.run_real(task,tmp_path,messages,threading.Event(),warm)
    outcome=messages.get_nowait()
    assert outcome['status']=='FAILED' and '校验失败' in outcome['error']
    assert not (tmp_path/'task/outcome.json').exists()


def test_cancelled_job_cannot_reach_warm_worker(tmp_path,monkeypatch):
    kit=tmp_path/'kit';kit.mkdir();(kit/'cp.pyz').write_bytes(b'pinned')
    manifest={'files':{'cp.pyz':engine.digest(kit/'cp.pyz')}}
    (kit/'manifest.json').write_text(json.dumps(manifest),encoding='utf8')
    monkeypatch.setattr(engine,'engine_root',lambda:kit)
    event=threading.Event();event.set();messages=queue.Queue()
    engine.run_real({'id':'cancelled','engineHash':engine.digest(kit/'manifest.json')},tmp_path,messages,event)
    assert messages.get_nowait()['status']=='CANCELLED'
