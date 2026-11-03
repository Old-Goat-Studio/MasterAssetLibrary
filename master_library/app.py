# SPDX-License-Identifier: Apache-2.0
"""Starting the program."""
import json
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from . import APP_NAME, ICON_PATH
from .settings import Settings
from .version import BUILD, VERSION


def run(smoke_test: Path | None = None) -> int:
    QCoreApplication.setApplicationName(APP_NAME)
    QCoreApplication.setOrganizationName("")  # settings in .../Master Asset Library
    QCoreApplication.setApplicationVersion(VERSION)
    # Don't round 150 % monitors up to 200 %: scale exactly, per monitor.
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    settings = Settings(smoke_test / "settings" if smoke_test else None)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(ICON_PATH)))
    if sys.platform == "win32":  # its own taskbar button and icon, not Python's
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "OldGoatStudio.MasterAssetLibrary")

    from .main_window import MainWindow  # import after QApplication exists

    window = MainWindow(settings)
    window.show()
    if smoke_test is not None:
        return _smoke_test(app, window, smoke_test)
    return app.exec()


def _smoke_test(app: QApplication, window, folder: Path) -> int:
    """Check the window, write smoke_test.json and quit. Used to check a packaged program really
    starts (a windowed build has no console to print to)."""
    folder.mkdir(parents=True, exist_ok=True)
    app.processEvents()
    result = {
        "ok": window.windowTitle() == APP_NAME and window.isVisible(),
        "title": window.windowTitle(),
        "version": VERSION,
        "build": BUILD,
        "icon": ICON_PATH.is_file(),
        "frozen": bool(getattr(sys, "frozen", False)),
    }
    (folder / "smoke_test.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    QTimer.singleShot(0, window.close)
    app.exec()
    return 0 if result["ok"] else 1
