from __future__ import annotations

import argparse
import logging
import multiprocessing
import os
from pathlib import Path
import sys


def main():
    project = Path(__file__).resolve().parents[2]
    if not getattr(sys, "frozen", False):
        sys.path.insert(0, str(project))
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", type=Path, default=Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "NCE/DesktopDataStudio-M0")
    parser.add_argument('--rendering',choices=['software','auto'],default='software' if os.name=='nt' else 'auto',help='Display backend; software avoids GPU/display-driver context switches')
    args = parser.parse_args()
    args.home.mkdir(parents=True, exist_ok=True)
    (args.home / "logs").mkdir(exist_ok=True)
    logging.basicConfig(filename=args.home / "logs/studio.log", encoding="utf-8", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from apps.desktop.rendering import configure_rendering
    configure_rendering(args.rendering)
    logging.info('Starting interface with rendering=%s',args.rendering)
    from PySide6.QtCore import QLockFile
    from PySide6.QtWidgets import QApplication, QMessageBox
    from apps.desktop.security import register_scheme
    register_scheme()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Desktop Data Studio")
    lock = QLockFile(str(args.home / "studio.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.warning(None, "工作区已打开", "另一个客户端正在使用此工作区，请切回已有窗口。")
        return 1
    from apps.desktop.shell import StudioWindow
    web = Path(sys._MEIPASS) / "web" if getattr(sys, "frozen", False) else project / "apps/web/dist"
    if not (web / "index.html").is_file():
        QMessageBox.critical(None, "缺少界面资源", "请先构建React界面，或解压完整便携包。")
        return 1
    window = StudioWindow(args.home, web)
    window.show()
    result = app.exec()
    lock.unlock()
    return result


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
