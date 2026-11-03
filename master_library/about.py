# SPDX-License-Identifier: Apache-2.0
"""Help ▸ About Master Asset Library, following the About Scheme (as in Midgard)."""
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget

from . import APP_NAME, DESCRIPTION, ICON_PATH, version
from .library_format import FORMAT_VERSION


def build_date_text(iso: str | None) -> str | None:
    if not iso:
        return None
    d = date.fromisoformat(iso)
    return f"{d:%B} {d.day}, {d.year}"


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(32, 24, 32, 16)

        name = QLabel(APP_NAME)
        font = name.font()
        font.setPointSizeF(font.pointSizeF() * 1.8)
        font.setBold(True)
        name.setFont(font)
        icon = QLabel()
        icon.setPixmap(QPixmap(str(ICON_PATH)).scaled(
            128, 128, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))
        self.version_label = QLabel(f"v{version.VERSION} (build {version.BUILD})")
        self.format_label = QLabel(f"Library format {FORMAT_VERSION}")
        lines = [name, QLabel(DESCRIPTION), icon, self.version_label, self.format_label]
        if built := build_date_text(version.BUILD_DATE):
            lines.append(QLabel(built))
        for w in lines:
            w.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(w)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.setCenterButtons(True)
        buttons.accepted.connect(self.accept)
        layout.addSpacing(6)
        layout.addWidget(buttons)
        # Widen to the golden ratio (1.6:1) so the title bar has room for its title.
        hint = self.sizeHint()
        self.setFixedSize(max(hint.width(), round(hint.height() * 1.6)), hint.height())
