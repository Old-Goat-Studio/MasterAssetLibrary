# SPDX-License-Identifier: Apache-2.0
"""The main window: menus, and (from step 3) the library's types, files and player."""
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence
from PySide6.QtWidgets import QFileDialog, QLabel, QMainWindow

from . import APP_NAME
from .about import AboutDialog
from .settings import Settings
from .themes import QSS_PREFIX, THEMES, ThemeApplier, qss_themes, theme_title


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.setWindowTitle(APP_NAME)
        self.resize(1100, 700)
        self.themes = ThemeApplier(settings.dir)

        self.place = QLabel()
        self.place.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.place.setWordWrap(True)
        self.setCentralWidget(self.place)
        self._show_place()

        self._build_menus()
        if geometry := settings.get("geometry"):
            self.restoreGeometry(QByteArray.fromBase64(geometry.encode("ascii")))
        theme = settings.get("theme")
        if theme and not self.themes.apply(theme):
            settings.set("theme", None)  # (its file is gone)
        self._check_theme()

    # ---- menus ------------------------------------------------------------------------------
    def _build_menus(self) -> None:
        file = self.menuBar().addMenu("&File")
        folder = file.addAction("Library &Folder…")
        folder.triggered.connect(self.choose_library_dir)
        file.addSeparator()
        quit_ = file.addAction("E&xit")
        quit_.setShortcut(QKeySequence.StandardKey.Quit)
        quit_.triggered.connect(self.close)

        view = self.menuBar().addMenu("&View")
        self.theme_menu = view.addMenu("&Themes")
        self.theme_group = QActionGroup(self)
        self.theme_group.setExclusive(True)
        self.theme_actions: dict[str, QAction] = {}
        for key, (label, _scheme) in THEMES.items():
            self._add_theme(key, label)
        self.theme_menu.addSeparator()
        for name in qss_themes(self.settings.dir):
            self._add_theme(QSS_PREFIX + name, theme_title(name))

        help_ = self.menuBar().addMenu("&Help")
        about = help_.addAction(f"&About {APP_NAME}")
        about.triggered.connect(lambda: AboutDialog(self).exec())

    def _add_theme(self, key: str, label: str) -> None:
        action = self.theme_menu.addAction(label)
        action.setCheckable(True)
        action.setData(key)
        action.triggered.connect(lambda _checked=False, k=key: self.set_theme(k))
        self.theme_group.addAction(action)
        self.theme_actions[key] = action

    def set_theme(self, key: str) -> None:
        if self.themes.apply(key):
            self.settings.set("theme", key)
        self._check_theme()

    def _check_theme(self) -> None:
        current = self.settings.get("theme")
        for key, action in self.theme_actions.items():
            action.setChecked(key == current)

    # ---- the library ------------------------------------------------------------------------
    def _show_place(self) -> None:
        self.place.setText(f"Your library is in\n{self.settings.library_dir()}\n\n"
                           "It's empty for now: importing comes in the next updates.")

    def choose_library_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Library Folder", str(self.settings.library_dir()))
        if chosen:
            self.settings.set("library_dir", chosen)
            self._show_place()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt's name
        self.settings.set("geometry", bytes(self.saveGeometry().toBase64()).decode("ascii"))
        super().closeEvent(event)
