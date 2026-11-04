# SPDX-License-Identifier: Apache-2.0
"""Step 1: the program starts, with its menus, themes, About box and settings."""
import datetime
import json

from master_library import APP_NAME, ICON_PATH, THEMES_DIR, version
from master_library.__main__ import main
from master_library.about import AboutDialog, build_date_text
from master_library.main_window import MainWindow
from master_library.settings import Settings, default_library_dir


def test_the_icon_and_themes_are_where_the_program_looks():
    assert ICON_PATH.is_file()
    assert sorted(THEMES_DIR.glob("*.qss"))


def test_version_prints(capsys):
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.startswith(f"Master Asset Library {version.VERSION}")


def test_the_window_has_its_menus(qtbot, settings):
    window = MainWindow(settings)
    qtbot.addWidget(window)
    assert window.windowTitle() == APP_NAME
    menus = [a.text() for a in window.menuBar().actions()]
    assert menus == ["&File", "&View", "&Help"]
    assert str(settings.library_dir()) in window.title.text()
    assert window.library is not None  # (made there, on first opening)
    assert settings.library_dir() != default_library_dir()  # (tests never touch Documents)


def test_a_theme_is_kept_for_next_time(qtbot, settings):
    window = MainWindow(settings)
    qtbot.addWidget(window)
    qss = next(k for k in window.theme_actions if k.startswith("qss:"))
    window.theme_actions[qss].trigger()
    assert window.theme_actions[qss].isChecked()
    assert Settings(settings.dir).get("theme") == qss
    again = MainWindow(Settings(settings.dir))
    qtbot.addWidget(again)
    assert again.theme_actions[qss].isChecked()
    again.theme_actions["light"].trigger()  # (back to the desktop's look for other tests)


def test_a_missing_theme_falls_back_to_the_desktop(qtbot, settings):
    settings.set("theme", "qss:gone-away")
    window = MainWindow(settings)
    qtbot.addWidget(window)
    assert settings.get("theme") is None


def test_the_library_folder_is_kept(qtbot, settings, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    chosen = tmp_path / "My Library"
    chosen.mkdir()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(chosen))
    window = MainWindow(settings)
    qtbot.addWidget(window)
    window.choose_library_dir()
    assert Settings(settings.dir).library_dir() == chosen
    assert str(chosen) in window.title.text()
    assert (chosen / "library.json").is_file()


def test_the_about_box_follows_the_about_scheme(qtbot):
    box = AboutDialog()
    qtbot.addWidget(box)
    assert box.version_label.text() == f"v{version.VERSION} (build {version.BUILD})"
    assert box.format_label.text().startswith("Library format ")
    assert box.width() >= round(box.height() * 1.6) - 1  # the golden ratio


def test_build_dates_read_naturally():
    assert build_date_text("2026-11-03") == "November 3, 2026"
    assert build_date_text(None) is None


def test_bump_build_counts_up_and_resets_on_a_new_minor(tmp_path):
    import bump_build

    version_file, out = tmp_path / "VERSION", tmp_path / "version.py"
    version_file.write_text("0.1.0\n")
    day = datetime.date(2026, 11, 3)
    assert bump_build.bump(version_file, out, day) == ("0.1.0", 1, "2026-11-03")
    assert bump_build.bump(version_file, out, day)[1] == 2
    version_file.write_text("0.2.0\n")
    assert bump_build.bump(version_file, out, day)[1] == 1


def test_the_smoke_test_reports_a_working_window(tmp_path, qapp):
    from master_library.app import run

    assert run(smoke_test=tmp_path) == 0
    result = json.loads((tmp_path / "smoke_test.json").read_text(encoding="utf-8"))
    assert result["ok"] and result["icon"] and result["title"] == APP_NAME
