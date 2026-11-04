# SPDX-License-Identifier: Apache-2.0
"""An asset's details, edited: its name, description, tags, licence and credit, and where a
purchased one was bought."""
import shutil

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
from .purchase import LICENCE_FILES, PurchaseForm

LICENCE_CHOICES = list(lf.LICENCES)


def licence_label(code: str) -> str:
    licence = lf.LICENCES.get(code)
    return licence.name if licence else (code or "none")


def licence_note(code: str) -> str:
    """What a licence asks, in a sentence or two."""
    licence = lf.LICENCES.get(code)
    if licence is None:
        return ""
    if code == lf.PURCHASED:
        return ("Bought: who sold it, and their licence (kept with it), are needed. Its "
                "original files are never given away: games use it, sharing a project warns.")
    notes = ["Its author, and its title or source, are needed for its credit."
             if licence.credit else "No credit is needed (naming the author is kind all the "
             "same)."]
    if licence.share_alike:
        notes.append("Share-alike: a game that changes it (recolours it, cuts it up) must offer "
                     "the changed asset under the same licence.")
    return " ".join(notes)


def parse_tags(text: str) -> list[str]:
    """'Sci-Fi, industrial,, sci-fi' -> ['sci-fi', 'industrial'] (lower case, each once)."""
    out: list[str] = []
    for tag in text.split(","):
        tag = " ".join(tag.strip().lower().split())
        if tag and tag not in out:
            out.append(tag)
    return out


def text_files(asset: lf.Asset) -> list[str]:
    """The asset's files a seller's licence could be."""
    return [f["path"] for f in asset.files if f["path"].lower().endswith(LICENCE_FILES)]


class DetailsDialog(QDialog):
    def __init__(self, asset: lf.Asset, parent=None):
        super().__init__(parent)
        self.asset = asset
        self.setWindowTitle(f"{asset.name}: Details")
        self.resize(560, 520)
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
        for code in LICENCE_CHOICES:
            self.licence.addItem(licence_label(code), code)
        if asset.licence not in lf.LICENCES:  # (kept as it is, until one is chosen)
            self.licence.addItem(licence_label(asset.licence), asset.licence)
        self.licence.setCurrentIndex(max(0, self.licence.findData(asset.licence)))
        self.licence.currentIndexChanged.connect(lambda _i: self._licence_changed())
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
        self.purchase = PurchaseForm(asset.purchase, text_files(asset))
        layout.addWidget(self.purchase)
        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._licence_changed()

    def _licence_changed(self) -> None:
        code = self.licence.currentData()
        self.purchase.setVisible(code == lf.PURCHASED)
        self.note.setText(licence_note(code))

    def save(self) -> bool:
        """The details written to the asset (asset.json and LICENSE.md; a licence file added
        from elsewhere is copied in). Nothing is saved, and the problem is shown, if a needed
        detail is missing."""
        trial = lf.Asset(**{**self.asset.__dict__})
        trial.name = self.name.text().strip() or self.asset.name
        trial.description = self.description.toPlainText().strip()
        trial.tags = parse_tags(self.tags.text())
        trial.licence = self.licence.currentData()
        trial.author = self.author.text().strip()
        trial.title = self.title.text().strip()
        trial.source = self.source.text().strip()
        extra = self.purchase.extra_file if trial.licence == lf.PURCHASED else None
        if trial.licence == lf.PURCHASED:
            trial.purchase = self.purchase.values()
            if extra is not None:  # (as it will be once copied in)
                trial.files = [*trial.files, {"path": extra.name, "sha256": "", "bytes": 0}]
        else:
            trial.purchase = None
        said = [p for p in lf.problems(trial)
                if any(w in p for w in ("credit", "licence", "bought", "sold"))]
        if extra is not None:
            said = [p for p in said if extra.name not in p]
        if said:
            QMessageBox.warning(self, "Details", "Not saved: " + "; ".join(said) + ".")
            return False
        if extra is not None:
            shutil.copy2(extra, self.asset.folder / extra.name)
            lf.record_files(self.asset)  # (its files changed: a new version)
        for key in ("name", "description", "tags", "licence", "author", "title", "source",
                    "purchase"):
            setattr(self.asset, key, getattr(trial, key))
        lf.write(self.asset)
        self.accept()
        return True
