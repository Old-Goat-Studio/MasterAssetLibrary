# SPDX-License-Identifier: Apache-2.0
"""Split Pack…: a model asset holding many objects made into one asset per chosen object, each
with the pack's licence, credit, tags and licence files."""
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from . import importing
from . import library_format as lf
from .importing import remove_if_empty
from .split import Pack, PackObject, SplitError, split_to

TEXTURE_LIMITS = (("As they are", None), ("At most 2048 pixels", 2048),
                  ("At most 1024 pixels", 1024), ("At most 512 pixels", 512))
ROLE = Qt.ItemDataRole.UserRole


def pack_file(asset: lf.Asset) -> Path | None:
    """The asset's model file, if it has exactly one."""
    models = [asset.folder / f["path"] for f in asset.files
              if f["path"].lower().endswith((".glb", ".gltf"))]
    return models[0] if len(models) == 1 else None


def can_split(asset: lf.Asset) -> bool:
    return asset.type in ("models", "objects") and pack_file(asset) is not None


def split_asset(library_root: Path, asset: lf.Asset, objects: list[PackObject], *,
                best_only: bool = True, largest_texture: int | None = None,
                names: dict[int, str] | None = None) -> importing.ImportResult:
    """The chosen objects made assets of their own, beside the pack (which stays)."""
    file = pack_file(asset)
    if file is None:
        raise SplitError(f"'{asset.name}' doesn't hold exactly one model file")
    texts = [asset.folder / f["path"] for f in asset.files
             if f["path"].lower().endswith(importing.TEXT)]
    result = importing.ImportResult()
    work = Path(library_root) / importing.WORK
    work.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(dir=work, prefix="split_") as scratch:
            made = split_to(file, Path(scratch), objects, best_only, largest_texture)
            for obj, glb in made:
                name = f"{asset.name}: {(names or {}).get(obj.node, obj.name)}"
                details = importing.Details(
                    category=asset.category, description=asset.description,
                    tags=list(asset.tags), licence=asset.licence, author=asset.author,
                    source=asset.source, title=asset.title,
                    purchase=dict(asset.purchase) if asset.purchase else None)
                one = importing.import_assets(library_root, [glb, *texts], asset.type, name,
                                              details)
                result.assets += one.assets
                result.refused += one.refused
                result.warnings += one.warnings
    finally:
        remove_if_empty(work)  # (its own scratch is gone: others' may not be)
    return result


class SplitDialog(QDialog):
    def __init__(self, library: lf.Library, asset: lf.Asset, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Split '{asset.name}'")
        self.resize(720, 620)
        self.library = library
        self.asset = asset
        self.result: importing.ImportResult | None = None
        self.removed = False
        self.quiet = False  # (tests: questions and reports aren't shown)
        self.last_report = ""
        self.pack = Pack.read(pack_file(asset))
        layout = QVBoxLayout(self)
        intro = QLabel(f"'{asset.name}' holds these objects. Each one ticked becomes an asset of "
                       "its own (standing at the middle of its base, its size and way up kept), "
                       "with the pack's licence, credit and tags.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Object (its name can be changed)", "Triangles",
                                   "Size (m)"])
        self.tree.setRootIsDecorated(False)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.itemChanged.connect(lambda *_: self._summary())
        layout.addWidget(self.tree, 1)
        row = QHBoxLayout()
        for label, on in (("Tick All", True), ("Tick None", False)):
            button = QPushButton(label)
            button.clicked.connect(lambda _c=False, v=on: self.tick_all(v))
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        form = QFormLayout()
        self.best_only = QCheckBox("Only each object's most detailed version (its LOD0)")
        self.best_only.setChecked(True)
        self.best_only.toggled.connect(lambda _on: self.fill())
        form.addRow("Detail levels", self.best_only)
        self.textures = QComboBox()
        for label, limit in TEXTURE_LIMITS:
            self.textures.addItem(label, limit)
        self.textures.setToolTip("Each object carries the textures it uses: big shared ones "
                                 "are copied into every object, so smaller ones save room")
        form.addRow("Largest texture", self.textures)
        self.remove_pack = QCheckBox("Remove the pack from the library afterwards")
        form.addRow("", self.remove_pack)
        layout.addLayout(form)
        self.summary = QLabel()
        layout.addWidget(self.summary)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.split_button = buttons.addButton("Split", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.accepted.connect(lambda: self.do_split())
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.fill()

    def fill(self) -> None:
        self.objects = self.pack.objects(self.best_only.isChecked())
        self.best_only.setVisible(any(o.levels > 1 for o in self.objects))
        self.tree.blockSignals(True)
        self.tree.clear()
        for o in self.objects:
            size = " × ".join(f"{s:.2f}" for s in o.size)
            item = QTreeWidgetItem([o.name, f"{o.triangles:,}", size])
            item.setData(0, ROLE, o.node)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable |
                          Qt.ItemFlag.ItemIsEditable)
            item.setCheckState(0, Qt.CheckState.Checked if len(self.objects) <= 200
                               else Qt.CheckState.Unchecked)
            item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tree.addTopLevelItem(item)
        self.tree.blockSignals(False)
        self._summary()

    def tick_all(self, on: bool) -> None:
        self.tree.blockSignals(True)
        for i in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(i).setCheckState(
                0, Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
        self.tree.blockSignals(False)
        self._summary()

    def tick(self, *names: str) -> None:
        """Only these objects ticked (by name)."""
        self.tree.blockSignals(True)
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            item.setCheckState(0, Qt.CheckState.Checked if item.text(0) in names
                               else Qt.CheckState.Unchecked)
        self.tree.blockSignals(False)
        self._summary()

    def chosen(self) -> tuple[list[PackObject], dict[int, str]]:
        """The ticked objects, and the names given them."""
        by_node = {o.node: o for o in self.objects}
        chosen, names = [], {}
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.checkState(0) == Qt.CheckState.Checked:
                node = item.data(0, ROLE)
                chosen.append(by_node[node])
                names[node] = item.text(0).strip() or by_node[node].name
        return chosen, names

    def _summary(self) -> None:
        chosen, _names = self.chosen()
        tris = sum(o.triangles for o in chosen)
        self.summary.setText(f"{len(chosen)} of {len(self.objects)} objects ticked "
                             f"({tris:,} triangles).")
        self.split_button.setEnabled(bool(chosen))

    def do_split(self) -> bool:
        chosen, names = self.chosen()
        if not chosen:
            return False
        try:
            result = split_asset(self.library.root, self.asset, chosen,
                                 best_only=self.best_only.isChecked(),
                                 largest_texture=self.textures.currentData(), names=names)
        except (SplitError, lf.LibraryError, OSError, ValueError, KeyError) as e:
            self._say(f"Not split: {e}", warning=True)
            return False
        self.result = result
        n = len(result.assets)
        lines = [f"Made {n} asset{'' if n == 1 else 's'} from '{self.asset.name}'."]
        lines += [f"  {name}: {why}" for name, why in result.refused]
        if n and self.remove_pack.isChecked():
            lf.remove(self.asset)
            self.removed = True
            lines.append(f"'{self.asset.name}' itself was removed from the library.")
        self._say("\n".join(lines), warning=not n)
        if n:
            self.accept()
        return bool(n)

    def _say(self, text: str, warning: bool = False) -> None:
        self.last_report = text
        if not self.quiet:
            (QMessageBox.warning if warning else QMessageBox.information)(
                self, "Split Pack", text)
