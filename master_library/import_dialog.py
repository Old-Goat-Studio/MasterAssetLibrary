# SPDX-License-Identifier: Apache-2.0
"""Import: files, a folder or a zip into the library, with what they are, their tags and their
licence. (Purchased assets' details come in step 5.)"""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import importing
from . import library_format as lf
from .details import EDITABLE_LICENCES, licence_label, parse_tags
from .roles import TEXTURE_ROLES, guess_role


class ImportForm(QWidget):
    """The asset's type, kind or album, name, description, tags, licence and credit."""

    def __init__(self, type_: str = "models", parent=None):
        super().__init__(parent)
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        self.type = QComboBox()
        for key, (label, _kinds) in lf.TYPES.items():
            self.type.addItem(label, key)
        self.type.setCurrentIndex(max(0, self.type.findData(type_)))
        self.type.currentIndexChanged.connect(lambda _i: self._kinds())
        form.addRow("Type", self.type)
        self.category = QComboBox()
        self.category_label = QLabel("Kind")
        form.addRow(self.category_label, self.category)
        self.name = QLineEdit()
        self.name.setPlaceholderText("What it is called in the library")
        form.addRow("Name", self.name)
        self.description = QPlainTextEdit()
        self.description.setMaximumHeight(70)
        form.addRow("Description", self.description)
        self.tags = QLineEdit()
        self.tags.setPlaceholderText("words to find it by, with commas between")
        form.addRow("Tags", self.tags)
        self.licence = QComboBox()
        for code in EDITABLE_LICENCES:
            self.licence.addItem(licence_label(code), code)
        self.licence.currentIndexChanged.connect(lambda _i: self._note())
        form.addRow("Licence", self.licence)
        self.author = QLineEdit()
        self.title = QLineEdit()
        self.title.setPlaceholderText("the work's own title, for its credit")
        self.source = QLineEdit()
        self.source.setPlaceholderText("where it came from (a web address)")
        form.addRow("Author", self.author)
        form.addRow("Title", self.title)
        form.addRow("Source", self.source)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setEnabled(False)
        form.addRow("", self.note)
        self._kinds()
        self._note()

    def _kinds(self) -> None:
        type_ = self.type.currentData()
        kinds = lf.TYPES[type_][1]
        self.category.clear()
        self.category.setEditable(type_ in lf.ALBUMS)
        if kinds:
            for k in kinds:
                self.category.addItem(k.capitalize(), k)
        elif type_ in lf.ALBUMS:
            self.category.lineEdit().setPlaceholderText("its album (empty: miscellaneous)")
        self.category_label.setText("Album" if type_ in lf.ALBUMS else "Kind")
        visible = bool(kinds) or type_ in lf.ALBUMS
        self.category.setVisible(visible)
        self.category_label.setVisible(visible)

    def _note(self) -> None:
        licence = lf.LICENCES[self.licence.currentData()]
        notes = ["Its author, and its title or source, are needed for its credit."
                 if licence.credit else "No credit is needed (naming the author is kind all "
                 "the same)."]
        if licence.share_alike:
            notes.append("Share-alike: a game that changes it must offer the changed asset "
                         "under the same licence.")
        self.note.setText(" ".join(notes))

    def type_(self) -> str:
        return self.type.currentData()

    def details(self) -> importing.Details:
        type_ = self.type_()
        category = self.category.currentText().strip() if type_ in lf.ALBUMS \
            else (self.category.currentData() or "")
        return importing.Details(
            category=category, description=self.description.toPlainText().strip(),
            tags=parse_tags(self.tags.text()), licence=self.licence.currentData(),
            author=self.author.text().strip(), source=self.source.text().strip(),
            title=self.title.text().strip())


class ImportDialog(QDialog):
    def __init__(self, library: lf.Library, type_: str = "models", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Into the Master Library")
        self.library = library
        self.result: importing.ImportResult | None = None
        self.last_report = ""
        self.quiet = False  # (tests: reports aren't shown)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Files (copied into the library: the originals stay where "
                                "they are)"))
        self.sources = QListWidget()
        self.sources.setMaximumHeight(110)
        layout.addWidget(self.sources)
        row = QHBoxLayout()
        for label, slot in (("Add Files…", self._add_files), ("Add Folder…", self._add_folder),
                            ("Add Zip…", self._add_zip)):
            button = QPushButton(label)
            button.clicked.connect(slot)
            row.addWidget(button)
        clear = QPushButton("Clear")
        clear.clicked.connect(self.sources.clear)
        clear.clicked.connect(self.refresh_pictures)
        row.addWidget(clear)
        layout.addLayout(row)
        self.form = ImportForm(type_)
        layout.addWidget(self.form)
        self.pictures_label = QLabel("Each picture's role (saved as the asset's name and its "
                                     "role; those not used are left out):")
        self.pictures_label.setWordWrap(True)
        self.pictures = QTableWidget(0, 2)
        self.pictures.setHorizontalHeaderLabels(["Picture", "Role"])
        self.pictures.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.pictures.verticalHeader().setVisible(False)
        layout.addWidget(self.pictures_label)
        layout.addWidget(self.pictures)
        self.form.type.currentIndexChanged.connect(lambda _i: self.refresh_pictures())
        self.refresh_pictures()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.addButton("Import", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.accepted.connect(lambda: self.do_import())
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(560, 620)

    # ---- the files ----------------------------------------------------------------------------
    def add_sources(self, paths) -> None:
        paths = [str(p) for p in paths]
        for p in paths:
            self.sources.addItem(p)
        if not self.form.name.text() and paths:  # (named after the first, to begin with)
            self.form.name.setText(importing.pretty(Path(paths[0]).stem))
        self.refresh_pictures()

    def _add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Files to import")
        self.add_sources(files)

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "A folder to import")
        if folder:
            self.add_sources([folder])

    def _add_zip(self) -> None:
        file, _ = QFileDialog.getOpenFileName(self, "A zip to import", "", "Zip files (*.zip)")
        if file:
            self.add_sources([file])

    def source_paths(self) -> list[Path]:
        return [Path(self.sources.item(i).text()) for i in range(self.sources.count())]

    # ---- a texture set's pictures -------------------------------------------------------------
    def refresh_pictures(self) -> None:
        """The pictures to give roles to (a texture import's), each with its guessed role."""
        texture = self.form.type_() == "textures"
        found = []
        if texture and self.sources.count():
            try:
                found = importing.images_in(self.source_paths())
            except (lf.LibraryError, OSError):
                found = []
        self.pictures.setRowCount(len(found))
        for row, rel in enumerate(found):
            item = QTableWidgetItem(rel)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.pictures.setItem(row, 0, item)
            role = guess_role(rel) or ("color" if len(found) == 1 else "")
            combo = QComboBox()
            for key, label in TEXTURE_ROLES.items():
                combo.addItem(label, key)
            combo.setCurrentIndex(combo.findData(role))
            self.pictures.setCellWidget(row, 1, combo)
        show = texture and bool(found)
        self.pictures.setVisible(show)
        self.pictures_label.setVisible(show)

    def roles(self) -> dict[str, str] | None:
        if self.form.type_() != "textures" or not self.pictures.rowCount():
            return None
        return {self.pictures.item(r, 0).text(): self.pictures.cellWidget(r, 1).currentData()
                for r in range(self.pictures.rowCount())}

    def set_role(self, picture: str, role: str) -> None:
        for r in range(self.pictures.rowCount()):
            if self.pictures.item(r, 0).text() == picture:
                combo = self.pictures.cellWidget(r, 1)
                combo.setCurrentIndex(combo.findData(role))

    # ---- importing ----------------------------------------------------------------------------
    def ask_split(self, models: int) -> bool:
        """A pack of several models: one asset, or one for each? (True: one each.)"""
        box = QMessageBox(QMessageBox.Icon.Question, "Import",
                          f"These files hold {models} models. Import them as one asset, or as "
                          "one asset for each model (each with its own textures, and the pack's "
                          "licence)?", parent=self)
        each = box.addButton(f"One for Each ({models})", QMessageBox.ButtonRole.YesRole)
        box.addButton("One Asset", QMessageBox.ButtonRole.NoRole)
        box.setDefaultButton(each)
        box.exec()
        return box.clickedButton() is each

    def do_import(self, split: bool | None = None) -> bool:
        type_ = self.form.type_()
        sources = self.source_paths()
        if split is None:
            models = importing.model_count(sources) if type_ in ("models", "objects") else 0
            split = models > 1 and self.ask_split(models)
        try:
            result = importing.import_assets(self.library.root, sources, type_,
                                             self.form.name.text(), self.form.details(),
                                             split=split, roles=self.roles())
        except (lf.LibraryError, OSError) as e:
            self._say(f"Not imported: {e}", warning=True)
            return False
        self.result = result
        if not result.assets:
            why = result.refused[0][1] if result.refused else "there is nothing to import"
            if result.skipped:
                why += f" ({importing.skipped_summary(result.skipped)})"
            self._say(f"Not imported: {why}", warning=True)
            return False
        if result.skipped or result.refused or result.warnings:
            lines = [result.summary()]
            if result.skipped:
                lines += ["", "Left out:"] + [f"  {rel}: {why}"
                                              for rel, why in result.skipped[:30]]
                if len(result.skipped) > 30:
                    lines.append(f"  … and {len(result.skipped) - 30} more")
            if result.warnings:
                lines += ["", "To know:"] + [f"  {w}" for w in result.warnings]
            self._say("\n".join(lines))
        self.accept()
        return True

    def _say(self, text: str, warning: bool = False) -> None:
        self.last_report = text
        if self.quiet:
            return
        box = QMessageBox(QMessageBox.Icon.Warning if warning else QMessageBox.Icon.Information,
                          "Import", text, parent=self)
        box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.exec()
