import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine_support/desktop_client'))
from nce_desktop.local_engines import dependency_path


def test_bound_runtime_still_hashes_dependencies_and_rejects_other_roots(tmp_path, monkeypatch):
    runtime=tmp_path/'runtime';library=runtime/'Lib/site-packages';library.mkdir(parents=True)
    home=tmp_path/'task';(home/'runtime-packages').mkdir(parents=True)
    source=library/'reader.py';source.write_bytes(b'approved reader')
    record=dict(schema=4,python=list(sys.version_info[:2]),root=str(library),
                files={'reader.py':hashlib.sha256(source.read_bytes()).hexdigest()})
    manifest=home/'runtime-packages/manifest.json'
    manifest.write_text(json.dumps(record))
    monkeypatch.setattr(sys,'executable',str(runtime/'python.exe'))
    assert dependency_path(home)==library
    assert not (home/'runtime-packages/reader.py').exists()
    source.write_bytes(b'tampered reader')
    with pytest.raises(ValueError,match='依赖已改变'):dependency_path(home)
    record['root']=str(tmp_path/'unapproved')
    manifest.write_text(json.dumps(record))
    with pytest.raises(ValueError,match='当前固定环境'):dependency_path(home)


def test_bound_dependency_manifest_cannot_escape_library(tmp_path,monkeypatch):
    runtime=tmp_path/'runtime';library=runtime/'Lib/site-packages';library.mkdir(parents=True)
    home=tmp_path/'task';(home/'runtime-packages').mkdir(parents=True)
    external=runtime/'Lib/outside.py';external.write_bytes(b'outside')
    (home/'runtime-packages/manifest.json').write_text(json.dumps(dict(schema=4,
        python=list(sys.version_info[:2]),root=str(library),files={'../outside.py':hashlib.sha256(b'outside').hexdigest()})))
    monkeypatch.setattr(sys,'executable',str(runtime/'python.exe'))
    with pytest.raises(ValueError,match='依赖已改变'):dependency_path(home)
