# SPDX-License-Identifier: Apache-2.0
"""A purchased asset's details: who sold it, what and when, the order, and the seller's licence
(a file kept with the asset), and whether the licence asks for a credit."""
from pathlib import Path

from PySide6.QtCore import QDate, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QWidget,
)

LICENCE_FILES = (".txt", ".md", ".pdf", ".html", ".htm", ".rtf")


class PurchaseForm(QGroupBox):
    """Where a purchased asset came from. The seller's licence is either one of the asset's own
    files (choose it) or a file from elsewhere (it is copied in with the asset)."""
    changed = Signal()

    def __init__(self, purchase: dict | None = None, files: list[str] | None = None,
                 parent: QWidget | None = None):
        super().__init__("Bought", parent)
        p = purchase or {}
        form = QFormLayout(self)
        self.seller = QLineEdit(p.get("seller", ""))
        self.seller.setPlaceholderText("the shop or person it was bought from")
        form.addRow("Seller", self.seller)
        self.product = QLineEdit(p.get("product", ""))
        self.product.setPlaceholderText("what was bought (the pack's name)")
        form.addRow("Product", self.product)
        self.order = QLineEdit(p.get("order", ""))
        self.order.setPlaceholderText("the order or receipt number")
        form.addRow("Order", self.order)
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("yyyy-MM-dd")
        given = QDate.fromString(p.get("date", ""), "yyyy-MM-dd")
        self.date.setDate(given if given.isValid() else QDate.currentDate())
        form.addRow("Date", self.date)
        row = QHBoxLayout()
        self.licence_file = QComboBox()
        self.licence_file.setEditable(False)
        self.licence_file.setToolTip("The seller's licence, kept with the asset")
        for name in files or []:
            self.licence_file.addItem(name, name)
        self.licence_file.setCurrentIndex(max(0, self.licence_file.findData(
            p.get("licence_file", ""))) if self.licence_file.count() else -1)
        row.addWidget(self.licence_file, 1)
        self.add_file = QPushButton("Add…")
        self.add_file.setToolTip("A licence file from elsewhere (copied in with the asset)")
        self.add_file.clicked.connect(self._choose_file)
        row.addWidget(self.add_file)
        form.addRow("Seller's licence", row)
        self.credit = QCheckBox("Its licence asks for a credit (in a game's credits)")
        self.credit.setChecked(bool(p.get("credit")))
        form.addRow("", self.credit)
        self.extra_file: Path | None = None  # a licence file from elsewhere, to copy in
        for w in (self.seller, self.product, self.order):
            w.textChanged.connect(self.changed)

    def set_files(self, files: list[str]) -> None:
        """The asset's own text files, any of which may be the seller's licence."""
        current = self.licence_file.currentData()
        self.licence_file.clear()
        for name in files:
            self.licence_file.addItem(name, name)
        if self.extra_file is not None:
            self.licence_file.addItem(f"{self.extra_file.name} (added)", self.extra_file.name)
        index = self.licence_file.findData(current)
        if index < 0:  # (a file whose name says licence, to begin with)
            index = next((i for i in range(self.licence_file.count())
                          if "licen" in self.licence_file.itemData(i).lower()), 0)
        self.licence_file.setCurrentIndex(index if self.licence_file.count() else -1)

    def add_licence_file(self, path: Path) -> None:
        self.extra_file = Path(path)
        name = self.extra_file.name
        index = self.licence_file.findData(name)
        if index < 0:
            self.licence_file.addItem(f"{name} (added)", name)
            index = self.licence_file.count() - 1
        self.licence_file.setCurrentIndex(index)

    def _choose_file(self) -> None:
        file, _ = QFileDialog.getOpenFileName(
            self, "The seller's licence", "",
            "Licences (" + " ".join(f"*{e}" for e in LICENCE_FILES) + ");;All files (*)")
        if file:
            self.add_licence_file(Path(file))

    def values(self) -> dict:
        return {"seller": self.seller.text().strip(), "product": self.product.text().strip(),
                "order": self.order.text().strip(),
                "date": self.date.date().toString("yyyy-MM-dd"),
                "licence_file": self.licence_file.currentData() or "",
                "credit": self.credit.isChecked()}
