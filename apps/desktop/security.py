from __future__ import annotations

import mimetypes
from pathlib import Path
from urllib.parse import unquote

from PySide6.QtCore import QFile, QIODevice, QUrl
from PySide6.QtWebEngineCore import QWebEngineUrlScheme, QWebEngineUrlSchemeHandler, QWebEngineUrlRequestInterceptor, QWebEnginePage

APP_URL = "studio://app/index.html"


def register_scheme():
    scheme = QWebEngineUrlScheme(b"studio")
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.Host)
    scheme.setFlags(QWebEngineUrlScheme.Flag.SecureScheme | QWebEngineUrlScheme.Flag.LocalScheme | QWebEngineUrlScheme.Flag.LocalAccessAllowed | QWebEngineUrlScheme.Flag.CorsEnabled | QWebEngineUrlScheme.Flag.FetchApiAllowed)
    QWebEngineUrlScheme.registerScheme(scheme)


def resource_path(root: Path, url: QUrl):
    if url.scheme() != "studio" or url.host() != "app" or url.hasQuery():
        raise ValueError("不可信资源")
    name = unquote(url.path()).lstrip("/") or "index.html"
    if "\\" in name or ":" in name or ".." in Path(name).parts:
        raise ValueError("路径越界")
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("资源不存在")
    return path


class Resources(QWebEngineUrlSchemeHandler):
    def __init__(self, root, parent):
        super().__init__(parent)
        self.root = root

    def requestStarted(self, job):
        try:
            path = resource_path(self.root, job.requestUrl())
            file = QFile(str(path), job)
            if not file.open(QIODevice.OpenModeFlag.ReadOnly):
                raise ValueError("无法读取资源")
            mime = {".js": "application/javascript", ".css": "text/css", ".html": "text/html"}.get(path.suffix) or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            job.reply(mime.encode("ascii"), file)
        except ValueError:
            job.fail(job.Error.RequestDenied)


class LocalOnly(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        url = info.requestUrl()
        allowed = (url.scheme() == "studio" and url.host() == "app") or url.toString() == "qrc:///qtwebchannel/qwebchannel.js" or url.scheme() in {"data", "blob"}
        if not allowed:
            info.block(True)


class TrustedPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, kind, is_main_frame):
        return is_main_frame and url.toString().split("#")[0] == APP_URL

    def createWindow(self, kind):
        return None
