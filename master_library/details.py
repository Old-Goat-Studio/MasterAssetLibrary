# SPDX-License-Identifier: Apache-2.0
"""An asset's details, edited: its name, description, tags, licence and credit. (Where a
purchased asset was bought comes in step 5.)"""
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
)

from . import library_format as lf

EDITABLE_LICENCES = [k for k in lf.LICENCES if k != lf.PURCHASED]


def licence_label(code: str) -> str:
    licence = lf.LICENCES.get(code)
    return licence.name if licence else (code or "none")


def parse_tags(text: str) -> list[str]:
    """'Sci-Fi, industrial,, sci-fi' -> ['sci-fi', 'industrial'] (lower case, each once)."""
    out: list[str] = []
    for tag in text.split(","):
        tag = " ".join(tag.strip().lower().split())
        if tag and tag not in out:
            out.append(tag)
    return out


class DetailsDialog(QDialog):
    def __init__(self, asset: lf.Asset, parent=None):
        super().__init__(parent)
        self.asset = asset
        self.setWindowTitle(f"{asset.name}: Details")
        self.resize(520, 420)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(asset.name)
        form.addRow("Name", self.name)
        self.description = QPlainTextEdit(asset.description)
        self.description.setFixedHeight(90)
        form.addRow("Description", self.description)
        self.tags = QLineEdit(", ".join(asset.tags))
        self.tags.setPlaceholderText("words to find it by, with commas between")
        form.addRow("Tags", self.tags)
        self.licence = QComboBox()
        for code in EDITABLE_LICENCES:
            self.licence.addItem(licence_label(code), code)
        if asset.licence == lf.PURCHASED:  # (kept as it is: its details come in step 5)
            self.licence.addItem(licence_label(lf.PURCHASED), lf.PURCHASED)
        self.licence.setCurrentIndex(max(0, self.licence.findData(asset.licence)))
        self.licence.currentIndexChanged.connect(lambda _i: self._credit_note())
        form.addRow("Licence", self.licence)
        self.author = QLineEdit(asset.author)
        form.addRow("Author", self.author)
        self.title = QLineEdit(asset.title)
        self.title.setPlaceholderText("the work's own title, for its credit")
        form.addRow("Title", self.title)
        self.source = QLineEdit(asset.source)
        self.source.setPlaceholderText("where it came from (a web address)")
        form.addRow("Source", self.source)
        layout.addLayout(form)
        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._credit_note()

    def _credit_note(self) -> None:
        code = self.licence.currentData()
        licence = lf.LICENCES.get(code)
        notes = []
        if licence and licence.credit:
            notes.append("This licence needs a credit: the author, and a title or source.")
        if licence and licence.share_alike:
            notes.append("Share-alike: a game that changes it must offer the changed asset "
                         "under the same licence.")
        self.note.setText(" ".join(notes))

    def save(self) -> bool:
        """The details written to the asset (asset.json and LICENSE.md). Nothing is saved, and
        the problem is shown, if a needed detail is missing."""
        trial = lf.Asset(**{**self.asset.__dict__})
        trial.name = self.name.text().strip() or self.asset.name
        trial.description = self.description.toPlainText().strip()
        trial.tags = parse_tags(self.tags.text())
        trial.licence = self.licence.currentData()
        trial.author = self.author.text().strip()
        trial.title = self.title.text().strip()
        trial.source = self.source.text().strip()
        said = [p for p in lf.problems(trial) if "credit" in p or "licence" in p]
        if said:
            QMessageBox.warning(self, "Details", "Not saved: " + "; ".join(said) + ".")
            return False
        for key in ("name", "description", "tags", "licence", "author", "title", "source"):
            setattr(self.asset, key, getattr(trial, key))
        lf.write(self.asset)
        self.accept()
        return True
