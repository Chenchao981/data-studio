from __future__ import annotations

import logging
import time
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl, Qt, QEvent
from PySide6.QtGui import QColor, QIcon, QPixmap, QPainter
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QWidget, QStackedWidget, QVBoxLayout, QLabel, QPushButton

from python_core.core import Core
from python_core.tasks import TaskManager
from .security import Resources, LocalOnly, TrustedPage, APP_URL
from .bridge import Bridge
from .rendering import RecoveryBudget


class LocalView(QWebEngineView):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setAcceptDrops(True)
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, receiver, event):
        # WebEngine's render child receives OS drops instead of the outer view.
        if event.type() in {QEvent.Type.DragEnter, QEvent.Type.DragMove, QEvent.Type.Drop} and isinstance(receiver, QWidget) and (receiver is self or self.isAncestorOf(receiver)):
            if event.type() == QEvent.Type.Drop:
                self.dropEvent(event)
            else:
                self.dragEnterEvent(event)
            return True
        return super().eventFilter(receiver, event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and all(u.isLocalFile() for u in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls and all(u.isLocalFile() for u in urls):
            self.window.bridge.import_paths([u.toLocalFile() for u in urls])
            event.acceptProposedAction()
        else:
            event.ignore()


class StudioWindow(QMainWindow):
    def __init__(self, root: Path, web: Path):
        super().__init__()
        self.setWindowTitle("Desktop Data Studio · 本地 CP / FT 分析")
        self.setMinimumSize(920, 620)
        area = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1500, area.width()-50), min(980, area.height()-60))
        self.core = Core(root)
        self.core.reset_inputs()
        self._closing=False
        self._page_ready=False
        self._pending_probe=None
        self._loading_since=None
        self._probe_serial=0
        self._recovery_budget=RecoveryBudget()
        self._observed_screens=set()
        self._screen_bound=False
        self.tasks = TaskManager(self.core)
        self.profile = QWebEngineProfile(self)  # Off-the-record; no disk browser cache.
        self.profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        self.resources = Resources(web, self.profile)
        self.profile.installUrlSchemeHandler(b"studio", self.resources)
        self.interceptor = LocalOnly(self.profile)
        self.profile.setUrlRequestInterceptor(self.interceptor)
        self.profile.downloadRequested.connect(lambda item: item.cancel())
        self.view = LocalView(self)
        self.page = TrustedPage(self.profile, self.view)
        self.view.setPage(self.page)
        self.page.setBackgroundColor(QColor("#f6f8fc"))
        settings = self.page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, False)
        self.channel = QWebChannel(self.page)
        self.bridge = Bridge(self.core, self.tasks, self, lambda: self.page.url().toString().split("#")[0] == APP_URL)
        self.channel.registerObject("studio", self.bridge)
        self.page.setWebChannel(self.channel)
        self.surface=QStackedWidget(self)
        self.surface.addWidget(self.view)
        self.recovery_panel=QWidget(self.surface)
        self.recovery_panel.setStyleSheet('background:#f6f8fc;color:#25354d;font-family:"Microsoft YaHei UI";font-size:14px;')
        layout=QVBoxLayout(self.recovery_panel);layout.addStretch()
        self.recovery_message=QLabel();self.recovery_message.setAlignment(Qt.AlignmentFlag.AlignCenter);self.recovery_message.setWordWrap(True)
        self.recovery_button=QPushButton('重新载入界面');self.recovery_button.setFixedWidth(180)
        self.recovery_button.setMinimumHeight(42)
        self.recovery_button.setStyleSheet('QPushButton{background:#3376ed;color:white;border:0;border-radius:7px;padding:10px;} QPushButton:disabled{background:#96b8f5;}')
        self.recovery_button.clicked.connect(self.reload_renderer)
        layout.addWidget(self.recovery_message);layout.addWidget(self.recovery_button,alignment=Qt.AlignmentFlag.AlignCenter);layout.addStretch()
        self.surface.addWidget(self.recovery_panel)
        self.setCentralWidget(self.surface)
        self.recovery_timer=QTimer(self);self.recovery_timer.setSingleShot(True);self.recovery_timer.setInterval(500)
        self.recovery_timer.timeout.connect(self.reload_renderer)
        self.page.renderProcessTerminated.connect(self.renderer_terminated)
        self.view.loadStarted.connect(self.load_started)
        self.view.loadFinished.connect(self.load_finished)
        self.display_timer=QTimer(self);self.display_timer.setSingleShot(True);self.display_timer.setInterval(160)
        self.display_timer.timeout.connect(self.refresh_display)
        for screen in QApplication.screens():self.observe_screen(screen)
        QApplication.instance().screenAdded.connect(self.observe_screen)
        self.health_timer=QTimer(self);self.health_timer.setInterval(5000);self.health_timer.timeout.connect(self.check_renderer);self.health_timer.start()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(150)
        self.view.load(QUrl(APP_URL))
        icon = QPixmap(64, 64)
        icon.fill(QColor("#3376ed"))
        painter = QPainter(icon)
        painter.setPen(Qt.GlobalColor.white)
        font = painter.font(); font.setPixelSize(30); font.setBold(True); painter.setFont(font)
        painter.drawText(icon.rect(), Qt.AlignmentFlag.AlignCenter, "DS")
        painter.end()
        self.setWindowIcon(QIcon(icon))

    def showEvent(self,event):
        super().showEvent(event)
        if not self._screen_bound and self.windowHandle():
            self.windowHandle().screenChanged.connect(self.display_changed)
            self._screen_bound=True
            self.display_changed()

    def event(self,event):
        if event.type()==QEvent.Type.DevicePixelRatioChange and hasattr(self,'display_timer'):
            self.display_changed()
        return super().event(event)

    def observe_screen(self,screen):
        if self._closing or screen in self._observed_screens:return
        self._observed_screens.add(screen)
        screen.availableGeometryChanged.connect(self.display_changed)
        screen.geometryChanged.connect(self.display_changed)
        screen.logicalDotsPerInchChanged.connect(self.display_changed)

    def display_changed(self,*_):
        if not self._closing:self.display_timer.start()

    def refresh_display(self):
        if self._closing:return
        screen=self.windowHandle().screen() if self.windowHandle() else QApplication.primaryScreen()
        if screen is None:return
        area=screen.availableGeometry()
        width=max(360,area.width()-24);height=max(320,area.height()-50)
        self.setMinimumSize(min(920,width),min(620,height))
        if not self.isMaximized() and not self.isMinimized():
            self.resize(min(self.width(),width),min(self.height(),height))
            frame=self.frameGeometry()
            self.move(max(area.left(),min(frame.x(),area.right()-frame.width()+1)),max(area.top(),min(frame.y(),area.bottom()-frame.height()+1)))
        # Repaint after the screen/DPI settles. Never reload or freeze the page
        # during resize: selected inputs and running jobs remain intact.
        self.view.update()
        logging.info('Display settled: size=%sx%s dpr=%s',area.width(),area.height(),screen.devicePixelRatio())

    def show_recovery(self,message):
        self.recovery_message.setText(message+'\n\n后台清洗任务不会重新提交；历史记录和输入文件仍然保留。')
        self.recovery_button.setEnabled(True)
        self.surface.setCurrentWidget(self.recovery_panel)

    def renderer_terminated(self,status,exit_code):
        if self._closing:return
        self._page_ready=False;self._pending_probe=None;self._loading_since=None
        logging.error('Interface renderer terminated: status=%s code=%s',status,exit_code)
        self.show_recovery('显示界面发生异常，正在尝试恢复。')
        self.recovery_timer.stop()
        if self._recovery_budget.take():
            self.recovery_button.setEnabled(False)
            self.recovery_timer.start()
        else:self.show_recovery('界面连续出现异常，请点击下方按钮重新载入。')

    def reload_renderer(self):
        if self._closing:return
        self.recovery_timer.stop()
        self._pending_probe=None;self._probe_serial+=1
        self.recovery_button.setEnabled(False)
        self.recovery_message.setText('正在恢复显示界面…\n\n后台任务继续执行，请稍候。')
        self.surface.setCurrentWidget(self.recovery_panel)
        self.view.load(QUrl(APP_URL))

    def load_started(self):
        self._page_ready=False;self._pending_probe=None;self._probe_serial+=1
        self._loading_since=time.monotonic()

    def load_finished(self,ok):
        if self._closing:return
        self._page_ready=ok
        self._loading_since=None
        if ok:self.surface.setCurrentWidget(self.view);self.view.update()
        else:self.show_recovery('界面未能正常加载，可以重新载入；无需重新清洗数据。')

    def check_renderer(self):
        if self._closing or self.isMinimized() or not self.isVisible():return
        if not self._page_ready:
            if self._loading_since is not None and time.monotonic()-self._loading_since>20:
                self._loading_since=None
                self.show_recovery('界面加载时间较长，请重新载入；后台任务不受影响。')
            return
        if self._pending_probe is not None:
            if time.monotonic()-self._pending_probe[1]>15:
                logging.error('Interface heartbeat timed out')
                self._page_ready=False
                self.show_recovery('界面暂时没有响应，可尝试重新载入。')
            return
        self._probe_serial+=1;serial=self._probe_serial
        self._pending_probe=(serial,time.monotonic())
        def acknowledged(state):
            if not self._closing and self._pending_probe and self._pending_probe[0]==serial and state is True:
                self._pending_probe=None
        self.page.runJavaScript("document.readyState==='complete' && !!document.getElementById('root')?.firstElementChild",acknowledged)

    def tick(self):
        try:
            if self.tasks.tick():
                self.bridge.changed.emit()
        except Exception:
            logging.exception("Task lifecycle error")

    def closeEvent(self, event):
        if self.tasks.active or self.tasks.waiting:
            answer = QMessageBox.question(self, "退出工作台", "退出会停止当前分析并取消等待任务，历史仍保留。是否退出？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore(); return
        self._closing=True
        self.timer.stop();self.health_timer.stop();self.display_timer.stop();self.recovery_timer.stop()
        self.bridge.close()
        self.tasks.close()
        self.page.setWebChannel(None)
        self.view.stop()
        event.accept()
