# SPDX-License-Identifier: Apache-2.0
"""Package the Master Asset Library (a one-folder PyInstaller build) following the About Scheme.

    python tools/package.py                 bump the build number and build the program
    python tools/package.py --no-bump       keep the current build number (CI)
    python tools/package.py --installer     also make a Windows installer (Inno Setup 6)

The result is build/dist/MasterAssetLibrary/; --installer adds
build/installer/MasterAssetLibrary-Setup-<version>.<build>.exe from master_library.iss. The build
number is bumped first; if anything fails, the previous master_library/version.py is put back, so
a failed build never uses up a number. One-folder mode keeps the Qt libraries as separate files,
as the LGPL requires.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_PY = ROOT / "master_library" / "version.py"
DIST = ROOT / "build" / "dist"
NAME = "MasterAssetLibrary"
APP = DIST / NAME
EXE = ".exe" if os.name == "nt" else ""
ICON_PNG = ROOT / "MasterAssetLibrary512.png"
ICO = ROOT / "build" / "MasterAssetLibrary.ico"
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def run(*cmd: str | Path) -> None:
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], cwd=ROOT, check=True)


def make_icon() -> Path:
    """The program's icon, made from the full-size picture so the small sizes stay sharp."""
    from PIL import Image

    ICO.parent.mkdir(parents=True, exist_ok=True)
    Image.open(ROOT / "MasterAssetLibrary.png").convert("RGBA").save(ICO, sizes=ICO_SIZES)
    return ICO


def build_program() -> None:
    icon = make_icon() if os.name == "nt" else ICON_PNG
    with tempfile.TemporaryDirectory() as tmp:
        # Record this project so the packaged program uses its live Themes folder.
        source_info = Path(tmp) / "source_dir.txt"
        source_info.write_text(str(ROOT), encoding="utf-8")

        def data(src: Path, dest: str) -> list[str]:
            return ["--add-data", f"{src}{os.pathsep}{dest}"]

        run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
            "--onedir", "--name", NAME, "--icon", icon,
            "--distpath", DIST, "--workpath", ROOT / "build" / "pyinstaller",
            "--specpath", ROOT / "build" / "pyinstaller",
            "--paths", ROOT,
            *data(ROOT / "Themes", "Themes"),
            *data(ICON_PNG, "."),
            *data(source_info, "."),
            ROOT / "tools" / "launcher.py")
    # Qt's glTF loader for the player's models: PyInstaller can't see it is needed (the player's
    # 3D view is QML, loaded from a string).
    import PySide6

    importers = Path(PySide6.__file__).parent / "plugins" / "assetimporters"
    if importers.is_dir():
        shutil.copytree(importers, APP / "_internal" / "PySide6" / "plugins" / "assetimporters",
                        dirs_exist_ok=True)
    for name in ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / name, APP / name)


def find_iscc() -> Path:
    found = shutil.which("ISCC")
    if found:
        return Path(found)
    for base in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("PROGRAMFILES(X86)", ""),
                 os.environ.get("PROGRAMFILES", "")):
        for sub in ("Programs/Inno Setup 6", "Inno Setup 6"):
            candidate = Path(base) / sub / "ISCC.exe"
            if base and candidate.is_file():
                return candidate
    sys.exit("The installer needs Inno Setup 6 (ISCC.exe): https://jrsoftware.org/isinfo.php")


def build_installer() -> Path:
    """build/installer/MasterAssetLibrary-Setup-<version>.<build>.exe from master_library.iss."""
    if os.name != "nt":
        sys.exit("--installer makes a Windows installer: run it on Windows.")
    iscc = find_iscc()
    version: dict = {}
    exec(VERSION_PY.read_text(encoding="utf-8"), version)
    run(iscc, f"/DAppVersion={version['VERSION']}", f"/DAppBuild={version['BUILD']}",
        ROOT / "master_library.iss")
    name = f"{NAME}-Setup-{version['VERSION']}.{version['BUILD']}.exe"
    return ROOT / "build" / "installer" / name


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-bump", action="store_true")
    parser.add_argument("--installer", action="store_true")
    args = parser.parse_args()

    backup = VERSION_PY.with_name("version.py.bak")
    if not args.no_bump:
        shutil.copy2(VERSION_PY, backup)
    try:
        if not args.no_bump:
            run(sys.executable, ROOT / "bump_build.py")
        build_program()
        if args.installer:
            installer = build_installer()
    except BaseException:
        if backup.exists():
            shutil.move(backup, VERSION_PY)  # a failed build never uses up a build number
        raise
    backup.unlink(missing_ok=True)
    print(f"Packaged: {APP / (NAME + EXE)}")
    if args.installer:
        print(f"Installer: {installer}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
