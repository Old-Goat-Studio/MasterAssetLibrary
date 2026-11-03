# SPDX-License-Identifier: Apache-2.0
"""PyInstaller's entry script for the packaged program."""
import sys

from master_library.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
