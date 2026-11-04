# SPDX-License-Identifier: Apache-2.0
"""The library format (docs/library_format.md), version 2: libraries, assets, their licences,
fingerprints and credits, and copying assets between libraries. Midgard follows the same format
for a project's Asset Library; version 1 (Midgard 5.13a's) is read too."""
import datetime
import hashlib
import json
import re
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path

FORMAT = 2
FORMAT_VERSION = f"{FORMAT}"
LIBRARY_FILE = "library.json"
METADATA = "asset.json"
LICENCE_FILE = "LICENSE.md"
OWN_FILES = (METADATA, LICENCE_FILE)  # never part of an asset's files or fingerprint

TEXTURE_KINDS = ("metal", "wood", "stone", "concrete", "bark", "brick", "fabric", "floor",
                 "ground", "leather", "road", "roof", "wall", "miscellaneous")
# The asset types (folders), their names, and the kinds a type is sorted into.
TYPES: dict[str, tuple[str, tuple[str, ...]]] = {
    "gui": ("GUI", ()),
    "fonts": ("Fonts", ()),
    "textures": ("Textures", TEXTURE_KINDS),
    "images": ("Images", ()),
    "icons": ("Icons", ()),
    "music": ("Music", ()),
    "ambiance": ("Ambiance", ()),
    "effects": ("FX", ()),
    "models": ("Models", ()),
    "objects": ("Objects", ()),
}
ALBUMS = ("music", "ambiance", "effects")  # types sorted by album
MISCELLANEOUS = "miscellaneous"


@dataclass(frozen=True)
class Licence:
    name: str
    deed: str           # where its terms are ("" for a purchased one: its own file has them)
    credit: bool        # needs crediting
    share_alike: bool   # changed versions must be offered under the same licence
    give_away: bool     # its original files may be passed on


LICENCES: dict[str, Licence] = {
    "CC0-1.0": Licence("CC0 1.0 (public domain)",
                       "https://creativecommons.org/publicdomain/zero/1.0/", False, False, True),
    "CC-BY-4.0": Licence("CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/",
                         True, False, True),
    "CC-BY-3.0": Licence("CC BY 3.0", "https://creativecommons.org/licenses/by/3.0/",
                         True, False, True),
    "CC-BY-SA-4.0": Licence("CC BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0/",
                            True, True, True),
    "CC-BY-SA-3.0": Licence("CC BY-SA 3.0", "https://creativecommons.org/licenses/by-sa/3.0/",
                            True, True, True),
    "Purchased": Licence("Purchased", "", False, False, False),
    "Own-Work": Licence("Own work (all rights reserved)", "", False, False, False),
}
PURCHASED = "Purchased"
OWN_WORK = "Own-Work"  # your own, all rights reserved: your games use it, no one else
# A version 1 asset's id: made from its path in this namespace, so it is the same every time.
_V1_NAMESPACE = uuid.UUID("6a1d4f0e-5b8c-4e2a-9f37-0c1d2e3f4a5b")


class LibraryError(Exception):
    """Shown to the user."""


def today() -> str:
    return datetime.date.today().isoformat()


def slug(name: str) -> str:
    """A folder name from an asset's name: lower case, words joined by underscores."""
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s or "asset"


def sha256(file: Path) -> str:
    h = hashlib.sha256()
    with open(file, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fingerprint(files: list[dict]) -> str:
    """The asset's files as one SHA-256: a line "<path>\\t<sha256>\\n" per file, sorted by path."""
    lines = sorted((f["path"], f["sha256"]) for f in files)
    text = "".join(f"{path}\t{digest}\n" for path, digest in lines)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---- a library ---------------------------------------------------------------------------------
@dataclass
class Library:
    root: Path
    id: str = ""
    name: str = "Master Asset Library"
    created: str = ""

    @staticmethod
    def create(root: Path, name: str = "Master Asset Library") -> "Library":
        """A new Master library in `root` (made if needed); LibraryError if one is there."""
        root = Path(root)
        if (root / LIBRARY_FILE).exists():
            raise LibraryError(f"{root} already holds a library")
        lib = Library(root, str(uuid.uuid4()), name, today())
        root.mkdir(parents=True, exist_ok=True)
        lib.save()
        return lib

    @staticmethod
    def open(root: Path) -> "Library":
        root = Path(root)
        try:
            doc = json.loads((root / LIBRARY_FILE).read_text("utf-8"))
        except (OSError, ValueError) as e:
            raise LibraryError(f"{root} isn't a library ({LIBRARY_FILE}: {e})") from e
        if not isinstance(doc, dict) or doc.get("kind") != "master" or not doc.get("id"):
            raise LibraryError(f"{root}: {LIBRARY_FILE} isn't a Master library's")
        if not isinstance(doc.get("format"), int) or doc["format"] > FORMAT:
            raise LibraryError(f"{root} was made by a newer program (format {doc.get('format')})")
        return Library(root, doc["id"], doc.get("name", "Master Asset Library"),
                       doc.get("created", ""))

    @staticmethod
    def open_or_create(root: Path) -> "Library":
        return Library.open(root) if (Path(root) / LIBRARY_FILE).exists() \
            else Library.create(root)

    def save(self) -> None:
        doc = {"format": FORMAT, "kind": "master", "id": self.id, "name": self.name,
               "created": self.created}
        _write_json(self.root / LIBRARY_FILE, doc)

    def type_folder(self, type_: str, category: str = "") -> Path:
        return type_folder(self.root, type_, category)

    def scan(self) -> tuple[list["Asset"], list[str]]:
        return scan(self.root)


def is_library(folder: Path) -> bool:
    """Whether a folder holds a Master library (its library.json)."""
    return (Path(folder) / LIBRARY_FILE).is_file()


def type_folder(root: Path, type_: str, category: str = "") -> Path:
    """Where assets of a type (and kind, or album) go in a library."""
    if type_ not in TYPES:
        raise LibraryError(f"there is no asset type '{type_}'")
    kinds = TYPES[type_][1]
    if kinds and category not in kinds:
        raise LibraryError(f"textures are one of: {', '.join(kinds)}")
    folder = Path(root) / type_
    if type_ in ALBUMS:
        return folder / slug(category or MISCELLANEOUS)
    return folder / category if category else folder


# ---- an asset ----------------------------------------------------------------------------------
@dataclass
class Asset:
    folder: Path   # its own folder
    root: Path     # its library's folder
    name: str
    type: str
    id: str = ""
    version: int = 1
    category: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    licence: str = "CC0-1.0"
    author: str = ""
    source: str = ""
    title: str = ""
    imported: str = ""
    files: list[dict] = field(default_factory=list)  # {"path", "sha256", "bytes"}
    fingerprint: str = ""
    purchase: dict | None = None
    origin: dict | None = None
    read_format: int = FORMAT  # the format it was read in (1: written back only when changed)

    @property
    def path(self) -> str:
        """Its folder from its library's: "textures/metal/rusty_plates"."""
        return self.folder.relative_to(self.root).as_posix()

    @property
    def size(self) -> int:
        return sum(int(f.get("bytes", 0)) for f in self.files)

    def to_json(self) -> dict:
        return {"format": FORMAT, "id": self.id, "version": self.version, "name": self.name,
                "type": self.type, "category": self.category, "description": self.description,
                "tags": self.tags, "licence": self.licence, "author": self.author,
                "source": self.source, "title": self.title, "imported": self.imported,
                "files": self.files, "fingerprint": self.fingerprint,
                "purchase": self.purchase, "origin": self.origin}


def read(folder: Path, root: Path) -> Asset:
    """An asset from its folder's asset.json (format 1 or 2); LibraryError if it can't be read."""
    folder, root = Path(folder), Path(root)
    try:
        doc = json.loads((folder / METADATA).read_text("utf-8"))
    except (OSError, ValueError) as e:
        raise LibraryError(f"{folder.name}: {METADATA} can't be read: {e}") from e
    if not isinstance(doc, dict) or doc.get("format") not in (1, 2):
        raise LibraryError(f"{folder.name}: {METADATA} isn't one this program reads")
    files = [f for f in doc.get("files", []) if isinstance(f, dict) and "path" in f]
    asset = Asset(folder=folder, root=root, name=str(doc.get("name", folder.name)),
                  type=str(doc.get("type", "")), files=files, read_format=doc["format"],
                  **{k: str(doc.get(k) or "") for k in ("category", "description", "licence",
                                                        "author", "source", "title",
                                                        "imported")})
    if doc["format"] == 1:
        asset.id = str(uuid.uuid5(_V1_NAMESPACE, asset.path))
        asset.fingerprint = fingerprint(files)
        return asset
    asset.id = str(doc.get("id") or uuid.uuid5(_V1_NAMESPACE, asset.path))
    asset.version = int(doc.get("version") or 1)
    asset.tags = [str(t) for t in doc.get("tags") or []]
    asset.fingerprint = str(doc.get("fingerprint") or fingerprint(files))
    asset.purchase = doc.get("purchase") if isinstance(doc.get("purchase"), dict) else None
    asset.origin = doc.get("origin") if isinstance(doc.get("origin"), dict) else None
    return asset


def scan(root: Path) -> tuple[list[Asset], list[str]]:
    """Every asset in a library (by type, category, then name), and what couldn't be read."""
    root = Path(root)
    assets, problems_found = [], []
    if not root.is_dir():
        return assets, problems_found
    for meta in sorted(root.rglob(METADATA)):
        try:
            assets.append(read(meta.parent, root))
        except LibraryError as e:
            problems_found.append(str(e))
    assets.sort(key=lambda a: (a.type, a.category, a.name.lower()))
    return assets, problems_found


def record_files(asset: Asset) -> bool:
    """Its files as they are now (every file in its folder but its own two), and its
    fingerprint. Returns whether they changed (its version goes up when they did)."""
    before = asset.fingerprint
    asset.files = [{"path": p.relative_to(asset.folder).as_posix(), "sha256": sha256(p),
                    "bytes": p.stat().st_size}
                   for p in sorted(asset.folder.rglob("*"))
                   if p.is_file() and p.relative_to(asset.folder).as_posix() not in OWN_FILES]
    asset.fingerprint = fingerprint(asset.files)
    changed = bool(before) and before != asset.fingerprint
    if changed:
        asset.version += 1
    return changed


def problems(asset: Asset, contents: bool = True) -> list[str]:
    """What is wrong with an asset (none: all well): its type, licence, credit, purchase and
    files (and, with `contents`, whether its files are still as recorded: that reads them all,
    so lists of many assets leave it out)."""
    out = []
    if asset.type not in TYPES:
        out.append(f"there is no asset type '{asset.type}'")
    licence = LICENCES.get(asset.licence)
    if licence is None:
        out.append(f"its licence, '{asset.licence or 'none'}', isn't one the library takes "
                   f"({', '.join(LICENCES)})")
    elif needs_credit(asset):
        if not asset.author.strip():
            out.append("it needs crediting: its author is needed")
        if not (asset.title.strip() or asset.source.strip()):
            out.append("it needs crediting: its title or source is needed")
    if asset.licence == OWN_WORK and not asset.author.strip():
        out.append("it is your own work: its artist (author) is needed")
    if asset.licence == PURCHASED:
        p = asset.purchase or {}
        if not str(p.get("seller", "")).strip():
            out.append("it was bought: who sold it is needed")
        licence_file = str(p.get("licence_file", ""))
        if not licence_file:
            out.append("it was bought: the seller's licence is needed, kept with it")
        elif not any(f["path"] == licence_file for f in asset.files):
            out.append(f"its licence file, {licence_file}, isn't one of its files")
    if not asset.files:
        out.append("it has no files")
    for f in asset.files:
        path = asset.folder / f.get("path", "")
        if not path.is_file():
            out.append(f"{f.get('path')} is missing")
        elif contents and f.get("sha256") and sha256(path) != f["sha256"]:
            out.append(f"{f.get('path')} has changed since it was recorded")
    return out


# ---- licences and credits ----------------------------------------------------------------------
def needs_credit(asset: Asset) -> bool:
    licence = LICENCES.get(asset.licence)
    if licence is None:
        return False
    if asset.licence == PURCHASED:
        return bool((asset.purchase or {}).get("credit"))
    return licence.credit


def share_alike(asset: Asset) -> bool:
    return asset.licence in LICENCES and LICENCES[asset.licence].share_alike


def may_give_away(asset: Asset) -> bool:
    """Whether its original files may be passed on (in a shared project, a sample set)."""
    return asset.licence in LICENCES and LICENCES[asset.licence].give_away


def credit(asset: Asset) -> str:
    """Its credit: '"Rusty Plates" by Ana Ruiz (https://example.org/rusty), CC BY 4.0
    (https://creativecommons.org/licenses/by/4.0/)'."""
    licence = LICENCES.get(asset.licence)
    name, deed = (licence.name, licence.deed) if licence else (asset.licence, "")
    if asset.licence == PURCHASED:
        p = asset.purchase or {}
        name = f"from {p.get('seller')}" if p.get("seller") else "purchased"
    text = f'"{asset.title or asset.name}" by {asset.author or "an unknown author"}'
    if asset.source:
        text += f" ({asset.source})"
    return f"{text}, {name}" + (f" ({deed})" if deed else "")


def credits(assets: list[Asset]) -> list[str]:
    """The credits the assets need, each once, in order."""
    return sorted({credit(a) for a in assets if needs_credit(a)})


# ---- writing -----------------------------------------------------------------------------------
def licence_text(asset: Asset) -> str:
    """LICENSE.md: the asset's description and licence, for people."""
    licence = LICENCES.get(asset.licence)
    lines = [f"# {asset.name}", ""]
    if asset.description:
        lines += [asset.description, ""]
    if licence:
        lines.append(f"- Licence: {licence.name}" + (f" ({licence.deed})" if licence.deed
                                                       else ""))
    else:
        lines.append(f"- Licence: {asset.licence}")
    for label, value in (("Title", asset.title), ("Author", asset.author),
                         ("Source", asset.source), ("Imported", asset.imported)):
        if value:
            lines.append(f"- {label}: {value}")
    if asset.tags:
        lines.append(f"- Tags: {', '.join(asset.tags)}")
    if asset.licence == PURCHASED and asset.purchase:
        p = asset.purchase
        lines += ["", "Bought:", ""]
        for label, key in (("Seller", "seller"), ("Product", "product"), ("Order", "order"),
                           ("Date", "date"), ("The seller's licence", "licence_file")):
            if p.get(key):
                lines.append(f"- {label}: {p[key]}")
        lines += ["", "Its original files may not be given away."]
    if share_alike(asset):
        lines += ["", "Share-alike: changed versions of it must be offered under the same "
                  "licence."]
    if needs_credit(asset):
        lines += ["", "Credit (shown in a game's credits):", "", credit(asset)]
    lines += ["", "## Files", ""] + [f"- {f['path']}" for f in asset.files]
    return "\n".join(lines) + "\n"


def _write_json(path: Path, doc: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n", "utf-8")
    tmp.replace(path)


def write(asset: Asset) -> None:
    """Its asset.json and LICENSE.md (as format 2; an id is made if it has none)."""
    asset.folder.mkdir(parents=True, exist_ok=True)
    if not asset.id:
        asset.id = str(uuid.uuid4())
    if not asset.fingerprint:
        asset.fingerprint = fingerprint(asset.files)
    _write_json(asset.folder / METADATA, asset.to_json())
    (asset.folder / LICENCE_FILE).write_text(licence_text(asset), "utf-8")
    asset.read_format = FORMAT


def free_folder(parent: Path, name: str) -> Path:
    """parent/<slug of name>, or with _2, _3 … when that is taken."""
    base = slug(name)
    folder, n = parent / base, 2
    while folder.exists():
        folder = parent / f"{base}_{n}"
        n += 1
    return folder


def remove(asset: Asset) -> None:
    """The asset's folder deleted (with everything in it), and its empty parents."""
    shutil.rmtree(asset.folder)
    parent = asset.folder.parent
    while parent != asset.root and parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent


# ---- copying -----------------------------------------------------------------------------------
def copy_asset(asset: Asset, to_root: Path, *, from_library: str = "") -> Asset:
    """A copy of the asset in another library, at the same path (or beside it, numbered, when
    that is taken): its whole folder, its id, version and fingerprint kept. Copied from a Master
    (`from_library`, its id), the copy records where it came from in its origin."""
    to_root = Path(to_root)
    parent = to_root / Path(asset.path).parent
    target = to_root / asset.path
    if target.exists():
        target = free_folder(parent, asset.folder.name)
    shutil.copytree(asset.folder, target)
    copy = read(target, to_root)
    if from_library:
        copy.origin = {"library": from_library, "path": asset.path, "version": asset.version,
                       "fingerprint": asset.fingerprint, "copied": today()}
    copy.id, copy.version, copy.fingerprint = asset.id, asset.version, asset.fingerprint
    write(copy)
    return copy


def find(assets: list[Asset], asset_id: str) -> Asset | None:
    return next((a for a in assets if a.id == asset_id), None)


def newer_in(master: list[Asset], copy: Asset) -> Asset | None:
    """The Master's asset when it is newer than a project's copy of it."""
    original = find(master, copy.id)
    if original is None or not copy.origin:
        return None
    return original if original.version > int(copy.origin.get("version", 0)) else None


def changed_here(copy: Asset) -> bool:
    """Whether a project's copy has been changed since it was copied."""
    return bool(copy.origin) and copy.origin.get("fingerprint") != fingerprint(copy.files)
