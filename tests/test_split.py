# SPDX-License-Identifier: Apache-2.0
"""Split a pack: a model file of many objects made into one model (and asset) per object."""
import json
import struct
from pathlib import Path

import pytest
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QColor, QImage

from master_library import importing
from master_library import library_format as lf
from master_library.gltf_bounds import gltf_document, model_bounds
from master_library.split import Pack, SplitError, clean_names, split_to

BOX = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 1)  # a triangle 1 x 1 x 1


def png_bytes(colour: str, size: int = 64) -> bytes:
    image = QImage(size, size, QImage.Format.Format_RGB32)
    image.fill(QColor(colour))
    out = QByteArray()
    buf = QBuffer(out)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, "PNG")
    return bytes(out)


def make_pack(path: Path, *, skinned: bool = False, required: list[str] | None = None) -> Path:
    """A pack as Sketchfab exports one: wrappers (one scaling by 2), then two objects: "rock_lr"
    (one mesh, its own texture) and "tree_lr" (two detail levels, LOD0 and LOD1, each a mesh with
    the tree's texture), 5 m apart."""
    blob = bytearray(BOX)
    images = []
    for colour in ("#808080", "#20a020"):
        data = png_bytes(colour)
        images.append({"bufferView": len(images) + 1, "mimeType": "image/png"})
        blob += data + b"\0" * (-len(data) % 4)
    offsets, at = [], len(BOX)
    for i in range(2):
        size = len(png_bytes(("#808080", "#20a020")[i]))
        offsets.append((at, size))
        at += size + (-size % 4)
    doc = {
        "asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
        "nodes": [
            {"name": "Sketchfab_model", "children": [1], "scale": [2, 2, 2]},
            {"name": "abc.fbx", "children": [2]},
            {"name": "RootNode", "children": [3, 4]},
            {"name": "rock_lr", "translation": [0, 0, 0], "children": [5]},
            {"name": "tree_lr", "translation": [5, 0, 0], "children": [6, 7]},
            {"name": "rock_lr_mesh_0", "mesh": 0},
            {"name": "tree_LOD0", "mesh": 1},
            {"name": "tree_LOD1", "mesh": 2, "translation": [0, 0, -10]},
        ],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "material": m}]}
                   for m in (0, 1, 1)],
        "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}},
                      {"pbrMetallicRoughness": {"baseColorTexture": {"index": 1}}}],
        "textures": [{"source": 0, "sampler": 0}, {"source": 1, "sampler": 0}],
        "samplers": [{}],
        "images": images,
        "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3",
                       "min": [0, 0, 0], "max": [1, 1, 1]}],
        "bufferViews": [{"buffer": 0, "byteLength": len(BOX)}] +
                       [{"buffer": 0, "byteOffset": o, "byteLength": n} for o, n in offsets],
        "buffers": [{"byteLength": len(blob)}],
    }
    if skinned:
        doc["nodes"][5]["skin"] = 0
        doc["skins"] = [{"joints": [5]}]
    if required:
        doc["extensionsRequired"] = doc["extensionsUsed"] = required
    text = json.dumps(doc).encode()
    text += b" " * (-len(text) % 4)
    body = struct.pack("<II", len(text), 0x4E4F534A) + text + \
        struct.pack("<II", len(blob), 0x004E4942) + bytes(blob)
    path.write_bytes(struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body)
    return path


def test_a_packs_objects_are_found_below_its_wrappers(tmp_path):
    pack = Pack.read(make_pack(tmp_path / "pack.glb"))
    objects = pack.objects()
    assert [o.name for o in objects] == ["Rock", "Tree"]  # ("_lr", the same in both, gone)
    rock, tree = objects
    assert rock.size == [2.0, 2.0, 2.0]  # (the wrapper's scale of 2 kept)
    assert tree.levels == 2 and tree.triangles == 1  # (its LOD0 only)
    assert pack.objects(best_only=False)[1].triangles == 2


def test_each_object_is_written_with_only_its_own_things_standing_at_the_origin(tmp_path):
    made = split_to(make_pack(tmp_path / "pack.glb"), tmp_path / "out")
    assert [p.name for _o, p in made] == ["rock.glb", "tree.glb"]
    for _obj, path in made:
        lo, hi = model_bounds(path)
        assert lo == pytest.approx([-1, 0, -1]) and hi == pytest.approx([1, 2, 1])
        doc = gltf_document(path)
        assert len(doc["meshes"]) == 1 and len(doc["images"]) == 1
    tree = gltf_document(made[1][1])
    assert [n.get("name") for n in tree["nodes"]][-1] == "tree_LOD0"  # (no LOD1)
    assert made[1][1].stat().st_size < (tmp_path / "pack.glb").stat().st_size


def test_every_detail_level_can_be_kept(tmp_path):
    pack = make_pack(tmp_path / "pack.glb")
    made = split_to(pack, tmp_path / "out", best_only=False)
    tree = gltf_document(made[1][1])
    assert len(tree["meshes"]) == 2


def test_textures_can_be_made_smaller(tmp_path):
    pack = make_pack(tmp_path / "pack.glb")
    _obj, path = split_to(pack, tmp_path / "out", largest_texture=16)[0]
    doc = gltf_document(path)
    data = path.read_bytes()
    json_len = struct.unpack_from("<I", data, 12)[0]
    binary = data[20 + json_len + 8:]
    view = doc["bufferViews"][doc["images"][0]["bufferView"]]
    image = QImage.fromData(binary[view["byteOffset"]:view["byteOffset"] + view["byteLength"]])
    assert (image.width(), image.height()) == (16, 16)


def test_characters_and_compressed_packs_are_refused(tmp_path):
    with pytest.raises(SplitError, match="skinned"):
        split_to(make_pack(tmp_path / "skin.glb", skinned=True), tmp_path / "out")
    with pytest.raises(SplitError, match="compressed"):
        Pack.read(make_pack(tmp_path / "draco.glb", required=["KHR_draco_mesh_compression"]))


def test_names_are_made_readable():
    assert clean_names(["rock46_lr", "rock44_lr"]) == ["Rock46", "Rock44"]
    assert clean_names(["Large tree_1", "Large tree_2"]) == ["Large tree 1", "Large tree 2"]
    assert clean_names(["a.fbx", "a.fbx"]) == ["A", "A 2"]


def test_the_window_splits_a_pack_into_assets_that_keep_its_licence(qtbot, settings, tmp_path):
    from master_library.main_window import MainWindow
    root = settings.library_dir()
    lf.Library.create(root)
    licence = tmp_path / "license.txt"
    licence.write_text("CC-BY-4.0 by DJ")
    imported = importing.import_assets(
        root, [make_pack(tmp_path / "pack.glb"), licence], "models", "Nature Pack",
        importing.Details(licence="CC-BY-4.0", author="DJ", title="Nature Pack",
                          source="https://example.org/pack", tags=["nature"]))
    window = MainWindow(settings)
    qtbot.addWidget(window)
    window.select(imported.assets[0].id)
    assert window.split_button.isEnabled()
    dialog = window.split_selected(run=False)
    dialog.quiet = True
    assert dialog.tree.topLevelItemCount() == 2
    dialog.tree.topLevelItem(0).setText(0, "Grey Rock")
    dialog.tick("Grey Rock")
    assert dialog.summary.text().startswith("1 of 2 objects ticked")
    dialog.remove_pack.setChecked(True)
    assert dialog.do_split()
    window.refresh()
    names = sorted(a.name for a in window.assets)
    assert names == ["Nature Pack: Grey Rock"]  # (the pack removed, as asked)
    rock = window.assets[0]
    assert rock.licence == "CC-BY-4.0" and rock.author == "DJ" and rock.tags == ["nature"]
    assert sorted(f["path"] for f in rock.files) == ["license.txt", "rock.glb"]
    assert lf.problems(rock) == []


def test_every_object_of_a_pack_is_split_out(settings, tmp_path):
    from master_library.split_dialog import split_asset
    root = settings.library_dir()
    lf.Library.create(root)
    pack = importing.import_assets(root, [make_pack(tmp_path / "pack.glb")], "models",
                                   "Pack").assets[0]
    objects = Pack.read(pack.folder / "pack.glb").objects()
    result = split_asset(root, pack, objects)
    assert sorted(a.name for a in result.assets) == ["Pack: Rock", "Pack: Tree"]
    assert not (root / importing.WORK).exists()  # (its scratch folder tidied away)


def test_only_a_single_model_file_can_be_split(settings, tmp_path):
    from master_library.split_dialog import can_split
    root = settings.library_dir()
    lf.Library.create(root)
    pic = tmp_path / "p.png"
    pic.write_bytes(png_bytes("#ffffff"))
    image = importing.import_assets(root, [pic], "images", "Picture").assets[0]
    assert not can_split(image)


def test_importing_a_pack_file_can_make_one_asset_per_object(qtbot, settings, tmp_path):
    from master_library.import_dialog import ImportDialog
    root = settings.library_dir()
    library = lf.Library.create(root)
    pack = make_pack(tmp_path / "rocks.glb")
    licence = tmp_path / "license.txt"
    licence.write_text("CC0")
    assert importing.objects_in([pack, licence]) == 2
    dialog = ImportDialog(library, "models")
    qtbot.addWidget(dialog)
    dialog.quiet = True
    dialog.split_answer = True
    dialog.add_sources([pack, licence])
    assert dialog.do_import()
    names = sorted(a.name for a in dialog.result.assets)
    assert names == ["Rocks: Rock", "Rocks: Tree"]
    assert all(sorted(f["path"] for f in a.files)[0] == "license.txt"
               for a in dialog.result.assets)
    # Answered "one asset": the pack as it is.
    other = tmp_path / "other"
    other.mkdir()
    again = make_pack(other / "again.glb")
    again.write_bytes(again.read_bytes() + b"  ")  # (not the same files)
    whole = importing.import_assets(root, [again], "models", "Whole")
    assert [a.name for a in whole.assets] == ["Whole"]
