# SPDX-License-Identifier: Apache-2.0
"""Step 4: bringing assets in (files, folders, zips; downloads as untrusted) and collecting
from Midgard projects."""
import json
import wave
import zipfile
from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QImage
from test_window import tiny_glb

from master_library import importing
from master_library import library_format as lf
from master_library.importing import Details


def png(path: Path, colour: str = "#a05030", size: int = 8) -> Path:
    image = QImage(size, size, QImage.Format.Format_RGB32)
    image.fill(QColor(colour))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(path))
    return path


def wav(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\1\0" * 800)
    return path


@pytest.fixture
def master(tmp_path):
    return lf.Library.create(tmp_path / "Master")


# ---- files, folders and zips ---------------------------------------------------------------
def test_loose_files_become_one_asset_with_its_details(master, tmp_path):
    sound = wav(tmp_path / "dl" / "door_creak.wav")
    (tmp_path / "dl" / "readme.txt").write_text("thanks")
    result = importing.import_assets(
        master.root, [sound, tmp_path / "dl" / "readme.txt"], "effects", "Door Creak",
        Details(category="Doors", tags=["door", "wood"], licence="CC-BY-4.0", author="Kim",
                source="https://example.org/creak"))
    assert len(result.assets) == 1 and not result.skipped
    a = result.assets[0]
    assert a.path == "effects/doors/door_creak"
    assert [f["path"] for f in a.files] == ["door_creak.wav", "readme.txt"]
    again = lf.read(a.folder, master.root)
    assert again.tags == ["door", "wood"] and again.author == "Kim" and again.version == 1
    assert sound.is_file()  # (the original stays where it was)
    assert not (master.root / importing.WORK).exists()  # (its scratch folder is gone)


def test_files_an_asset_cant_use_or_that_lie_are_left_out(master, tmp_path):
    good = png(tmp_path / "dl" / "logo.png")
    (tmp_path / "dl" / "fake.png").write_bytes(b"MZ this is a program")
    (tmp_path / "dl" / "setup.exe").write_bytes(b"MZ")
    result = importing.import_assets(master.root, [tmp_path / "dl"], "images", "Logo")
    assert [f["path"] for f in result.assets[0].files] == ["logo.png"]
    assert dict(result.skipped) == {"fake.png": "isn't a .png file inside",
                                    "setup.exe": "images can't use .exe"}
    assert "skipped 2 files: 1 .exe, 1 .png" in result.summary()
    assert good.is_file()


def test_a_zip_is_opened_without_its_top_folder(master, tmp_path):
    z = tmp_path / "pack.zip"
    with zipfile.ZipFile(z, "w") as out:
        out.write(png(tmp_path / "a.png"), "Pack/icons/a.png")
        out.write(png(tmp_path / "b.png", "#00ff00"), "Pack/icons/b.png")
        out.writestr("__MACOSX/._a.png", "junk")
    a = importing.import_assets(master.root, [z], "icons", "Pack").assets[0]
    assert sorted(f["path"] for f in a.files) == ["icons/a.png", "icons/b.png"]


@pytest.mark.parametrize("name", ["../escape.png", "/abs.png", "C:/win.png", "a/../../x.png"])
def test_a_zip_that_would_write_outside_the_library_is_refused(master, tmp_path, name):
    z = tmp_path / "evil.zip"
    with zipfile.ZipFile(z, "w") as out:
        out.writestr(name, "x")
    with pytest.raises(lf.LibraryError, match="outside the library"):
        importing.import_assets(master.root, [z], "images", "Evil")
    assert not (tmp_path / "escape.png").exists()
    assert lf.scan(master.root)[0] == []


def test_a_damaged_zip_says_so(master, tmp_path):
    (tmp_path / "broken.zip").write_bytes(b"PK not really")
    with pytest.raises(lf.LibraryError, match="can't be opened as a zip"):
        importing.import_assets(master.root, [tmp_path / "broken.zip"], "images", "Broken")


def test_the_same_files_twice_are_refused(master, tmp_path):
    pic = png(tmp_path / "logo.png")
    importing.import_assets(master.root, [pic], "images", "Logo")
    again = importing.import_assets(master.root, [pic], "images", "Logo again")
    assert not again.assets
    assert "in the library already, as 'Logo'" in again.refused[0][1]


def test_a_licence_needing_credit_without_an_author_leaves_nothing_behind(master, tmp_path):
    result = importing.import_assets(master.root, [png(tmp_path / "x.png")], "images", "X",
                                     Details(licence="CC-BY-4.0"))
    assert not result.assets and "author" in result.refused[0][1]
    assert not (master.root / "images").exists()


def test_nothing_usable_is_refused(master, tmp_path):
    (tmp_path / "only.txt").write_text("words")
    result = importing.import_assets(master.root, [tmp_path / "only.txt"], "images", "Words")
    assert "nothing usable" in result.refused[0][1]
    with pytest.raises(lf.LibraryError, match="needs a name"):
        importing.import_assets(master.root, [tmp_path / "only.txt"], "images", "  ")


# ---- texture sets --------------------------------------------------------------------------
def test_a_texture_sets_pictures_are_named_by_their_roles(master, tmp_path):
    src = tmp_path / "Rock_Wall_001"
    for name, colour in (("Rock_Wall_001_Color.png", "#806040"),
                         ("Rock_Wall_001_Normal.png", "#8080ff"),
                         ("Rock_Wall_001_Roughness.png", "#c0c0c0"),
                         ("Rock_Wall_001_Height.png", "#808080")):
        png(src / name, colour)
    pictures = importing.images_in([src])
    from master_library.roles import guess_role
    roles = {rel: guess_role(rel) for rel in pictures}
    assert roles["Rock_Wall_001_Height.png"] == ""  # (not used: left out)
    result = importing.import_assets(master.root, [src], "textures", "Rock Wall",
                                     Details(category="stone"), roles=roles)
    names = sorted(f["path"] for f in result.assets[0].files)
    assert names == ["rock_wall_color.png", "rock_wall_metallic_roughness.png",
                     "rock_wall_normal.png", "rock_wall_roughness.png"]
    assert ("Rock_Wall_001_Height.png", "not used") in result.skipped
    combined = QImage(str(result.assets[0].folder / "rock_wall_metallic_roughness.png"))
    pixel = combined.pixelColor(0, 0)
    assert pixel.green() == 0xC0 and pixel.blue() == 0  # (roughness green, no metal)


def test_two_pictures_with_one_role_are_refused(master, tmp_path):
    a, b = png(tmp_path / "a_color.png"), png(tmp_path / "b_color.png", "#000000")
    with pytest.raises(lf.LibraryError, match="both colour"):
        importing.import_assets(master.root, [a, b], "textures", "Twice",
                                Details(category="metal"),
                                roles={"a_color.png": "color", "b_color.png": "color"})


# ---- packs of models -----------------------------------------------------------------------
def test_a_pack_of_models_is_split_one_asset_each(master, tmp_path):
    pack = tmp_path / "Village"
    pack.mkdir()
    (pack / "house.glb").write_bytes(tiny_glb())
    (pack / "well.glb").write_bytes(tiny_glb() + b"  ")  # (different files)
    png(pack / "house_wood.png")
    (pack / "LICENSE.txt").write_text("CC0")
    assert importing.model_count([pack]) == 2
    result = importing.import_assets(master.root, [pack], "models", "Village", split=True)
    names = sorted(a.name for a in result.assets)
    assert names == ["Village: House", "Village: Well"]
    house = next(a for a in result.assets if a.name == "Village: House")
    assert sorted(f["path"] for f in house.files) == ["LICENSE.txt", "house.glb",
                                                       "house_wood.png"]


def test_a_gltf_naming_missing_files_is_warned_about(master, tmp_path):
    gltf = tmp_path / "tree.gltf"
    gltf.write_text(json.dumps({"asset": {"version": "2.0"},
                                "buffers": [{"uri": "tree.bin", "byteLength": 4}]}))
    result = importing.import_assets(master.root, [gltf], "models", "Tree")
    assert result.assets and "names tree.bin, which isn't with it" in result.warnings[0]


# ---- collecting from Midgard projects ------------------------------------------------------
def midgard_project(folder: Path) -> Path:
    """A Midgard project as 5.13a writes it: version 1 assets in its library folder."""
    (folder / "Demo.config").parent.mkdir(parents=True, exist_ok=True)
    (folder / "Demo.config").write_text("{}")
    for path, name, colour, licence in (("textures/wood/planks", "Planks", "#806040", "CC0-1.0"),
                                        ("images/logo", "Logo", "#204080", "CC-BY-4.0")):
        asset = folder / "library" / path
        pic = png(asset / f"{Path(path).name}.png", colour)
        files = [{"path": pic.name, "sha256": lf.sha256(pic), "bytes": pic.stat().st_size}]
        (asset / "asset.json").write_text(json.dumps({
            "format": 1, "name": name, "type": path.split("/")[0],
            "category": path.split("/")[1] if path.count("/") == 2 else "",
            "description": "", "licence": licence, "author": "Ana", "source": "",
            "title": name, "imported": "2026-10-30", "files": files}))
    return folder


def test_a_midgard_projects_assets_are_collected_once(master, tmp_path):
    project = midgard_project(tmp_path / "Midgard Projects" / "Demo")
    result = importing.collect(master, project / "Demo.config")
    assert sorted(a.name for a in result.collected) == ["Logo", "Planks"]
    planks = next(a for a in result.collected if a.name == "Planks")
    assert planks.path == "textures/wood/planks"
    assert planks.origin is None and planks.licence == "CC0-1.0"
    doc = json.loads((planks.folder / "asset.json").read_text())
    assert doc["format"] == 2  # (written as the Master's)
    again = importing.collect(master, project)
    assert not again.collected and sorted(again.already) == ["Logo", "Planks"]
    assert "2 already in the Master" in again.summary()
    # (the project's own files are untouched)
    assert json.loads((project / "library/images/logo/asset.json").read_text())["format"] == 1


def test_two_projects_with_different_assets_at_one_path_are_both_kept(master, tmp_path):
    one = midgard_project(tmp_path / "One")
    two = midgard_project(tmp_path / "Two")
    png(two / "library/textures/wood/planks/planks.png", "#000000")  # (other planks)
    doc = json.loads((two / "library/textures/wood/planks/asset.json").read_text())
    pic = two / "library/textures/wood/planks/planks.png"
    doc["files"] = [{"path": "planks.png", "sha256": lf.sha256(pic), "bytes": 1}]
    (two / "library/textures/wood/planks/asset.json").write_text(json.dumps(doc))
    importing.collect(master, one)
    result = importing.collect(master, two)
    assert [a.name for a in result.collected] == ["Planks"]
    assets, _ = master.scan()
    planks = [a for a in assets if a.name == "Planks"]
    assert sorted(a.folder.name for a in planks) == ["planks", "planks_2"]
    assert planks[0].id != planks[1].id


def test_a_projects_changed_copy_of_a_master_asset_is_left_there(master, tmp_path):
    original = importing.import_assets(master.root, [png(tmp_path / "rust.png")], "images",
                                       "Rust").assets[0]
    project = tmp_path / "P"
    copy = lf.copy_asset(original, project / "library", from_library=master.id)
    png(copy.folder / "rust.png", "#ffffff")  # (repainted in the project)
    lf.record_files(copy)
    lf.write(copy)
    result = importing.collect(master, project)
    assert result.changed == ["Rust"] and not result.collected


def test_a_folder_without_a_library_isnt_a_project(master, tmp_path):
    with pytest.raises(lf.LibraryError, match="isn't a Midgard project"):
        importing.collect(master, tmp_path)


# ---- in the window -------------------------------------------------------------------------
def test_the_window_imports_and_shows_the_new_asset(qtbot, settings, tmp_path):
    from master_library.main_window import MainWindow
    window = MainWindow(settings)
    qtbot.addWidget(window)
    dialog = window.import_dialog([png(tmp_path / "dl" / "splash_screen.png")], run=False)
    dialog.quiet = True
    assert dialog.form.name.text() == "Splash screen"
    dialog.form.type.setCurrentIndex(dialog.form.type.findData("images"))
    dialog.form.tags.setText("Title, logo")
    assert dialog.do_import()
    window.refresh()
    assert [a.name for a in window.assets] == ["Splash screen"]
    assert window.assets[0].tags == ["title", "logo"]


def test_the_import_dialog_gives_texture_pictures_their_roles(qtbot, master, tmp_path):
    from master_library.import_dialog import ImportDialog
    src = tmp_path / "Bricks"
    png(src / "bricks_basecolor.png")
    png(src / "bricks_nrm.png", "#8080ff")
    dialog = ImportDialog(master, "textures")
    qtbot.addWidget(dialog)
    dialog.quiet = True
    dialog.add_sources([src])
    assert dialog.roles() == {"bricks_basecolor.png": "color", "bricks_nrm.png": "normal"}
    dialog.form.category.setCurrentIndex(dialog.form.category.findData("brick"))
    assert dialog.do_import()
    assert sorted(f["path"] for f in dialog.result.assets[0].files) == \
        ["bricks_color.png", "bricks_normal.png"]


def test_the_window_collects_from_a_project(qtbot, settings, tmp_path):
    from master_library.main_window import MainWindow
    window = MainWindow(settings)
    qtbot.addWidget(window)
    window.quiet = True
    result = window.collect_dialog(midgard_project(tmp_path / "Demo"))
    assert len(result.collected) == 2
    assert window.last_collect_report.startswith("Collected 2 assets")
    assert window.types.item(0).text() == "Everything  (2)"
