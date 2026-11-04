# SPDX-License-Identifier: Apache-2.0
"""Step 5: purchased and share-alike assets, imported and edited, and found by their licence."""
from pathlib import Path

import pytest
from test_importing import png
from test_window import tiny_glb

from master_library import importing
from master_library import library_format as lf
from master_library.details import DetailsDialog, licence_note
from master_library.import_dialog import ImportDialog
from master_library.main_window import MainWindow


@pytest.fixture
def master(tmp_path):
    return lf.Library.create(tmp_path / "Master")


def village_pack(folder: Path) -> Path:
    folder.mkdir(parents=True)
    (folder / "village.glb").write_bytes(tiny_glb())
    (folder / "Licence Agreement.txt").write_text("Use in your games; don't resell the files.")
    return folder


def test_a_purchased_pack_is_imported_with_where_it_was_bought(qtbot, master, tmp_path):
    dialog = ImportDialog(master, "models")
    qtbot.addWidget(dialog)
    dialog.quiet = True
    dialog.add_sources([village_pack(tmp_path / "Village")])
    form = dialog.form
    form.licence.setCurrentIndex(form.licence.findData(lf.PURCHASED))
    assert not form.purchase.isHidden()
    # The pack's own licence file is offered (one that says licence, to begin with).
    assert form.purchase.licence_file.currentData() == "Licence Agreement.txt"
    assert not dialog.do_import()  # (who sold it is needed)
    assert "who sold it" in dialog.last_report
    form.purchase.seller.setText("Example Asset Store")
    form.purchase.product.setText("Fantasy Village Pack")
    form.purchase.order.setText("EX-104455")
    assert dialog.do_import()
    asset = lf.read(dialog.result.assets[0].folder, master.root)
    assert asset.licence == lf.PURCHASED
    assert asset.purchase["seller"] == "Example Asset Store"
    assert asset.purchase["licence_file"] == "Licence Agreement.txt"
    assert not lf.may_give_away(asset) and lf.problems(asset) == []
    text = (asset.folder / "LICENSE.md").read_text("utf-8")
    assert "Seller: Example Asset Store" in text and "may not be given away" in text


def test_a_sellers_licence_from_elsewhere_is_copied_in(qtbot, master, tmp_path):
    receipt = tmp_path / "Downloads" / "EULA.pdf"
    receipt.parent.mkdir()
    receipt.write_bytes(b"%PDF-1.4 the terms")
    model = tmp_path / "barrel.glb"
    model.write_bytes(tiny_glb())
    dialog = ImportDialog(master, "models")
    qtbot.addWidget(dialog)
    dialog.quiet = True
    dialog.add_sources([model])
    form = dialog.form
    form.licence.setCurrentIndex(form.licence.findData(lf.PURCHASED))
    form.purchase.seller.setText("Shop")
    form.purchase.add_licence_file(receipt)
    assert dialog.do_import()
    asset = dialog.result.assets[0]
    assert sorted(f["path"] for f in asset.files) == ["EULA.pdf", "barrel.glb"]
    assert asset.purchase["licence_file"] == "EULA.pdf"
    assert receipt.is_file()  # (the original stays)


def test_share_alike_is_imported_only_when_meant(qtbot, master, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    answers = [QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes]
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: asked.append(a[2]) or answers.pop(0))
    dialog = ImportDialog(master, "images")
    qtbot.addWidget(dialog)
    dialog.add_sources([png(tmp_path / "mural.png")])
    dialog.quiet = False
    monkeypatch.setattr(dialog, "_say", lambda *a, **k: None)
    form = dialog.form
    form.licence.setCurrentIndex(form.licence.findData("CC-BY-SA-4.0"))
    form.author.setText("Kim")
    form.title.setText("Mural")
    assert "Share-alike" in form.note.text()
    assert not dialog.do_import()  # (No: not imported)
    assert "share-alike" in asked[0] and lf.scan(master.root)[0] == []
    assert dialog.do_import()  # (Yes)
    assert lf.share_alike(dialog.result.assets[0])


def test_details_turn_an_asset_into_a_purchased_one(qtbot, master, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    said = []
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, text: said.append(text))
    asset = importing.import_assets(master.root, [png(tmp_path / "logo.png")], "images",
                                    "Logo").assets[0]
    dialog = DetailsDialog(asset)
    qtbot.addWidget(dialog)
    assert dialog.purchase.isHidden()
    dialog.licence.setCurrentIndex(dialog.licence.findData(lf.PURCHASED))
    assert not dialog.purchase.isHidden()
    dialog.purchase.seller.setText("Logo Shop")
    assert not dialog.save()  # (no licence file yet)
    assert "licence is needed" in said[0]
    terms = tmp_path / "terms.txt"
    terms.write_text("terms")
    dialog.purchase.add_licence_file(terms)
    assert dialog.save()
    again = lf.read(asset.folder, master.root)
    assert again.licence == lf.PURCHASED and again.purchase["licence_file"] == "terms.txt"
    assert again.version == 2  # (a file was added: a new version)
    assert lf.problems(again) == []
    # And back to CC0: the purchase details go.
    dialog = DetailsDialog(again)
    qtbot.addWidget(dialog)
    dialog.licence.setCurrentIndex(dialog.licence.findData("CC0-1.0"))
    assert dialog.save()
    assert lf.read(asset.folder, master.root).purchase is None


def test_licence_notes_say_what_each_asks():
    assert "never given away" in licence_note(lf.PURCHASED)
    assert "Share-alike" in licence_note("CC-BY-SA-3.0")
    assert "No credit" in licence_note("CC0-1.0")


def test_the_licence_filter_finds_purchased_and_share_alike_assets(qtbot, settings, tmp_path):
    root = settings.library_dir()
    lf.Library.create(root)
    imp = importing.import_assets
    imp(root, [png(tmp_path / "a.png", "#100000")], "images", "Free")
    imp(root, [png(tmp_path / "b.png", "#200000")], "images", "Mural",
        importing.Details(licence="CC-BY-SA-4.0", author="Kim", title="Mural"))
    pack = village_pack(tmp_path / "V")
    imp(root, [pack], "models", "Village", importing.Details(
        licence=lf.PURCHASED, purchase={"seller": "Example Asset Store",
                                        "licence_file": "Licence Agreement.txt"}))
    window = MainWindow(settings)
    qtbot.addWidget(window)

    def shown(label):
        window.licence_filter.setCurrentIndex(window.licence_filter.findText(label))
        return sorted(a.name for a in window.shown_assets())

    assert shown("Any licence") == ["Free", "Mural", "Village"]
    assert shown("Purchased") == ["Village"]
    assert shown("Share-alike (CC BY-SA)") == ["Mural"]
    assert shown("Free to share (CC0, CC BY)") == ["Free"]
    assert shown("Needs a credit") == ["Mural"]
    window.licence_filter.setCurrentIndex(0)
    window.search.setText("example asset store")  # (found by its seller)
    assert [a.name for a in window.shown_assets()] == ["Village"]
    window.select(window.shown_assets()[0].id)
    assert "Bought: from Example Asset Store" in window.info.text()
    assert "may not be given away" in window.info.text()


def test_own_work_needs_its_artist_and_isnt_given_away(tmp_path):
    root = tmp_path / "M"
    lf.Library.create(root)
    result = importing.import_assets(root, [png(tmp_path / "tile.png")], "textures", "Tile",
                                     importing.Details(category="floor", licence=lf.OWN_WORK))
    assert "its artist (author) is needed" in result.refused[0][1]
    result = importing.import_assets(root, [png(tmp_path / "tile.png")], "textures", "Tile",
                                     importing.Details(category="floor", licence=lf.OWN_WORK,
                                                       author="Richard E Rogers"))
    a = result.assets[0]
    assert lf.problems(a) == [] and not lf.may_give_away(a) and not lf.needs_credit(a)
    assert "Own work" in licence_note(lf.OWN_WORK) or "own work" in licence_note(lf.OWN_WORK)


def test_a_combined_map_is_the_metallic_and_roughness():
    from master_library.roles import guess_role
    assert guess_role("Rock_Wall_001_Combined.png") == "metallic_roughness"
    assert guess_role("Rock_Wall_001_Emissive.png") == "emissive"
    assert guess_role("Rock_Wall_001_Ambient occlusion.png") == "occlusion"
    # (the role is the last word: a "Metal Floor" set's maps aren't all metallic)
    roles = [guess_role(f"Metal_Floor_001_{k}.png") for k in
             ("Color", "Normal", "Ambient occlusion", "Emissive", "Metallic", "Combined")]
    assert roles == ["color", "normal", "occlusion", "emissive", "metallic",
                     "metallic_roughness"]
