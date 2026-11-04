# SPDX-License-Identifier: Apache-2.0
"""The main window: the library's asset types on the left; the assets (found by a search, or a
tag) in the middle; the selected one on the right, shown or played above its details and its
files."""
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import APP_NAME
from . import library_format as lf
from .about import AboutDialog
from .details import DetailsDialog, licence_label
from .import_dialog import ImportDialog
from .importing import CollectResult, collect
from .player import AssetPlayer, choices
from .roles import texture_set
from .settings import Settings, projects_dir
from .split import SplitError
from .split_dialog import SplitDialog, can_split
from .themes import QSS_PREFIX, THEMES, ThemeApplier, qss_themes, theme_title

ROLE = Qt.ItemDataRole.UserRole
THUMB = 48
ALL_TYPES = ""   # the types list's first row: every type
ALL_TAGS = ""    # the tag filter's first choice: any tag
THUMBNAILS = (".png", ".jpg", ".jpeg")


def size_text(size: int) -> str:
    """'3.4 MB', '820 KB', '96 bytes'."""
    if size >= 1_000_000:
        return f"{size / 1e6:.1f} MB"
    if size >= 1_000:
        return f"{size / 1e3:.0f} KB"
    return f"{size} bytes"


# The licence filter: (label, which licences).
LICENCE_FILTERS = (
    ("Any licence", ()),
    ("Free to share (CC0, CC BY)", ("CC0-1.0", "CC-BY-4.0", "CC-BY-3.0")),
    ("Share-alike (CC BY-SA)", ("CC-BY-SA-4.0", "CC-BY-SA-3.0")),
    ("Purchased", (lf.PURCHASED,)),
    ("Own work", (lf.OWN_WORK,)),
    ("Needs a credit", ("credit",)),
)


def licence_matches(asset: lf.Asset, which: tuple[str, ...]) -> bool:
    if not which:
        return True
    if which == ("credit",):
        return lf.needs_credit(asset)
    return asset.licence in which


def matches(asset: lf.Asset, words: str, tag: str) -> bool:
    """Whether an asset is found by a search (every word somewhere in its name, description,
    tags, author, title, category or seller) and has the tag (if one is chosen)."""
    if tag and tag not in asset.tags:
        return False
    bought = asset.purchase or {}
    seller = f"{bought.get('seller', '')} {bought.get('product', '')}"
    text = " ".join([asset.name, asset.description, " ".join(asset.tags), asset.author,
                     asset.title, asset.category, seller]).lower()
    return all(w in text for w in words.lower().split())


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.setWindowTitle(APP_NAME)
        self.resize(1200, 760)
        self.themes = ThemeApplier(settings.dir)
        self.library: lf.Library | None = None
        self.library_error = ""
        self.assets: list[lf.Asset] = []
        self.unreadable: list[str] = []
        self._build()
        self._build_menus()
        if geometry := settings.get("geometry"):
            self.restoreGeometry(QByteArray.fromBase64(geometry.encode("ascii")))
        theme = settings.get("theme")
        if theme and not self.themes.apply(theme):
            settings.set("theme", None)  # (its file is gone)
        self._check_theme()
        self.open_library(settings.library_dir())

    # ---- the window -------------------------------------------------------------------------
    def _build(self) -> None:
        central = QWidget()
        outer = QVBoxLayout(central)
        bar = QHBoxLayout()
        self.title = QLabel()
        bar.addWidget(self.title, 1)
        self.import_button = QPushButton("Import…")
        self.import_button.clicked.connect(lambda: self.import_dialog())
        bar.addWidget(self.import_button)
        self.details_button = QPushButton("Details…")
        self.details_button.clicked.connect(self.edit_details)
        self.split_button = QPushButton("Split Pack…")
        self.split_button.setToolTip("A model holding many objects (a pack of trees, rocks…) "
                                     "made into one asset per object")
        self.split_button.clicked.connect(lambda: self.split_selected())
        bar.addWidget(self.split_button)
        self.remove_button = QPushButton("Remove")
        self.remove_button.clicked.connect(self.remove_selected)
        self.show_button = QPushButton("Show in Folder")
        self.show_button.clicked.connect(self.show_in_folder)
        for b in (self.details_button, self.remove_button, self.show_button):
            bar.addWidget(b)
        outer.addLayout(bar)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.types = QListWidget()
        self.types.setMaximumWidth(200)
        for key, label in [(ALL_TYPES, "Everything")] + [(k, v[0]) for k, v in lf.TYPES.items()]:
            item = QListWidgetItem(label)
            item.setData(ROLE, key)
            self.types.addItem(item)
        self.types.currentRowChanged.connect(lambda _r: self.show_list())
        split.addWidget(self.types)

        middle = QWidget()
        middle_layout = QVBoxLayout(middle)
        middle_layout.setContentsMargins(0, 0, 0, 0)
        find = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search names, descriptions, tags, authors…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _t: self.show_list())
        find.addWidget(self.search, 1)
        self.tag = QComboBox()
        self.tag.setToolTip("Only the assets with this tag")
        self.tag.currentIndexChanged.connect(lambda _i: self.show_list())
        find.addWidget(self.tag)
        self.licence_filter = QComboBox()
        self.licence_filter.setToolTip("Only the assets with these licences")
        for label, which in LICENCE_FILTERS:
            self.licence_filter.addItem(label, which)
        self.licence_filter.currentIndexChanged.connect(lambda _i: self.show_list())
        find.addWidget(self.licence_filter)
        middle_layout.addLayout(find)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Licence", "Size", "Tags"])
        self.tree.setIconSize(QSize(THUMB, THUMB))
        self.tree.setColumnWidth(0, 280)
        self.tree.itemSelectionChanged.connect(self.show_selected)
        self.tree.itemDoubleClicked.connect(lambda *_: self.edit_details())
        middle_layout.addWidget(self.tree, 1)
        split.addWidget(middle)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.player = AssetPlayer()
        right_layout.addWidget(self.player, 3)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        right_layout.addWidget(self.info)
        # The asset's files (below its licence): choosing one shows or plays it.
        self.files = QTreeWidget()
        self.files.setHeaderLabels(["File", "Size"])
        self.files.setRootIsDecorated(False)
        self.files.setAlternatingRowColors(True)
        self.files.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        header = self.files.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.files.setToolTip("Choose a file to see it, or a sound to play it")
        self.files.itemSelectionChanged.connect(self._file_chosen)
        right_layout.addWidget(self.files, 2)
        split.addWidget(right)
        split.setSizes([170, 560, 420])
        outer.addWidget(split, 1)
        self.setCentralWidget(central)
        self.types.setCurrentRow(0)
        self.setAcceptDrops(True)  # (files dropped on the window: Import, with them)

    def _build_menus(self) -> None:
        file = self.menuBar().addMenu("&File")
        import_ = file.addAction("&Import…")
        import_.setShortcut(QKeySequence("Ctrl+I"))
        import_.triggered.connect(lambda: self.import_dialog())
        collect = file.addAction("&Collect from a Midgard Project…")
        collect.triggered.connect(lambda: self.collect_dialog())
        file.addSeparator()
        folder = file.addAction("Library &Folder…")
        folder.triggered.connect(self.choose_library_dir)
        reload_ = file.addAction("&Reload")
        reload_.setShortcut(QKeySequence.StandardKey.Refresh)
        reload_.triggered.connect(self.refresh)
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
    def open_library(self, folder: Path) -> bool:
        """The library in a folder (made there if the folder is new or empty)."""
        folder = Path(folder)
        try:
            if not lf.is_library(folder) and folder.is_dir() and any(folder.iterdir()):
                raise lf.LibraryError(f"{folder} has other things in it and isn't a library: "
                                      "choose an empty folder, or one that is a library")
            self.library = lf.Library.open_or_create(folder)
            self.library_error = ""
        except (lf.LibraryError, OSError) as e:
            self.library, self.library_error = None, str(e)
        self.refresh()
        return self.library is not None

    def choose_library_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Library Folder", str(self.settings.library_dir()))
        if chosen and self.open_library(Path(chosen)):
            self.settings.set("library_dir", chosen)
        elif chosen:
            QMessageBox.warning(self, "Library Folder", self.library_error)
            self.open_library(self.settings.library_dir())

    def refresh(self) -> None:
        if self.library is None:
            self.assets, self.unreadable = [], []
            self.title.setText(f"No library: {self.library_error}")
        else:
            self.assets, self.unreadable = self.library.scan()
            n = len(self.assets)
            self.title.setText(f"{self.library.name}: {n} asset{'' if n == 1 else 's'}, "
                               f"{size_text(sum(a.size for a in self.assets))}  —  "
                               f"{self.library.root}")
        for b in (self.show_button, self.import_button):
            b.setEnabled(self.library is not None)
        for i in range(self.types.count()):
            item = self.types.item(i)
            key = item.data(ROLE)
            label = lf.TYPES[key][0] if key else "Everything"
            count = sum(1 for a in self.assets if not key or a.type == key)
            item.setText(label + (f"  ({count})" if count else ""))
        current = self.tag.currentData()
        self.tag.blockSignals(True)
        self.tag.clear()
        self.tag.addItem("Any tag", ALL_TAGS)
        for tag in sorted({t for a in self.assets for t in a.tags}):
            self.tag.addItem(tag, tag)
        self.tag.setCurrentIndex(max(0, self.tag.findData(current)))
        self.tag.blockSignals(False)
        self.show_list()

    def current_type(self) -> str:
        item = self.types.currentItem()
        return item.data(ROLE) if item else ALL_TYPES

    def shown_assets(self) -> list[lf.Asset]:
        type_ = self.current_type()
        which = tuple(self.licence_filter.currentData() or ())
        return [a for a in self.assets if (not type_ or a.type == type_)
                and matches(a, self.search.text(), self.tag.currentData() or ALL_TAGS)
                and licence_matches(a, which)]

    def show_list(self) -> None:
        """The assets of the chosen type that the search and tag find, in their folders (the
        type, then its kinds or albums)."""
        selected = self.selected()
        self.tree.blockSignals(True)
        self.tree.clear()
        folders: dict[str, QTreeWidgetItem] = {}
        everything = not self.current_type()
        for asset in self.shown_assets():
            parent = None
            group = " / ".join(p for p in (lf.TYPES[asset.type][0] if everything and
                                           asset.type in lf.TYPES else "",
                                           asset.category.replace("_", " ").capitalize())
                               if p)
            if group:
                if group not in folders:
                    folders[group] = QTreeWidgetItem(self.tree, [group])
                    folders[group].setExpanded(True)
                    folders[group].setFlags(Qt.ItemFlag.ItemIsEnabled)
                parent = folders[group]
            item = QTreeWidgetItem(parent or self.tree, [
                asset.name, licence_label(asset.licence), size_text(asset.size),
                ", ".join(asset.tags)])
            item.setData(0, ROLE, asset.id)
            if (icon := self.thumbnail(asset)) is not None:
                item.setIcon(0, icon)
            if lf.problems(asset, contents=False):  # (quick: the selected one is read)
                item.setForeground(0, Qt.GlobalColor.red)
            if selected and asset.id == selected.id:
                item.setSelected(True)
        self.tree.blockSignals(False)
        self.show_selected()

    def thumbnail(self, asset: lf.Asset) -> QIcon | None:
        """Its picture (a texture set's colour map; else its first picture)."""
        paths = [asset.folder / f["path"] for f in asset.files]
        colour = texture_set(paths).get("color") if asset.type == "textures" else None
        for path in ([colour] if colour else []) + paths:
            if path.suffix.lower() in THUMBNAILS and path.is_file():
                pixmap = QPixmap(str(path))
                if not pixmap.isNull():
                    return QIcon(pixmap.scaled(THUMB, THUMB, Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation))
        return None

    def selected(self) -> lf.Asset | None:
        items = self.tree.selectedItems()
        if not items:
            return None
        return lf.find(self.assets, items[0].data(0, ROLE))

    def select(self, asset_id: str) -> None:
        for item in self.tree.findItems("*", Qt.MatchFlag.MatchWildcard |
                                        Qt.MatchFlag.MatchRecursive):
            item.setSelected(item.data(0, ROLE) == asset_id)

    def show_selected(self) -> None:
        asset = self.selected()
        shown = self.player.asset
        if (asset.id if asset else None) != (shown.id if shown else None):
            self.player.show_asset(asset)
            self.show_files(asset)
        for b in (self.details_button, self.remove_button):
            b.setEnabled(asset is not None)
        self.split_button.setEnabled(asset is not None and can_split(asset))
        if asset is None:
            text = "Select an asset to see it." if self.library else ""
            if self.unreadable:
                text += "<br><br><b>Not read:</b><br>" + "<br>".join(self.unreadable)
            self.info.setText(text)
            return
        rows = [f"<b>{asset.name}</b> &nbsp; version {asset.version}"]
        if asset.description:
            rows.append(asset.description.replace("\n", "<br>"))
        rows.append(f"Licence: {licence_label(asset.licence)}")
        if lf.share_alike(asset):
            rows.append("<i>Share-alike: changed versions under the same licence.</i>")
        if asset.licence == lf.PURCHASED and asset.purchase:
            p = asset.purchase
            bought = ", ".join(x for x in (p.get("product"), f"from {p['seller']}"
                                           if p.get("seller") else "", p.get("date"),
                                           f"order {p['order']}" if p.get("order") else "")
                               if x)
            rows.append(f"Bought: {bought}")
            if p.get("licence_file"):
                rows.append(f"The seller's licence: {p['licence_file']}")
        if not lf.may_give_away(asset):
            rows.append("<i>Its original files may not be given away.</i>")
        for label, value in (("Author", asset.author), ("Title", asset.title),
                             ("Source", asset.source), ("Imported", asset.imported),
                             ("Tags", ", ".join(asset.tags))):
            if value:
                rows.append(f"{label}: {value}")
        if lf.needs_credit(asset):
            rows.append(f"Credit: {lf.credit(asset)}")
        rows.append(f"Files: {len(asset.files)}, {size_text(asset.size)}")
        if said := lf.problems(asset):
            rows.append("<span style='color:#d05050'>" + "<br>".join(said) + "</span>")
        self.info.setText("<br>".join(rows))

    def show_files(self, asset: lf.Asset | None) -> None:
        """The asset's files with their sizes: what can be shown or played first (a texture
        set's whole material, then models, sounds, fonts and pictures), then the rest, greyed."""
        self.files.blockSignals(True)
        self.files.clear()
        if asset is not None:
            found = choices(asset)
            labels = {path: label for label, _kind, path in found if path is not None}
            if any(kind == "material" for _l, kind, _p in found):
                item = QTreeWidgetItem(["Material (all maps)", ""])
                item.setData(0, ROLE, "")
                self.files.addTopLevelItem(item)
            order = {path: i for i, (_l, _k, path) in enumerate(found) if path is not None}
            for f in sorted(asset.files, key=lambda f: (
                    order.get(asset.folder / f["path"], len(found)), f["path"].lower())):
                path = asset.folder / f["path"]
                item = QTreeWidgetItem([labels.get(path, f["path"]),
                                        size_text(int(f.get("bytes", 0)))])
                item.setToolTip(0, f["path"])
                item.setData(0, ROLE, str(path))
                item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight |
                                      Qt.AlignmentFlag.AlignVCenter)
                if path not in labels:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                    for column in range(2):
                        item.setForeground(column, Qt.GlobalColor.gray)
                self.files.addTopLevelItem(item)
            if self.files.topLevelItemCount():
                self.files.topLevelItem(0).setSelected(True)
        self.files.blockSignals(False)

    def _file_chosen(self) -> None:
        items = self.files.selectedItems()
        if not items:
            return
        chosen = items[0].data(0, ROLE)
        if chosen:
            self.player.show_file(Path(chosen))
        else:
            self.player.show_material()

    # ---- what it does -----------------------------------------------------------------------
    def edit_details(self) -> None:
        asset = self.selected()
        if asset is not None and DetailsDialog(asset, self).exec():
            self.refresh()
            self.select(asset.id)

    def remove_selected(self, confirm: bool = True) -> bool:
        asset = self.selected()
        if asset is None:
            return False
        if confirm and QMessageBox.question(
                self, "Remove", f"Remove '{asset.name}' from the library? Its folder and files "
                "are deleted (this can't be undone). Projects' own copies of it stay as they "
                "are.") != QMessageBox.StandardButton.Yes:
            return False
        self.player.show_asset(None)
        lf.remove(asset)
        self.refresh()
        return True

    def show_in_folder(self) -> None:
        if self.library is None:
            return
        asset = self.selected()
        folder = asset.folder if asset else self.library.root
        if sys.platform == "win32":
            os.startfile(folder)  # noqa: S606 (the user's own folder, in Explorer)
        else:
            subprocess.Popen(["xdg-open", str(folder)])

    def import_dialog(self, sources=None, run: bool = True) -> ImportDialog | None:
        """Import (with files to begin with, if given): the new assets shown when it's done."""
        if self.library is None:
            return None
        type_ = self.current_type() or "models"
        dialog = ImportDialog(self.library, type_, self)
        if sources:
            dialog.add_sources(sources)
        if run and dialog.exec() and dialog.result and dialog.result.assets:
            self.refresh()
            self.select(dialog.result.assets[0].id)
        return dialog

    def split_selected(self, run: bool = True) -> SplitDialog | None:
        """Split Pack…: the selected model's objects made assets of their own."""
        asset = self.selected()
        if asset is None or self.library is None or not can_split(asset):
            return None
        try:
            dialog = SplitDialog(self.library, asset, self)
        except (SplitError, OSError, ValueError) as e:
            QMessageBox.warning(self, "Split Pack", f"It can't be split: {e}")
            return None
        if run and dialog.exec():
            self.player.show_asset(None)
            self.refresh()
            if dialog.result and dialog.result.assets:
                self.select(dialog.result.assets[0].id)
        return dialog

    def collect_dialog(self, project: Path | None = None) -> CollectResult | None:
        """A Midgard project's library assets collected into the Master."""
        if self.library is None:
            return None
        if project is None:
            chosen = QFileDialog.getExistingDirectory(
                self, "Collect from a Midgard Project (its folder)",
                str(projects_dir()))
            if not chosen:
                return None
            project = Path(chosen)
        try:
            result = collect(self.library, project)
        except (lf.LibraryError, OSError) as e:
            QMessageBox.warning(self, "Collect", f"Nothing collected: {e}")
            return None
        self.refresh()
        if result.collected:
            self.select(result.collected[0].id)
        lines = [result.summary()]
        for name, why in result.refused:
            lines.append(f"  {name}: {why}")
        self.last_collect_report = "\n".join(lines)
        if not getattr(self, "quiet", False):
            QMessageBox.information(self, "Collect", self.last_collect_report)
        return result

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt's name
        if event.mimeData().hasUrls() and self.library is not None:
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt's name
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            event.acceptProposedAction()
            self.import_dialog(paths)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt's name
        self.player.stop()
        self.settings.set("geometry", bytes(self.saveGeometry().toBase64()).decode("ascii"))
        super().closeEvent(event)
