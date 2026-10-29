import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QCoreApplication, QUrl
from apps.desktop.security import resource_path
from apps.desktop.bridge import Bridge
from python_core.core import Core
from python_core.tasks import TaskManager


def test_resources_are_confined_to_dist(tmp_path):
    (tmp_path/"index.html").write_text("local")
    assert resource_path(tmp_path,QUrl("studio://app/index.html"))==tmp_path/"index.html"
    for value in ["studio://app/%2e%2e/private", "studio://other/index.html", "file:///C:/Windows/win.ini", "studio://app/index.html?path=secret", "studio://app/C:%5csecret"]:
        with pytest.raises(ValueError):resource_path(tmp_path,QUrl(value))


def test_bridge_denies_untrusted_page_and_unknown_methods(tmp_path):
    app=QCoreApplication.instance() or QCoreApplication([])
    core=Core(tmp_path);manager=TaskManager(core)
    bridge=Bridge(core,manager,None,lambda:False)
    replies=[];bridge.response.connect(lambda rid,r:replies.append(json.loads(r)))
    bridge.request("1","bootstrap","{}")
    assert not replies[-1]["ok"] and "可信" in replies[-1]["error"]
    bridge.trusted=lambda:True
    bridge.request("2","readFile",'{"path":"C:/secret"}')
    assert not replies[-1]["ok"]
    bridge.request("3","bootstrap","[]")
    assert not replies[-1]["ok"]
    bridge.close();manager.close()
