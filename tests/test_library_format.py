# SPDX-License-Identifier: Apache-2.0
"""Step 2: the library format (docs/library_format.md) as the code follows it."""
import json
from pathlib import Path

import pytest

from master_library import library_format as lf
from master_library.library_format import Asset, Library, LibraryError

DOC = Path(__file__).resolve().parent.parent / "docs" / "library_format.md"


def make_asset(root: Path, name="Rusty Plates", type_="textures", category="metal",
               files=None, **fields) -> Asset:
    folder = lf.free_folder(lf.type_folder(root, type_, category), name)
    folder.mkdir(parents=True)
    for rel, data in (files or {"rusty_basecolor.png": b"\x89PNG\r\n\x1a\nplates"}).items():
        (folder / rel).parent.mkdir(parents=True, exist_ok=True)
        (folder / rel).write_bytes(data)
    asset = Asset(folder=folder, root=root, name=name, type=type_, category=category,
                  imported="2026-11-03", **fields)
    lf.record_files(asset)
    lf.write(asset)
    return asset


# ---- a library -----------------------------------------------------------------------------
def test_a_library_is_made_once_and_opened_again(tmp_path):
    lib = Library.create(tmp_path / "Master")
    assert lf.is_library(tmp_path / "Master")
    again = Library.open(tmp_path / "Master")
    assert (again.id, again.created) == (lib.id, lib.created)
    doc = json.loads((tmp_path / "Master" / "library.json").read_text("utf-8"))
    assert doc["format"] == 2 and doc["kind"] == "master"
    with pytest.raises(LibraryError, match="already holds"):
        Library.create(tmp_path / "Master")
    assert Library.open_or_create(tmp_path / "Master").id == lib.id


def test_a_folder_that_isnt_a_library_is_refused(tmp_path):
    with pytest.raises(LibraryError, match="isn't a library"):
        Library.open(tmp_path)
    (tmp_path / "library.json").write_text('{"format": 9, "kind": "master", "id": "x"}')
    with pytest.raises(LibraryError, match="newer program"):
        Library.open(tmp_path)


def test_assets_go_by_type_kind_and_album(tmp_path):
    assert lf.type_folder(tmp_path, "textures", "metal") == tmp_path / "textures" / "metal"
    assert lf.type_folder(tmp_path, "music", "Dark Woods") == tmp_path / "music" / "dark_woods"
    assert lf.type_folder(tmp_path, "effects") == tmp_path / "effects" / "miscellaneous"
    assert lf.type_folder(tmp_path, "models") == tmp_path / "models"
    with pytest.raises(LibraryError):
        lf.type_folder(tmp_path, "textures", "cheese")
    with pytest.raises(LibraryError):
        lf.type_folder(tmp_path, "videos")


# ---- an asset ------------------------------------------------------------------------------
def test_an_asset_is_written_and_read_back_the_same(tmp_path):
    a = make_asset(tmp_path, tags=["sci-fi"], description="Riveted steel.")
    b = lf.read(a.folder, tmp_path)
    assert b.to_json() == a.to_json()
    assert b.path == "textures/metal/rusty_plates"
    assert b.version == 1 and len(b.id) == 36
    assert (a.folder / "LICENSE.md").read_text("utf-8").startswith("# Rusty Plates")
    assert [f["path"] for f in b.files] == ["rusty_basecolor.png"]  # (not its own two files)


def test_the_fingerprint_follows_the_files_only(tmp_path):
    a = make_asset(tmp_path)
    first = a.fingerprint
    assert first == lf.fingerprint(list(reversed(a.files)))  # (the order doesn't matter)
    a.description = "changed words only"
    lf.write(a)
    assert not lf.record_files(a) and a.fingerprint == first and a.version == 1
    (a.folder / "rusty_basecolor.png").write_bytes(b"\x89PNG\r\n\x1a\nrepainted")
    assert lf.record_files(a)
    assert a.fingerprint != first and a.version == 2


def test_the_fingerprint_is_as_the_document_says(tmp_path):
    import hashlib
    files = [{"path": "b.png", "sha256": "22"}, {"path": "a.png", "sha256": "11"}]
    assert lf.fingerprint(files) == hashlib.sha256(b"a.png\t11\nb.png\t22\n").hexdigest()


def test_midgards_version_1_assets_are_read(tmp_path):
    folder = tmp_path / "textures" / "wood" / "planks"
    folder.mkdir(parents=True)
    (folder / "planks.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    files = [{"path": "planks.png", "sha256": lf.sha256(folder / "planks.png"), "bytes": 8}]
    (folder / "asset.json").write_text(json.dumps({
        "format": 1, "name": "Planks", "type": "textures", "category": "wood",
        "description": "", "licence": "CC0-1.0", "author": "", "source": "", "title": "",
        "imported": "2026-10-30", "files": files}))
    a, b = lf.read(folder, tmp_path), lf.read(folder, tmp_path)
    assert a.read_format == 1 and a.version == 1 and a.tags == []
    assert a.id == b.id  # (the same each time it is read)
    assert a.fingerprint == lf.fingerprint(files)
    assert json.loads((folder / "asset.json").read_text())["format"] == 1  # (not rewritten)
    assert lf.problems(a) == []


def test_a_library_is_scanned_and_what_cant_be_read_is_reported(tmp_path):
    make_asset(tmp_path, "Zinc")
    make_asset(tmp_path, "Brass")
    make_asset(tmp_path, "Oak", category="wood")
    broken = tmp_path / "models" / "broken"
    broken.mkdir(parents=True)
    (broken / "asset.json").write_text("{not json")
    assets, problems = lf.scan(tmp_path)
    assert [a.name for a in assets] == ["Brass", "Zinc", "Oak"]
    assert len(problems) == 1 and "broken" in problems[0]


def test_names_that_are_taken_get_a_number(tmp_path):
    a = make_asset(tmp_path, "Rusty Plates")
    b = make_asset(tmp_path, "Rusty Plates")
    assert (a.folder.name, b.folder.name) == ("rusty_plates", "rusty_plates_2")


def test_removing_an_asset_tidies_its_empty_folders(tmp_path):
    a = make_asset(tmp_path)
    lf.remove(a)
    assert not (tmp_path / "textures").exists()


# ---- licences ------------------------------------------------------------------------------
def test_licences_that_need_credit_need_an_author_and_a_title_or_source(tmp_path):
    a = make_asset(tmp_path, licence="CC-BY-4.0")
    assert any("author" in p for p in lf.problems(a))
    assert any("title or source" in p for p in lf.problems(a))
    a.author, a.source = "Ana Ruiz", "https://example.org/rusty"
    assert lf.problems(a) == []
    assert lf.credit(a) == ('"Rusty Plates" by Ana Ruiz (https://example.org/rusty), CC BY 4.0 '
                            "(https://creativecommons.org/licenses/by/4.0/)")


def test_share_alike_is_marked(tmp_path):
    a = make_asset(tmp_path, licence="CC-BY-SA-4.0", author="Kim", title="Bricks")
    assert lf.share_alike(a) and lf.needs_credit(a) and lf.may_give_away(a)
    assert "Share-alike" in lf.licence_text(a)


def test_a_purchased_asset_keeps_its_seller_and_licence_and_isnt_given_away(tmp_path):
    a = make_asset(tmp_path, "Village", type_="models", category="",
                   files={"village.glb": b"glTF....", "LICENSE-purchase.txt": b"terms"},
                   licence="Purchased")
    assert any("who sold it" in p for p in lf.problems(a))
    assert any("licence is needed" in p for p in lf.problems(a))
    a.purchase = {"seller": "Example Asset Store", "product": "Fantasy Village Pack",
                  "order": "SS-1", "date": "2026-08-14", "licence_file": "LICENSE-purchase.txt",
                  "credit": False}
    assert lf.problems(a) == []
    assert not lf.may_give_away(a) and not lf.needs_credit(a)
    lf.write(a)
    text = lf.licence_text(a)
    assert "Seller: Example Asset Store" in text and "may not be given away" in text
    a.purchase["licence_file"] = "elsewhere.txt"
    assert any("isn't one of its files" in p for p in lf.problems(a))
    a.purchase.update(licence_file="LICENSE-purchase.txt", credit=True)
    a.author = "Studio Nine"
    assert lf.needs_credit(a)
    assert lf.credit(a) == '"Village" by Studio Nine, from Example Asset Store'


def test_an_unknown_licence_is_a_problem(tmp_path):
    a = make_asset(tmp_path, licence="All rights reserved")
    assert any("isn't one the library takes" in p for p in lf.problems(a))


def test_credits_are_listed_once_each(tmp_path):
    a = make_asset(tmp_path, "One", licence="CC-BY-4.0", author="A", title="One")
    b = make_asset(tmp_path, "Two", licence="CC0-1.0")
    assert lf.credits([a, a, b]) == [lf.credit(a)]


def test_changed_or_missing_files_are_problems(tmp_path):
    a = make_asset(tmp_path)
    (a.folder / "rusty_basecolor.png").write_bytes(b"other")
    assert any("has changed" in p for p in lf.problems(a))
    (a.folder / "rusty_basecolor.png").unlink()
    assert any("is missing" in p for p in lf.problems(a))


# ---- copying -------------------------------------------------------------------------------
def test_a_copy_into_a_project_remembers_where_it_came_from(tmp_path):
    master = Library.create(tmp_path / "Master")
    original = make_asset(master.root, tags=["metal"])
    project = tmp_path / "Project" / "library"
    copy = lf.copy_asset(original, project, from_library=master.id)
    assert copy.path == original.path
    assert (copy.id, copy.version, copy.fingerprint) == \
        (original.id, original.version, original.fingerprint)
    assert copy.origin["library"] == master.id and copy.origin["version"] == 1
    assert lf.read(copy.folder, project).origin == copy.origin
    assert not lf.changed_here(copy)
    # The Master's is changed: the project's copy is behind it.
    (original.folder / "rusty_basecolor.png").write_bytes(b"\x89PNG\r\n\x1a\nnew")
    lf.record_files(original)
    lf.write(original)
    masters, _ = master.scan()
    assert lf.newer_in(masters, copy).version == 2
    # The project's copy is changed by itself.
    (copy.folder / "rusty_basecolor.png").write_bytes(b"\x89PNG\r\n\x1a\nmine")
    lf.record_files(copy)
    assert lf.changed_here(copy)


def test_a_copy_beside_one_already_there_is_numbered(tmp_path):
    original = make_asset(tmp_path / "Master")
    first = lf.copy_asset(original, tmp_path / "P")
    second = lf.copy_asset(original, tmp_path / "P")
    assert first.folder.name == "rusty_plates" and second.folder.name == "rusty_plates_2"
    assert first.origin is None  # (not from a Master)


# ---- the document and the code agree -------------------------------------------------------
def test_the_document_lists_every_type_and_licence():
    text = DOC.read_text("utf-8")
    for type_ in lf.TYPES:
        assert f"| `{type_}` |" in text
    for key in lf.LICENCES:
        assert f"| `{key}` |" in text
    assert "Version 2" in text and '"format": 2' in text
