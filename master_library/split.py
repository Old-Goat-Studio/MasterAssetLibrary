# SPDX-License-Identifier: Apache-2.0
"""Splitting a pack: a model file holding many objects (a showcase of trees, a scatter of rocks)
made into one model file per object, each with only its own meshes, materials and textures.

The objects are where the file's node tree first branches, below the wrappers exporters add
(Sketchfab's "Sketchfab_model" → "<id>.fbx" → "RootNode", say). An object holding detail levels
(children named …LOD0, …LOD1 …) can keep only its most detailed one. Each object keeps its
size and which way is up (the transforms above it), and is moved so the middle of its base is at
the origin, ready to place."""
import json
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

from .gltf_bounds import _node_matrix, _times

Matrix = list[list[float]]
IDENTITY: Matrix = [[float(r == c) for c in range(4)] for r in range(4)]
# Extensions whose data can't be copied piece by piece (compressed meshes and textures).
CANT_SPLIT = ("KHR_draco_mesh_compression", "EXT_meshopt_compression", "KHR_texture_basisu",
              "EXT_texture_webp", "KHR_mesh_quantization")
_LOD = re.compile(r"(?:^|[^a-z])lod[ _]?(\d+)", re.IGNORECASE)


class SplitError(Exception):
    """Shown to the user."""


@dataclass
class PackObject:
    node: int                 # its node in the pack
    name: str                 # its name, made readable
    parent: Matrix            # the transforms above it (its parent's, in the file's world)
    triangles: int = 0
    size: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])  # metres
    levels: int = 1           # its detail levels (1: none)


# ---- reading -----------------------------------------------------------------------------------
@dataclass
class Pack:
    path: Path
    doc: dict
    binary: bytes  # a .glb's binary chunk ("" for a .gltf: its buffers are files beside it)

    @staticmethod
    def read(path: Path) -> "Pack":
        path = Path(path)
        data = path.read_bytes()
        if data[:4] == b"glTF":
            if len(data) < 20:
                raise SplitError(f"{path.name} is damaged")
            length, kind = struct.unpack_from("<II", data, 12)
            doc = json.loads(data[20:20 + length])
            rest = data[20 + length:]
            binary = b""
            if len(rest) >= 8 and struct.unpack_from("<I", rest, 4)[0] == 0x004E4942:
                size = struct.unpack_from("<I", rest, 0)[0]
                binary = rest[8:8 + size]
        else:
            doc = json.loads(data.decode("utf-8"))
            binary = b""
        if not isinstance(doc, dict):
            raise SplitError(f"{path.name} isn't a glTF model")
        stuck = [e for e in doc.get("extensionsRequired", []) if e in CANT_SPLIT]
        if stuck:
            raise SplitError(f"{path.name} is compressed ({', '.join(stuck)}): it can't be "
                             "split here")
        return Pack(path, doc, binary)

    def buffer(self, index: int) -> bytes:
        """A buffer's bytes: the .glb's own, or a file beside a .gltf (or data: inline)."""
        b = self.doc["buffers"][index]
        uri = b.get("uri")
        if uri is None:
            return self.binary
        if uri.startswith("data:"):
            import base64
            return base64.b64decode(uri.split(",", 1)[1])
        from urllib.parse import unquote
        return (self.path.parent / unquote(uri)).read_bytes()

    def view_bytes(self, index: int) -> bytes:
        v = self.doc["bufferViews"][index]
        data = self._buffers.setdefault(v["buffer"], self.buffer(v["buffer"]))
        start = v.get("byteOffset", 0)
        return data[start:start + v["byteLength"]]

    def __post_init__(self):
        self._buffers: dict[int, bytes] = {}

    # ---- its objects ----------------------------------------------------------------------
    def nodes(self) -> list[dict]:
        return self.doc.get("nodes", [])

    def roots(self) -> list[int]:
        scenes = self.doc.get("scenes", [])
        scene = self.doc.get("scene", 0)
        if 0 <= scene < len(scenes):
            return list(scenes[scene].get("nodes", []))
        return [i for i in range(len(self.nodes()))]

    def objects(self, best_only: bool = True) -> list[PackObject]:
        """The pack's objects: where its node tree first branches, below single wrappers."""
        nodes = self.nodes()
        level, parent = self.roots(), IDENTITY
        while len(level) == 1 and "mesh" not in nodes[level[0]] and \
                nodes[level[0]].get("children"):
            parent = _times(parent, _node_matrix(nodes[level[0]]))
            level = list(nodes[level[0]]["children"])
        found = [PackObject(i, nodes[i].get("name", f"object {n + 1}"), parent)
                 for n, i in enumerate(level)]
        names = clean_names([o.name for o in found])
        for o, name in zip(found, names, strict=True):
            o.name = name
            o.levels = len(self.levels(o.node))
            lo, hi, o.triangles = self.extent(o.node, o.parent, best_only)
            o.size = [round(b - a, 3) for a, b in zip(lo, hi, strict=True)] if lo else [0, 0, 0]
        return [o for o in found if o.triangles > 0]

    def levels(self, node: int) -> list[int]:
        """An object's detail levels (its children named …LOD<n>), most detailed first."""
        kids = self.nodes()[node].get("children", [])
        lods = []
        for k in kids:
            m = _LOD.search(self.nodes()[k].get("name", ""))
            if m:
                lods.append((int(m.group(1)), k))
        return [k for _n, k in sorted(lods)] if len(lods) == len(kids) and len(lods) > 1 else []

    def kept_children(self, node: int, best_only: bool) -> list[int]:
        levels = self.levels(node)
        if best_only and levels:
            return levels[:1]
        return list(self.nodes()[node].get("children", []))

    def walk(self, node: int, parent: Matrix, best_only: bool, top: bool = True):
        """(node, its world matrix) for the object's nodes (only its best level, if wished)."""
        m = _times(parent, _node_matrix(self.nodes()[node]))
        yield node, m
        children = self.kept_children(node, best_only) if top else \
            self.nodes()[node].get("children", [])
        for c in children:
            yield from self.walk(c, m, best_only, top=False)

    def extent(self, node: int, parent: Matrix, best_only: bool):
        """The object's box (as drawn) and its triangles."""
        accessors = self.doc.get("accessors", [])
        meshes = self.doc.get("meshes", [])
        lo, hi, tris = [float("inf")] * 3, [float("-inf")] * 3, 0
        for n, m in self.walk(node, parent, best_only):
            mesh = self.nodes()[n].get("mesh")
            if mesh is None or not 0 <= mesh < len(meshes):
                continue
            for prim in meshes[mesh].get("primitives", []):
                pos = prim.get("attributes", {}).get("POSITION")
                if pos is None:
                    continue
                acc = accessors[pos]
                count = accessors[prim["indices"]]["count"] if "indices" in prim else acc["count"]
                tris += count // 3
                if "min" not in acc or "max" not in acc:
                    continue
                for corner in range(8):
                    p = [(acc["max"] if corner >> k & 1 else acc["min"])[k] for k in range(3)]
                    q = [sum(m[r][k] * p[k] for k in range(3)) + m[r][3] for r in range(3)]
                    for k in range(3):
                        lo[k], hi[k] = min(lo[k], q[k]), max(hi[k], q[k])
        return (lo, hi, tris) if lo[0] != float("inf") else (None, None, tris)


def clean_names(names: list[str]) -> list[str]:
    """Readable object names: exporters' endings gone ("_0", ".fbx"), a word every name ends
    with dropped ("rock46_lr", "rock44_lr": "Rock46", "Rock44"), and each name once."""
    def words(name: str) -> list[str]:
        name = re.sub(r"\.(fbx|obj|blend|max|ma|mb)$", "", name, flags=re.IGNORECASE)
        return [w for w in re.split(r"[_\s.]+", name) if w]

    split = [words(n) for n in names]
    while len(split) > 1 and all(len(w) > 1 for w in split) and \
            len({w[-1].lower() for w in split}) == 1:
        split = [w[:-1] for w in split]
    out, seen = [], {}
    for w in split:
        name = " ".join(w) or "Object"
        name = name[:1].upper() + name[1:]
        seen[name] = seen.get(name, 0) + 1
        out.append(name if seen[name] == 1 else f"{name} {seen[name]}")
    return out


# ---- writing one object ------------------------------------------------------------------------
def _texture_refs(value, out: list[dict]) -> None:
    """Every texture reference ({"index": n, …}) in a material, extensions included."""
    if isinstance(value, dict):
        for key, inner in value.items():
            if key.endswith("Texture") and isinstance(inner, dict) and "index" in inner:
                out.append(inner)
            _texture_refs(inner, out)
    elif isinstance(value, list):
        for inner in value:
            _texture_refs(inner, out)


def shrink_image(data: bytes, largest: int) -> bytes:
    """A PNG or JPEG made no larger than `largest` pixels on its longer side (as it is if it
    isn't larger, or can't be read)."""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
    from PySide6.QtGui import QImage
    image = QImage.fromData(data)
    if image.isNull() or max(image.width(), image.height()) <= largest:
        return data
    smaller = image.scaled(largest, largest, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
    out = QByteArray()
    buffer = QBuffer(out)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    jpeg = data[:2] == b"\xff\xd8"
    smaller.save(buffer, "JPG" if jpeg else "PNG", 92 if jpeg else -1)
    buffer.close()
    return bytes(out) if out.size() else data


def object_glb(pack: Pack, obj: PackObject, best_only: bool = True,
               largest_texture: int | None = None) -> bytes:
    """One object as a .glb of its own: its nodes, meshes, materials, textures and images (and
    only those), standing with the middle of its base at the origin. Textures larger than
    `largest_texture` pixels are made smaller."""
    import copy
    doc = pack.doc
    nodes = pack.nodes()
    for n, _m in pack.walk(obj.node, obj.parent, best_only):
        if "skin" in nodes[n]:
            raise SplitError(f"{obj.name} is skinned (a character): it can't be split out")
    # The object's nodes, renumbered; their meshes, materials … gathered as they're found.
    new_nodes: list[dict] = []
    maps = {key: {} for key in ("mesh", "material", "texture", "image", "sampler", "accessor",
                                "view")}
    out = {key: [] for key in ("meshes", "materials", "textures", "images", "samplers",
                               "accessors", "bufferViews")}
    blob = bytearray()

    def view(i: int) -> int:
        if i not in maps["view"]:
            data = pack.view_bytes(i)
            while len(blob) % 4:
                blob.append(0)
            old = doc["bufferViews"][i]
            v = {"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)}
            for key in ("byteStride", "target"):
                if key in old:
                    v[key] = old[key]
            blob.extend(data)
            maps["view"][i] = len(out["bufferViews"])
            out["bufferViews"].append(v)
        return maps["view"][i]

    def accessor(i: int) -> int:
        if i not in maps["accessor"]:
            a = copy.deepcopy(doc["accessors"][i])
            if "bufferView" in a:
                a["bufferView"] = view(a["bufferView"])
            sparse = a.get("sparse")
            if sparse:
                sparse["indices"]["bufferView"] = view(sparse["indices"]["bufferView"])
                sparse["values"]["bufferView"] = view(sparse["values"]["bufferView"])
            maps["accessor"][i] = len(out["accessors"])
            out["accessors"].append(a)
        return maps["accessor"][i]

    def image(i: int) -> int:
        if i not in maps["image"]:
            im = copy.deepcopy(doc["images"][i])
            data = None
            if "bufferView" in im:
                data = pack.view_bytes(im.pop("bufferView"))
            elif "uri" in im and not im["uri"].startswith("data:"):
                from urllib.parse import unquote
                data = (pack.path.parent / unquote(im.pop("uri"))).read_bytes()
            if data is not None:
                if largest_texture:
                    data = shrink_image(data, largest_texture)
                while len(blob) % 4:
                    blob.append(0)
                out["bufferViews"].append({"buffer": 0, "byteOffset": len(blob),
                                           "byteLength": len(data)})
                blob.extend(data)
                im["bufferView"] = len(out["bufferViews"]) - 1
                im.setdefault("mimeType", "image/png" if data[:4] == b"\x89PNG"
                              else "image/jpeg")
            maps["image"][i] = len(out["images"])
            out["images"].append(im)
        return maps["image"][i]

    def sampler(i: int) -> int:
        if i not in maps["sampler"]:
            maps["sampler"][i] = len(out["samplers"])
            out["samplers"].append(copy.deepcopy(doc["samplers"][i]))
        return maps["sampler"][i]

    def texture(i: int) -> int:
        if i not in maps["texture"]:
            t = copy.deepcopy(doc["textures"][i])
            if "source" in t:
                t["source"] = image(t["source"])
            if "sampler" in t:
                t["sampler"] = sampler(t["sampler"])
            for ext in t.get("extensions", {}).values():
                if isinstance(ext, dict) and "source" in ext:
                    ext["source"] = image(ext["source"])
            maps["texture"][i] = len(out["textures"])
            out["textures"].append(t)
        return maps["texture"][i]

    def material(i: int) -> int:
        if i not in maps["material"]:
            m = copy.deepcopy(doc["materials"][i])
            refs: list[dict] = []
            _texture_refs(m, refs)
            for ref in refs:
                ref["index"] = texture(ref["index"])
            maps["material"][i] = len(out["materials"])
            out["materials"].append(m)
        return maps["material"][i]

    def mesh(i: int) -> int:
        if i not in maps["mesh"]:
            m = copy.deepcopy(doc["meshes"][i])
            for prim in m.get("primitives", []):
                prim["attributes"] = {k: accessor(a) for k, a in prim["attributes"].items()}
                if "indices" in prim:
                    prim["indices"] = accessor(prim["indices"])
                if "material" in prim:
                    prim["material"] = material(prim["material"])
                if "targets" in prim:
                    prim["targets"] = [{k: accessor(a) for k, a in t.items()}
                                       for t in prim["targets"]]
            maps["mesh"][i] = len(out["meshes"])
            out["meshes"].append(m)
        return maps["mesh"][i]

    def copy_node(i: int, top: bool) -> int:
        old = nodes[i]
        n = {k: copy.deepcopy(v) for k, v in old.items()
             if k in ("name", "matrix", "translation", "rotation", "scale", "extras")}
        if "mesh" in old:
            n["mesh"] = mesh(old["mesh"])
        index = len(new_nodes)
        new_nodes.append(n)
        kids = pack.kept_children(i, best_only) if top else old.get("children", [])
        children = [copy_node(c, False) for c in kids]
        if children:
            n["children"] = children
        return index

    # The object, under its parents' transforms, moved to stand at the origin.
    lo, hi, _tris = pack.extent(obj.node, obj.parent, best_only)
    centre = [-(lo[0] + hi[0]) / 2, -lo[1], -(lo[2] + hi[2]) / 2] if lo else [0.0, 0.0, 0.0]
    new_nodes.append({"name": obj.name, "translation": centre, "children": [1]})
    p = obj.parent
    new_nodes.append({"name": "pack transforms",
                      "matrix": [p[r][c] for c in range(4) for r in range(4)]})
    new_nodes[1]["children"] = [copy_node(obj.node, True)]
    if all(abs(p[r][c] - IDENTITY[r][c]) < 1e-12 for r in range(4) for c in range(4)):
        new_nodes[1].pop("matrix")
    result = {"asset": {"version": "2.0",
                        "generator": "Master Asset Library: Split a pack"},
              "scene": 0, "scenes": [{"nodes": [0]}], "nodes": new_nodes}
    for key, items in out.items():
        if items:
            result[key] = items
    used = [e for e in doc.get("extensionsUsed", []) if e not in CANT_SPLIT]
    if used:
        result["extensionsUsed"] = used
    while len(blob) % 4:
        blob.append(0)
    result["buffers"] = [{"byteLength": len(blob)}]
    text = json.dumps(result, separators=(",", ":")).encode("utf-8")
    text += b" " * (-len(text) % 4)
    body = struct.pack("<II", len(text), 0x4E4F534A) + text + \
        struct.pack("<II", len(blob), 0x004E4942) + bytes(blob)
    return struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body


def split_to(pack_file: Path, folder: Path, chosen: list[PackObject] | None = None,
             best_only: bool = True,
             largest_texture: int | None = None) -> list[tuple[PackObject, Path]]:
    """The chosen objects (all, by default) written as .glb files into a folder."""
    pack = Pack.read(pack_file)
    objects = chosen if chosen is not None else pack.objects(best_only)
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    used: set[str] = set()
    for obj in objects:
        stem = re.sub(r"[^a-z0-9]+", "_", obj.name.lower()).strip("_") or "object"
        name, n = stem, 2
        while name in used:
            name, n = f"{stem}_{n}", n + 1
        used.add(name)
        path = folder / f"{name}.glb"
        path.write_bytes(object_glb(pack, obj, best_only, largest_texture))
        out.append((obj, path))
    return out
