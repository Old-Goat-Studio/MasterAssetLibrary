# SPDX-License-Identifier: Apache-2.0
"""Master Asset Library entry point.

    master-library                    open the library
    master-library --version          print the version
    master-library --smoke-test DIR   start, write DIR/smoke_test.json, quit (packaging checks)
"""
import argparse
import sys
from pathlib import Path

from .version import BUILD, VERSION


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="master-library", description="Master Asset Library")
    parser.add_argument("--version", action="store_true", help="print the version and exit")
    parser.add_argument("--smoke-test", type=Path, metavar="DIR",
                        help="start, write smoke_test.json in DIR, quit")
    args = parser.parse_args(argv)
    if args.version:
        print(f"Master Asset Library {VERSION} (build {BUILD})")
        return 0
    from .app import run  # the GUI; only imported when needed

    return run(smoke_test=args.smoke_test)


if __name__ == "__main__":
    sys.exit(main())
