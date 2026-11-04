# SPDX-License-Identifier: Apache-2.0
"""Bringing assets into a library: files, folders and zips (downloads are untrusted: a zip can't
write outside the library, files must be what their names say, and only the types an asset can
hold are kept), and collecting what a Midgard project's own library already has.

Assets are always copied in, never linked; the originals stay where they are."""
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

from . import library_format as lf
from .gltf_bounds import gltf_document
from .roles import IMAGES, TEXTURE_ROLES

AUDIO = (".ogg", ".opus", ".wav", ".mp3", ".flac")
MODEL_SUFFIXES = (".glb", ".gltf")
# The files each type may hold (besides text about them: licences, read-mes, receipts).
ALLOWED: dict[str, tuple[str, ...]] = {
    "gui": IMAGES,
    "fonts": (".ttf", ".otf", ".fnt", ".png"),
    "textures": IMAGES,
    "images": IMAGES,
    "icons": IMAGES + (".ico",),
    "music": AUDIO,
    "ambiance": AUDIO,
    "effects": AUDIO,
    "models": (".glb", ".gltf", ".bin") + IMAGES,
    "objects": (".glb", ".gltf", ".bin", ".json") + IMAGES,
}
TEXT = (".md", ".txt", ".pdf")
MAX_IMPORT_BYTES = 4 << 30  # a zip's contents, at most (4 GB)
WORK = ".import"            # the library's scratch folder while importing (removed after)


@dataclass
class ImportResult:
    """What an import made, and what it left out."""
    assets: list[lf.Asset] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (file, why)
    warnings: list[str] = field(default_factory=list)
    refused: list[tuple[str, str]] = field(default_factory=list)  # (an asset's name, why)

    def summary(self) -> str:
        """'Imported 2 assets; skipped 14 files: 9 .fbx, 4 .blend, 1 .exe.'"""
        n = len(self.assets)
        parts = [f"Imported {n} asset{'' if n == 1 else 's'}"]
        if self.skipped:
            parts.append(skipped_summary(self.skipped))
        for name, why in self.refused:
            parts.append(f"{name} not imported: {why}")
        return "; ".join(parts) + "."


def skipped_summary(skipped: list[tuple[str, str]]) -> str:
    """'skipped 14 files: 9 .fbx, 4 .blend, 1 .exe' (by ending, most first)."""
    counts: dict[str, int] = {}
    for rel, _why in skipped:
        ext = Path(rel).suffix.lower() or "(no ending)"
        counts[ext] = counts.get(ext, 0) + 1
    listed = ", ".join(f"{n} {ext}" for ext, n in sorted(counts.items(),
                                                          key=lambda kv: (-kv[1], kv[0])))
    return f"skipped {len(skipped)} file{'' if len(skipped) == 1 else 's'}: {listed}"


def gltf_dependencies(file: Path) -> list[str]:
    """The relative files a .gltf refers to (buffers and images), as written in it."""
    if file.suffix.lower() != ".gltf":
        return []
    doc = gltf_document(file) or {}
    uris = [item.get("uri", "") for key in ("buffers", "images") for item in doc.get(key, [])
            if isinstance(item, dict)]
    return [u for u in uris if u and not u.startswith("data:") and "://" not in u]


def looks_like(path: Path) -> str | None:
    """What is wrong with a file's contents for its ending (None: it looks right)."""
    ext = path.suffix.lower()
    try:
        with open(path, "rb") as f:
            head = f.read(16)
    except OSError as e:
        return f"can't be read: {e}"
    if ext == ".png":
        ok = head.startswith(b"\x89PNG\r\n\x1a\n")
    elif ext in (".jpg", ".jpeg"):
        ok = head.startswith(b"\xff\xd8\xff")
    elif ext == ".ktx2":
        ok = head.startswith(b"\xabKTX 20\xbb")
    elif ext == ".ico":
        ok = head[:4] == b"\x00\x00\x01\x00"
    elif ext == ".glb":
        ok = head.startswith(b"glTF")
    elif ext in (".gltf", ".json"):
        ok = gltf_document(path) is not None if ext == ".gltf" else _is_json_object(path)
    elif ext in (".ogg", ".opus"):
        ok = head.startswith(b"OggS")
    elif ext == ".wav":
        ok = head[:4] == b"RIFF" and head[8:12] == b"WAVE"
    elif ext == ".mp3":
        ok = head.startswith(b"ID3") or (len(head) > 1 and head[0] == 0xFF and
                                         head[1] & 0xE0 == 0xE0)
    elif ext == ".flac":
        ok = head.startswith(b"fLaC")
    elif ext in (".ttf", ".otf"):
        ok = head[:4] in (b"\x00\x01\x00\x00", b"OTTO", b"true")
    elif ext == ".pdf":
        ok = head.startswith(b"%PDF")
    else:
        ok = True  # (.bin buffers, .fnt descriptions, text: nothing to check)
    return None if ok else f"isn't a {ext} file inside"


def _is_json_object(path: Path) -> bool:
    import json
    try:
        return isinstance(json.loads(path.read_text("utf-8")), dict)
    except (OSError, ValueError, UnicodeDecodeError):
        return False


def gathered(sources: list[Path], scratch: Path) -> list[tuple[Path, str]]:
    """The files to import, each with its path in the asset: loose files by name, a folder's
    files as they are under it, a zip's (opened into `scratch`, never outside it) likewise."""
    out: list[tuple[Path, str]] = []
    for source in (Path(s) for s in sources):
        if source.is_dir():
            out += [(p, p.relative_to(source).as_posix())
                    for p in sorted(source.rglob("*")) if p.is_file()]
        elif source.suffix.lower() == ".zip":
            out += _unzipped(source, scratch / lf.slug(source.stem))
        elif source.is_file():
            out.append((source, source.name))
        else:
            raise lf.LibraryError(f"{source} isn't there")
    return out


def _unzipped(source: Path, target: Path) -> list[tuple[Path, str]]:
    unpacked: list[tuple[Path, str]] = []
    try:
        z = zipfile.ZipFile(source)
    except (OSError, zipfile.BadZipFile) as e:
        raise lf.LibraryError(f"{source.name} can't be opened as a zip: {e}") from e
    with z:
        total = 0
        for info in z.infolist():
            name = info.filename
            if info.is_dir() or name.startswith("__MACOSX/") or Path(name).name.startswith("._"):
                continue
            parts = Path(name).parts
            if name.startswith(("/", "\\")) or ".." in parts or ":" in name:
                raise lf.LibraryError(f"{source.name}: '{name}' would land outside the library "
                                      "(refused)")
            total += info.file_size
            if total > MAX_IMPORT_BYTES:
                raise lf.LibraryError(f"{source.name} is larger than 4 GB unpacked")
            dest = target / Path(*parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(dest, "wb") as out_file:
                shutil.copyfileobj(src, out_file)
            unpacked.append((dest, Path(*parts).as_posix()))
    # A single top folder (as zips often have): its contents, without it.
    tops = {rel.split("/", 1)[0] for _p, rel in unpacked}
    if len(tops) == 1 and all("/" in rel for _p, rel in unpacked):
        unpacked = [(p, rel.split("/", 1)[1]) for p, rel in unpacked]
    return unpacked


def sorted_files(files: list[tuple[Path, str]], type_: str) -> tuple[list[tuple[Path, str]],
                                                                     list[tuple[str, str]]]:
    """The files an asset of the type keeps (text about it always), and those it leaves out,
    each with why: a type it can't hold, or contents that aren't what the name says."""
    allowed = ALLOWED[type_]
    kept, skipped = [], []
    for p, rel in files:
        ext = p.suffix.lower()
        if ext not in TEXT and ext not in allowed:
            skipped.append((rel, f"{lf.TYPES[type_][0].lower()} can't use {ext or 'it'}"))
        elif (why := looks_like(p)) is not None:
            skipped.append((rel, why))
        else:
            kept.append((p, rel))
    return kept, skipped


def find_duplicate(root: Path, file: Path) -> lf.Asset | None:
    """An asset already holding a file with these contents."""
    digest = lf.sha256(file)
    assets, _ = lf.scan(root)
    return next((a for a in assets if any(f.get("sha256") == digest for f in a.files)), None)


# ---- texture sets ------------------------------------------------------------------------------
def images_in(sources: list[Path]) -> list[str]:
    """The pictures files, folders and zips hold, by their path in an asset (as an import would
    put them), to choose their roles before importing."""
    with tempfile.TemporaryDirectory(prefix="master_images_") as scratch:
        return [rel for p, rel in gathered([Path(s) for s in sources], Path(scratch))
                if p.suffix.lower() in IMAGES]


def text_files_in(sources: list[Path]) -> list[str]:
    """The text files (licences, read-mes) files, folders and zips hold, by their path in an
    asset, to choose the seller's licence among them before importing."""
    with tempfile.TemporaryDirectory(prefix="master_text_") as scratch:
        return [rel for p, rel in gathered([Path(s) for s in sources], Path(scratch))
                if p.suffix.lower() in TEXT]


def _combined(roughness: Path | None, metallic: Path | None, out: Path) -> Path | None:
    """The combined picture glTF reads (roughness in green, metallic in blue), from separate
    roughness and metallic maps (a missing one: rough, not metal)."""
    from PySide6.QtGui import QImage
    maps = {k: QImage(str(p)) for k, p in (("r", roughness), ("m", metallic)) if p is not None}
    if not maps or any(img.isNull() for img in maps.values()):
        return None
    size = next(iter(maps.values())).size()
    w, h = size.width(), size.height()

    def grey(img, fill: int) -> bytes:  # one byte a pixel, rows unpadded
        if img is None:
            return bytes([fill]) * (w * h)
        g = img.scaled(size).convertToFormat(QImage.Format.Format_Grayscale8)
        data, stride = bytes(g.constBits()), g.bytesPerLine()
        return b"".join(data[y * stride:y * stride + w] for y in range(h))

    pixels = bytearray(w * h * 4)  # (RGB32 in memory: blue, green, red, alpha)
    pixels[0::4] = grey(maps.get("m"), 0)
    pixels[1::4] = grey(maps.get("r"), 255)
    pixels[3::4] = bytes([255]) * (w * h)
    image = QImage(bytes(pixels), w, h, w * 4, QImage.Format.Format_RGB32)
    return out if image.save(str(out)) else None


def named_by_role(files: list[tuple[Path, str]], roles: dict[str, str], name: str,
                  scratch: Path) -> tuple[list[tuple[Path, str]], list[tuple[str, str]]]:
    """A texture set's files renamed by role (<name>_<role>.<ext>), pictures "not used" left
    out, and the combined metallic & roughness made from separate maps. LibraryError if two
    pictures have the same role."""
    base = lf.slug(name)
    out, skipped, by_role = [], [], {}
    for p, rel in files:
        if p.suffix.lower() not in IMAGES:
            out.append((p, rel))  # (text about it, kept as it is)
            continue
        role = roles.get(rel, "")
        if not role:
            skipped.append((rel, "not used"))
            continue
        if role not in TEXTURE_ROLES:
            raise lf.LibraryError(f"'{role}' isn't a role a picture can have")
        if role in by_role:
            raise lf.LibraryError(f"{by_role[role][1]} and {rel} are both "
                                  f"{TEXTURE_ROLES[role].lower()}: one picture each")
        by_role[role] = (p, rel)
        out.append((p, f"{base}_{role}{p.suffix.lower()}"))
    if ("roughness" in by_role or "metallic" in by_role) and "metallic_roughness" not in by_role:
        made = _combined(by_role.get("roughness", (None,))[0],
                         by_role.get("metallic", (None,))[0],
                         scratch / f"{base}_metallic_roughness.png")
        if made is not None:
            out.append((made, made.name))
    return out, skipped


# ---- models ------------------------------------------------------------------------------------
def model_groups(kept: list[tuple[Path, str]]) -> list[tuple[str, list[tuple[Path, str]]]]:
    """The models among the files, each with what goes with it: the files a .gltf names, the
    pictures named after it (or all of its folder's, when the folder has no other model), and
    the text about them all. Files with no one model are left over (the last group, "")."""
    text = [(p, rel) for p, rel in kept if p.suffix.lower() in TEXT]
    models = [(p, rel) for p, rel in kept if p.suffix.lower() in MODEL_SUFFIXES]
    taken: set[str] = set()
    groups = []

    def folder_of(rel: str) -> str:
        return rel.rsplit("/", 1)[0] if "/" in rel else ""

    for p, rel in models:
        folder = folder_of(rel)
        mine = [(p, rel)]
        for uri in gltf_dependencies(p):
            dep = (folder + "/" if folder else "") + unquote(uri)
            mine += [(q, r) for q, r in kept if r == dep]
        alone = sum(1 for _q, r in models if folder_of(r) == folder) == 1
        for q, r in kept:
            if q.suffix.lower() in IMAGES and folder_of(r) == folder and \
                    (alone or q.stem.lower().startswith(p.stem.lower())) and \
                    all(r != m for _m, m in mine):
                mine.append((q, r))
        taken |= {r for _q, r in mine}
        groups.append((p.stem, mine + text))
    left = [(q, r) for q, r in kept if r not in taken and q.suffix.lower() not in TEXT]
    if left:
        groups.append(("", left))
    return groups


def model_count(sources: list[Path]) -> int:
    """How many models (.glb, .gltf) files, folders and zips hold (to ask about splitting)."""
    n = 0
    for s in (Path(s) for s in sources):
        if s.is_dir():
            n += sum(1 for p in s.rglob("*") if p.suffix.lower() in MODEL_SUFFIXES)
        elif s.suffix.lower() == ".zip":
            try:
                with zipfile.ZipFile(s) as z:
                    n += sum(1 for name in z.namelist()
                             if Path(name).suffix.lower() in MODEL_SUFFIXES and
                             not name.startswith("__MACOSX/"))
            except (OSError, zipfile.BadZipFile):
                pass
        elif s.suffix.lower() in MODEL_SUFFIXES:
            n += 1
    return n


def pretty(stem: str) -> str:
    """'oak_tree-01' -> 'Oak tree 01'."""
    import re
    words = re.sub(r"[_\-]+", " ", stem).strip()
    return words[:1].upper() + words[1:] if words else stem


# ---- importing ---------------------------------------------------------------------------------
@dataclass
class Details:
    """What an import says about its assets."""
    category: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    licence: str = "CC0-1.0"
    author: str = ""
    source: str = ""
    title: str = ""
    purchase: dict | None = None


def _make(root: Path, files: list[tuple[Path, str]], type_: str, name: str,
          details: Details) -> lf.Asset:
    """An asset from files already sorted. LibraryError if it can't be made (nothing usable,
    already in the library, its licence): nothing is left behind then."""
    content = [(p, rel) for p, rel in files if p.suffix.lower() not in TEXT]
    if not content:
        raise lf.LibraryError("there is nothing usable (only text, or files it can't use)")
    if (twin := find_duplicate(root, content[0][0])) is not None:
        raise lf.LibraryError(f"{content[0][1]} is in the library already, as "
                              f"'{twin.name}' ({twin.path})")
    folder = lf.free_folder(lf.type_folder(root, type_, details.category), name)
    asset = lf.Asset(folder=folder, root=root, name=name, type=type_,
                     category=details.category, description=details.description.strip(),
                     tags=list(details.tags), licence=details.licence,
                     author=details.author.strip(), source=details.source.strip(),
                     title=details.title.strip(), imported=lf.today(),
                     purchase=dict(details.purchase) if details.purchase else None)
    try:
        for p, rel in files:
            dest = folder / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest)
        lf.record_files(asset)
        said = lf.problems(asset)
        if said:
            raise lf.LibraryError("; ".join(said))
        lf.write(asset)
    except BaseException:
        if folder.exists():
            lf.remove(asset)
        raise
    return asset


def import_assets(root: Path, sources: list[Path], type_: str, name: str,
                  details: Details | None = None, *, split: bool = False,
                  roles: dict[str, str] | None = None) -> ImportResult:
    """Files, folders and zips into the library: one asset, or (split, for models) one for each
    model with what goes with it and the pack's text. Files it can't use are skipped, and why;
    an asset that can't be made is refused (and why) without stopping the rest. `roles` (for
    textures: each picture's path, as images_in gives them, to its role) renames the pictures
    <name>_<role> and leaves out those not used."""
    root = Path(root)
    details = details or Details()
    if type_ not in lf.TYPES:
        raise lf.LibraryError(f"there is no asset type '{type_}'")
    name = name.strip()
    if not name:
        raise lf.LibraryError("an asset needs a name")
    result = ImportResult()
    work = root / WORK
    work.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(dir=work, prefix="import_") as scratch:
            files = gathered([Path(s) for s in sources], Path(scratch))
            if not files:
                raise lf.LibraryError("there is nothing to import")
            kept, result.skipped = sorted_files(files, type_)
            if roles is not None and type_ == "textures":
                kept, unused = named_by_role(kept, roles, name, Path(scratch))
                result.skipped += unused
            groups = [(name, kept)]
            if split and type_ in ("models", "objects"):
                found = model_groups(kept)
                if sum(1 for stem, _g in found if stem) > 1:
                    groups = [(f"{name}: {pretty(stem)}", g) for stem, g in found if stem]
                    leftover = next((g for stem, g in found if not stem), [])
                    result.skipped += [(r, "with no one model") for _q, r in leftover]
            for asset_name, group in groups:
                try:
                    asset = _make(root, group, type_, asset_name, details)
                except lf.LibraryError as e:
                    result.refused.append((asset_name, str(e)))
                    continue
                result.assets.append(asset)
                result.warnings += [f"{asset.name}: {w}" for w in _missing_parts(asset)]
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return result


def _missing_parts(asset: lf.Asset) -> list[str]:
    """A .gltf naming files that aren't with it (left out, or never there)."""
    out = []
    for gltf in asset.folder.rglob("*.gltf"):
        for uri in gltf_dependencies(gltf):
            if not (gltf.parent / unquote(uri)).is_file():
                out.append(f"{gltf.relative_to(asset.folder).as_posix()} names {unquote(uri)}, "
                           "which isn't with it")
    return out


# ---- collecting from Midgard projects ----------------------------------------------------------
@dataclass
class CollectResult:
    collected: list[lf.Asset] = field(default_factory=list)
    already: list[str] = field(default_factory=list)                # names in the Master already
    changed: list[str] = field(default_factory=list)                # changed copies of the Master's
    refused: list[tuple[str, str]] = field(default_factory=list)    # (name, why)
    unreadable: list[str] = field(default_factory=list)

    def summary(self) -> str:
        n = len(self.collected)
        parts = [f"Collected {n} asset{'' if n == 1 else 's'}"]
        if self.already:
            parts.append(f"{len(self.already)} already in the Master")
        if self.changed:
            parts.append(f"{len(self.changed)} changed in the project since they were copied "
                         "from the Master (left there)")
        if self.refused:
            parts.append(f"{len(self.refused)} not collected")
        if self.unreadable:
            parts.append(f"{len(self.unreadable)} couldn't be read")
        return "; ".join(parts) + "."


def project_library(folder: Path) -> Path | None:
    """A Midgard project's library folder (the project folder, its {name}.config, or the
    library folder itself), or None if there is none."""
    folder = Path(folder)
    if folder.is_file() and folder.suffix == ".config":
        folder = folder.parent
    if folder.name == "library" and folder.is_dir():
        return folder
    lib = folder / "library"
    return lib if lib.is_dir() else None


def collect(master: lf.Library, project: Path) -> CollectResult:
    """A Midgard project's library assets copied into the Master: each once (one with the same
    files is there already), its licence and details kept. A project's copy of a Master asset
    changed since (its files differ from the Master's) is left: it is the project's own now."""
    result = CollectResult()
    lib = project_library(project)
    if lib is None:
        raise lf.LibraryError(f"{project} isn't a Midgard project with an Asset Library")
    theirs, result.unreadable = lf.scan(lib)
    ours, _ = master.scan()
    prints = {a.fingerprint for a in ours}
    for asset in theirs:
        if asset.fingerprint in prints:
            result.already.append(asset.name)
            continue
        if asset.origin and asset.origin.get("library") == master.id and \
                lf.find(ours, asset.id) is not None:
            result.changed.append(asset.name)
            continue
        if said := lf.problems(asset):
            result.refused.append((asset.name, "; ".join(said)))
            continue
        copy = lf.copy_asset(asset, master.root)
        copy.origin = None  # (in the Master it is an original)
        if lf.find(ours, copy.id) is not None:  # (two projects' version 1 assets at one path)
            import uuid
            copy.id = str(uuid.uuid4())
        ours.append(copy)
        if not copy.imported:
            copy.imported = lf.today()
        lf.write(copy)
        result.collected.append(copy)
        prints.add(copy.fingerprint)
    return result
