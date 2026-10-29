import json
from pathlib import Path
import pytest
from python_core.core import Core


def test_latest_batch_removal_reopen_and_history_are_independent(tmp_path):
    core=Core(tmp_path/'history')
    a=tmp_path/'a.txt';b=tmp_path/'b.txt';c=tmp_path/'c.txt'
    for p in [a,b,c]:p.write_text('original')
    old=core.register([str(a)])[0]
    task=core.create_task('demo-cp');task.update(demo=False,status='RUNNING',sourceId=old['id'],sourceSnapshot=old);core.save_task(task)
    current=core.register([str(b),str(c)])
    assert [f['id'] for f in core.bootstrap()['files']]==[f['id'] for f in current]
    core.remove_inputs([current[0]['id']])
    again=Core(core.root)
    assert [f['id'] for f in again.workspace_files()]==[current[1]['id']]
    assert again.task(task['id'])['status']=='RUNNING'
    assert again.registered_sources([old['id']])[old['id']]['path']==str(a)
    # A delayed removal from an older import must not clear a newer batch.
    again.register([str(a)])
    again.remove_inputs([current[1]['id']])
    assert [f['id'] for f in again.workspace_files()]==[old['id']]
    again.remove_inputs([old['id']])
    assert not Core(core.root).workspace_files()
    assert again.task(task['id'])['sourceId']==old['id']
    assert all(p.read_text()=='original' for p in [a,b,c])
    for invalid in [None,'all',[1],['x'*65],['x']*101]:
        with pytest.raises(ValueError):again.remove_inputs(invalid)


def test_real_history_filter_before_limit_and_empty_bootstrap(tmp_path):
    core=Core(tmp_path)
    real=core.create_task('demo-cp');real.update(demo=False,status='SUCCESS');core.save_task(real)
    for _ in range(110):core.create_task('demo-ft')
    assert [t['id'] for t in core.history(real_only=True)]==[real['id']]
    state=core.bootstrap()
    assert not state['files'] and state['demoRows']==0
    assert [t['id'] for t in state['tasks']]==[real['id']]
    assert not (core.root/'demo.sqlite').exists()


def test_saved_default_output_and_old_source_replay(tmp_path,monkeypatch):
    from python_core import engine
    kit=tmp_path/'kit';kit.mkdir();(kit/'manifest.json').write_text('{}')
    tool=dict(tool_code='TEST_CP',enabled=True,allowed_suffixes=['.txt'],display_name='CP',test_stage='CP',factory_code='HUAHONG',analysis_type='QUICK_CLEAN')
    monkeypatch.setattr(engine,'catalog',lambda:{'tools':[tool]})
    monkeypatch.setattr(engine,'configuration',lambda:(kit,{'version':'test'}))
    core=Core(tmp_path/'history');a=tmp_path/'a.txt';a.write_text('original')
    first=tmp_path/'output1';first.mkdir();second=tmp_path/'output2';second.mkdir()
    core.set_output_directory(str(first));source=core.register([str(a)])[0]
    task=core.create_task(source['id'],'TEST_CP')
    core.remove_inputs([source['id']]);core.set_output_directory(str(second))
    again=Core(core.root)
    assert again.settings()['outputDirectory']==str(second)
    assert again.task(task['id'])['outputParent']==str(first)
    assert again.create_task(source['id'],'TEST_CP')['outputParent']==str(second)
    second.rmdir()
    assert again.settings()['outputDirectory']==str(second)
    with pytest.raises((ValueError,OSError)):again.create_task(source['id'],'TEST_CP')


def test_new_session_resets_only_pending_list(tmp_path):
    core=Core(tmp_path/'history');source=tmp_path/'raw.txt';source.write_text('unchanged')
    output=tmp_path/'output';output.mkdir();core.set_output_directory(str(output))
    row=core.register([str(source)])[0];task=core.create_task('demo-cp')
    before=core.settings();core.reset_inputs();again=Core(core.root)
    assert again.workspace_files()==[] and again.settings()['inputIds']==[]
    assert again.settings()['inputDirectory']==before['inputDirectory']
    assert again.settings()['outputDirectory']==str(output)
    assert again.task(task['id'])==task
    assert again.registered_sources([row['id']])[row['id']]==row
    assert source.read_text()=='unchanged'


def test_hidden_old_inputs_remain_protected_during_export(tmp_path):
    core=Core(tmp_path/'history');old=tmp_path/'old';old.mkdir()
    source=core.register([str(old)])[0];core.reset_inputs()
    with core.connect() as con:
        for i in range(1005):
            con.execute('INSERT INTO sources VALUES (?,?)',(str(i),json.dumps(dict(path=str(tmp_path/f'item{i}'),demo=False,folder=False))))
    assert not core.workspace_files()
    assert len(core.protected_sources())==1006
    assert any(s['path']==str(old) and s['folder'] for s in core.protected_sources())
    assert source['id'] in core.registered_sources([source['id']])
