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
    if smoke_test is not None:  # (its own library, never the user's)
        settings.set("library_dir", str(smoke_test / "library"))
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


def _model_loads(app: QApplication, window, folder: Path) -> bool:
    """Whether the player loads a model (a one-triangle glTF): Qt's glTF loader is there."""
    import struct
    import time

    positions = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    doc = json.dumps({
        "asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}], "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "buffers": [{"byteLength": 36}], "bufferViews": [{"buffer": 0, "byteLength": 36}],
        "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3",
                       "min": [0, 0, 0], "max": [1, 1, 0]}]}).encode()
    doc += b" " * (-len(doc) % 4)
    body = (struct.pack("<II", len(doc), 0x4E4F534A) + doc +
            struct.pack("<II", 36, 0x004E4942) + positions)
    glb = folder / "triangle.glb"
    glb.write_bytes(struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body)
    window.player.show_file(glb)
    root = window.player.scene_root()
    if root is None:
        return False
    end = time.monotonic() + 10
    while root.property("status") == 0 and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)
    return root.property("status") == 1  # (RuntimeLoader.Success)


def _smoke_test(app: QApplication, window, folder: Path) -> int:
    """Check the window, write smoke_test.json and quit. Used to check a packaged program really
    starts (a windowed build has no console to print to)."""
    folder.mkdir(parents=True, exist_ok=True)
    app.processEvents()
    model = _model_loads(app, window, folder)
    result = {
        "ok": window.windowTitle() == APP_NAME and window.isVisible() and
        window.library is not None and window.player._scene_view() is not None and model,
        "title": window.windowTitle(),
        "version": VERSION,
        "build": BUILD,
        "icon": ICON_PATH.is_file(),
        "library": window.library is not None,
        "player_3d": window.player._scene_view() is not None,
        "player_3d_error": window.player.scene_error,
        "model_loads": model,
        "frozen": bool(getattr(sys, "frozen", False)),
    }
    (folder / "smoke_test.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    QTimer.singleShot(0, window.close)
    app.exec()
    return 0 if result["ok"] else 1
