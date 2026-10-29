import zipfile
import pytest
from python_core.core import Core
from python_core.engine import digest
from python_core.result_index import index_artifacts
from python_core.results import details,directory,export_folder
from python_core.viewers import Viewers


def result(tmp_path, *, legacy=False, different=False):
    core=Core(tmp_path/'home');task=core.create_task('demo-cp')
    folder=core.results/task['id'];files=folder/'files';files.mkdir(parents=True)
    csv=files/'LOT_cleaned_20260101.csv';csv.write_text('Lot_ID,Wafer_ID,Bin,V\nLOT,001,1,0.00000001\n',encoding='utf8')
    archive=folder/'result.zip'
    with zipfile.ZipFile(archive,'w') as z:z.writestr(csv.name, csv.read_bytes() if not different else b'Lot_ID,Wafer_ID,Bin,V\nLOT,002,2,9\n')
    # Older previews contain both archive and direct rows. Deliberately use a
    # distinct artifact label during indexing to reproduce that persisted shape.
    tables=index_artifacts(folder,[(('legacy/' if legacy else 'files/')+csv.name,csv),('result.zip',archive)])
    if legacy:tables[0]['name']='files/'+csv.name
    artifacts=[{'name':name,'path':str(path),'sha256':digest(path)} for name,path in [('files/'+csv.name,csv),('result.zip',archive)]]
    task.update(status='SUCCESS',demo=False,finished='2026-01-01T01:02:03+00:00',parameters={'stage':'CP','operation':'QUICK_CLEAN'},output=str(archive),sha256=digest(archive),artifacts=artifacts,tables=tables,previewHash=digest(folder/'preview.sqlite'))
    core.save_task(task);return core,task,csv


def test_result_details_uses_only_history_even_without_preview(tmp_path, monkeypatch):
    core,task,csv=result(tmp_path,legacy=True)
    (core.results/task['id']/'preview.sqlite').unlink()
    def unexpected(*args, **kwargs):raise AssertionError('Result overview read output contents')
    monkeypatch.setattr(core,'real_preview',unexpected)
    monkeypatch.setattr(core,'artifact',unexpected)
    monkeypatch.setattr(zipfile,'ZipFile',unexpected)
    info=details(core,task['id'])
    assert info=={'directory':str(csv.parent),'files':[csv.name]}
    assert len(core.task(task['id'])['tables'])==2


def test_result_details_prefers_published_folder_and_rejects_escape(tmp_path):
    core,task,csv=result(tmp_path)
    published=tmp_path/'saved';published.mkdir()
    task['publishedDirectory']=str(published);core.save_task(task)
    assert details(core,task['id'])['directory']==str(published)
    published.rmdir()
    assert details(core,task['id'])['directory']==str(csv.parent)
    task['artifacts'][0]['path']=str(tmp_path/'outside.csv');core.save_task(task)
    with pytest.raises(ValueError,match='路径'):details(core,task['id'])


def test_index_dedup_requires_equal_content(tmp_path):
    core,task,_=result(tmp_path/'equal');assert len(task['tables'])==1
    core,task,_=result(tmp_path/'different',different=True);assert len(task['tables'])==2


def test_export_original_files_collision_and_tamper(tmp_path):
    core,task,csv=result(tmp_path);parent=tmp_path/'export';parent.mkdir()
    first=export_folder(core,task['id'],parent);second=export_folder(core,task['id'],parent)
    from pathlib import Path
    assert first!=second
    assert (Path(first)/csv.name).read_bytes()==csv.read_bytes()
    assert len(list(Path(first).iterdir()))==1
    with pytest.raises(ValueError):export_folder(core,task['id'],core.root)
    csv.write_text('changed')
    with pytest.raises(ValueError):export_folder(core,task['id'],parent)


def test_viewer_rejects_demo_and_ft_before_launch(tmp_path):
    core=Core(tmp_path);task=core.create_task('demo-cp');viewers=Viewers(core)
    with pytest.raises(ValueError,match='CP清洗'):viewers.open(task['id'])
    viewers.close()
