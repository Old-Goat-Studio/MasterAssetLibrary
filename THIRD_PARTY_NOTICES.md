# Third-party components

The packaged Master Asset Library includes:

| Component | Licence | Notes |
|---|---|---|
| Python 3.12 | PSF License 2.0 | https://www.python.org/ |
| Qt 6 and Qt for Python (PySide6, Shiboken6) | LGPL-3.0 | https://www.qt.io/ — kept as separate library files in the program's `_internal` folder, which you may replace with your own builds. Source: https://code.qt.io/ |
| PyInstaller bootloader | GPL-2.0 with the PyInstaller bootloader exception | https://pyinstaller.org/ — the exception allows its use in programs under any licence. |

Building it also uses Pillow (MIT-CMU, to make the icon) and Inno Setup (Inno Setup licence,
for the installer); neither is part of the installed program.
