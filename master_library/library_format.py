# SPDX-License-Identifier: Apache-2.0
"""The library format both this program and Midgard follow (docs/library_format.md, written in
step 2). Step 1 only needs its version and where a library lives."""
from pathlib import Path

FORMAT_VERSION = "1.0"


def is_library(folder: Path) -> bool:
    """Whether a folder holds a Master Asset Library (its library.json)."""
    return (folder / "library.json").is_file()
