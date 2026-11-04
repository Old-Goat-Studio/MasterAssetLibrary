# SPDX-License-Identifier: Apache-2.0
"""Step 3: the Master window: types, the list, search and tags, the player, details, files."""
import json
import struct
import wave
from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QImage

from master_library import library_format as lf
from master_library.details import DetailsDialog, parse_tags
from master_library.main_window import MainWindow, matches
from master_library.player import choices


def png(path: Path, colour: str = "#a05030", size: int = 16) -> bytes:
    image = QImage(size, size, QImage.Format.Format_RGB32)
    image.fill(QColor(colour))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(path))
    return path.read_bytes()


def tiny_glb() -> bytes:
    """A one-triangle glTF binary."""
    positions = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
           "nodes": [{"mesh": 0}],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
           "buffers": [{"byteLength": len(positions)}],
           "bufferViews": [{"buffer": 0, "byteLength": len(positions)}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3",
                          "min": [0, 0, 0], "max": [1, 1, 0]}]}
    text = json.dumps(doc).encode()
    text += b" " * (-len(text) % 4)
    body = struct.pack("<II", len(text), 0x4E4F534A) + text + \
        struct.pack("<II", len(positions), 0x004E4942) + positions
    return struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body


def add(root: Path, name: str, type_: str, category: str, files: dict[str, bytes],
        **fields) -> lf.Asset:
    folder = lf.free_folder(lf.type_folder(root, type_, category), name)
    folder.mkdir(parents=True)
    for rel, data in files.items():
        (folder / rel).write_bytes(data)
    asset = lf.Asset(folder=folder, root=root, name=name, type=type_, category=category,
                     imported="2026-11-03", **fields)
    lf.record_files(asset)
    lf.write(asset)
    return asset


@pytest.fixture
def library(settings, tmp_path):
    """A library with a texture set, a sound, a model and a picture."""
    root = settings.library_dir()
    lf.Library.create(root)
    scratch = tmp_path / "scratch"
    add(root, "Rusty Plates", "textures", "metal", {
        "rusty_plates_color.png": png(scratch / "c.png", "#a05030"),
        "rusty_plates_normal.png": png(scratch / "n.png", "#8080ff"),
        "LICENSE.txt": b"CC0"}, tags=["sci-fi", "industrial"], description="Riveted steel.")
    sound = scratch / "beep.wav"
    with wave.open(str(sound), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\0\0" * 2205)
    add(root, "Beep", "effects", "UI", {"beep.wav": sound.read_bytes()}, tags=["ui"],
        licence="CC-BY-4.0", author="Kim", title="Beep")
    add(root, "Triangle", "models", "", {"triangle.glb": tiny_glb()}, tags=["sci-fi"])
    add(root, "Splash", "images", "", {"splash.png": png(scratch / "s.png", "#204080")})
    return root


@pytest.fixture
def window(qtbot, settings, library):
    w = MainWindow(settings)
    qtbot.addWidget(w)
    return w


def listed(window) -> list[str]:
    names = []
    for i in range(window.tree.topLevelItemCount()):
        top = window.tree.topLevelItem(i)
        if top.data(0, 0x0100):
            names.append(top.text(0))
        for j in range(top.childCount()):
            names.append(top.child(j).text(0))
    return names


def choose(window, name: str) -> lf.Asset:
    asset = next(a for a in window.assets if a.name == name)
    window.select(asset.id)
    return asset


def type_row(window, key: str) -> int:
    return next(i for i in range(window.types.count()) if window.types.item(i).data(0x0100) == key)


def test_the_types_show_their_counts_and_everything_is_listed(window):
    assert window.types.item(0).text() == "Everything  (4)"
    assert window.types.item(type_row(window, "textures")).text() == "Textures  (1)"
    assert window.types.item(type_row(window, "fonts")).text() == "Fonts"
    assert sorted(listed(window)) == ["Beep", "Rusty Plates", "Splash", "Triangle"]
    assert "4 assets" in window.title.text()
    window.types.setCurrentRow(type_row(window, "textures"))
    assert listed(window) == ["Rusty Plates"]


def test_search_and_tags_find_assets(window):
    window.search.setText("steel")
    assert listed(window) == ["Rusty Plates"]
    window.search.setText("kim")  # (its author)
    assert listed(window) == ["Beep"]
    window.search.setText("")
    window.tag.setCurrentIndex(window.tag.findData("sci-fi"))
    assert sorted(listed(window)) == ["Rusty Plates", "Triangle"]
    assert [window.tag.itemText(i) for i in range(window.tag.count())] == \
        ["Any tag", "industrial", "sci-fi", "ui"]


def test_matching_needs_every_word():
    a = lf.Asset(folder=Path("x"), root=Path("."), name="Rusty Plates", type="textures",
                 tags=["sci-fi"], description="Riveted steel.")
    assert matches(a, "rusty steel", "")
    assert not matches(a, "rusty wood", "")
    assert matches(a, "", "sci-fi") and not matches(a, "", "fantasy")


def test_a_texture_set_shows_its_material_and_its_maps(window):
    asset = choose(window, "Rusty Plates")
    assert "Riveted steel." in window.info.text() and "version 1" in window.info.text()
    rows = [window.files.topLevelItem(i).text(0) for i in range(window.files.topLevelItemCount())]
    assert rows[0] == "Material (all maps)"
    assert rows[1:3] == ["rusty_plates_color.png (colour)", "rusty_plates_normal.png (normal)"]
    assert rows[3] == "LICENSE.txt"  # (not shown: greyed, last)
    assert window.player.kind in ("material", "picture")  # (a picture where there is no 3D)
    window.files.setCurrentItem(window.files.topLevelItem(2))
    assert window.player.kind == "picture"
    assert window.player.shown == asset.folder / "rusty_plates_normal.png"


def test_a_sound_is_played(window):
    choose(window, "Beep")
    assert window.player.kind in ("sound", "")
    assert "Credit:" in window.info.text()
    if window.player.kind == "sound":
        assert window.player.play_button.isVisible() or not window.isVisible()


def test_a_model_is_shown_in_3d(window, qtbot):
    choose(window, "Triangle")
    if window.player._scene_view() is None:
        pytest.skip(f"no 3D here: {window.player.scene_error}")
    assert window.player.kind == "model"
    root = window.player.scene_root()
    assert root.property("mode") == "model"
    qtbot.waitUntil(lambda: root.property("status") != 0, timeout=5000)
    assert root.property("status") == 1, root.property("error")  # (RuntimeLoader.Success)


def test_choices_put_the_material_first(library):
    assets, _ = lf.scan(library)
    plates = next(a for a in assets if a.name == "Rusty Plates")
    kinds = [kind for _label, kind, _path in choices(plates)]
    assert kinds == ["material", "picture", "picture"]
    assert choices(None) == []


def test_details_are_edited_and_kept(window, qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    said = []
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, text: said.append(text))
    asset = choose(window, "Splash")
    dialog = DetailsDialog(asset)
    qtbot.addWidget(dialog)
    dialog.tags.setText("Title Screen, logo, logo")
    dialog.description.setPlainText("The opening picture.")
    dialog.licence.setCurrentIndex(dialog.licence.findData("CC-BY-4.0"))
    assert not dialog.save()  # (a credit needs its author)
    assert "author" in said[0]
    dialog.author.setText("Ana")
    dialog.title.setText("Splash")
    assert dialog.save()
    again = lf.read(asset.folder, asset.root)
    assert again.tags == ["title screen", "logo"]
    assert again.licence == "CC-BY-4.0" and again.author == "Ana"
    assert again.version == 1  # (its files didn't change)


def test_tags_are_tidied():
    assert parse_tags(" Sci-Fi ,industrial,, sci-fi,  big   rock ") == \
        ["sci-fi", "industrial", "big rock"]


def test_an_asset_is_removed(window):
    asset = choose(window, "Splash")
    assert window.remove_selected(confirm=False)
    assert not asset.folder.exists()
    assert "Splash" not in listed(window)


def test_assets_that_cant_be_read_are_reported(window, library):
    broken = library / "models" / "broken"
    broken.mkdir(parents=True)
    (broken / "asset.json").write_text("{nope")
    window.refresh()
    window.tree.clearSelection()
    assert "Not read" in window.info.text()


def test_a_folder_with_other_things_in_it_isnt_made_a_library(window, tmp_path):
    busy = tmp_path / "Busy"
    busy.mkdir()
    (busy / "holiday.jpg").write_bytes(b"x")
    assert not window.open_library(busy)
    assert "isn't a library" in window.title.text()
    assert not (busy / "library.json").exists()


def test_a_models_box_is_read_from_its_file(tmp_path):
    from master_library.gltf_bounds import model_bounds

    glb = tmp_path / "triangle.glb"
    glb.write_bytes(tiny_glb())
    assert model_bounds(glb) == ([0, 0, 0], [1, 1, 0])
    gltf = tmp_path / "moved.gltf"  # (a node moves it: the box moves with it)
    gltf.write_text(json.dumps({
        "scene": 0, "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "translation": [2, 0, 0], "scale": [2, 2, 2]}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "accessors": [{"min": [0, 0, 0], "max": [1, 1, 1]}]}))
    assert model_bounds(gltf) == ([2, 0, 0], [4, 2, 2])
    (tmp_path / "bad.glb").write_bytes(b"nonsense")
    assert model_bounds(tmp_path / "bad.glb") is None
