# SPDX-License-Identifier: Apache-2.0
"""Settings in master_library.json: %APPDATA%\\Master Asset Library on Windows,
~/.local/share/Master Asset Library on Linux (QStandardPaths.AppDataLocation with the application
name and no organisation)."""
import copy
import json
import os
from pathlib import Path
from typing import Any

from PySide6.QtCore import QStandardPaths

DEFAULTS: dict[str, Any] = {
    "theme": None,         # "light", "dark" or "qss:<name>"; None = desktop colours
    "library_dir": "",     # where the library is ("": Documents/Master Asset Library)
    "geometry": None,      # the window's last size and place (base64)
}


def default_dir() -> Path:
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))


def default_library_dir() -> Path:
    documents = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
    return Path(documents or Path.home()) / "Master Asset Library"


def projects_dir() -> Path:
    """Where Midgard makes projects, to begin looking for one (Documents/Midgard Projects)."""
    documents = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
    return Path(documents or Path.home()) / "Midgard Projects"


class Settings:
    """Settings, written atomically so a crash never leaves half a file."""

    def __init__(self, directory: Path | None = None):
        self.dir = directory or default_dir()
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "master_library.json"
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            self._data = loaded if isinstance(loaded, dict) else {}
        except (OSError, ValueError):
            self._data = {}

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._data:
            return self._data[key]
        if default is not None:
            return default
        return copy.deepcopy(DEFAULTS.get(key))  # never hand out the shared default objects

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def library_dir(self) -> Path:
        """Where the library is (File ▸ Library Folder…)."""
        chosen = self.get("library_dir")
        return Path(chosen) if chosen else default_library_dir()
