# SPDX-License-Identifier: Apache-2.0
"""A glTF model's extent (its meshes' boxes where its nodes place them), read from the file, so
the player can frame it. (As Midgard's Asset Library reads it.)"""
import json
import struct
from pathlib import Path

Matrix = list[list[float]]


def _node_matrix(node: dict) -> Matrix:
    """A glTF node's own transform, as rows of a 4 x 4 matrix (its "matrix", or its
    translation, rotation and scale)."""
    if "matrix" in node:
        m = node["matrix"]  # (column by column)
        return [[m[c * 4 + r] for c in range(4)] for r in range(4)]
    tx, ty, tz = node.get("translation", [0.0, 0.0, 0.0])
    x, y, z, w = node.get("rotation", [0.0, 0.0, 0.0, 1.0])
    sx, sy, sz = node.get("scale", [1.0, 1.0, 1.0])
    rot = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
           [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
           [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    rows = [[rot[r][0] * sx, rot[r][1] * sy, rot[r][2] * sz, (tx, ty, tz)[r]] for r in range(3)]
    return rows + [[0.0, 0.0, 0.0, 1.0]]


def _times(a: Matrix, b: Matrix) -> Matrix:
    return [[sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]


def gltf_document(path: Path) -> dict | None:
    """The JSON of a .glb's first chunk, or of a .gltf; None if it can't be read."""
    try:
        data = Path(path).read_bytes()
        if data[:4] == b"glTF":
            length = struct.unpack_from("<I", data, 12)[0]
            doc = json.loads(data[20:20 + length])
        else:
            doc = json.loads(data.decode("utf-8"))
    except (OSError, ValueError, struct.error, UnicodeDecodeError):
        return None
    return doc if isinstance(doc, dict) else None


def model_bounds(path: Path) -> tuple[list[float], list[float]] | None:
    """A model's box (low and high corners), as it is drawn; None if it has no meshes."""
    doc = gltf_document(path)
    if doc is None:
        return None
    accessors, meshes, nodes = (doc.get(k, []) for k in ("accessors", "meshes", "nodes"))
    lo, hi = [float("inf")] * 3, [float("-inf")] * 3

    def take(mesh_index: int, m: Matrix) -> None:
        if not 0 <= mesh_index < len(meshes):
            return
        for prim in meshes[mesh_index].get("primitives", []):
            index = prim.get("attributes", {}).get("POSITION")
            if index is None or index >= len(accessors):
                continue
            acc = accessors[index]
            if "min" not in acc or "max" not in acc:
                continue
            for corner in range(8):
                p = [(acc["max"] if corner >> k & 1 else acc["min"])[k] for k in range(3)]
                q = [sum(m[r][k] * p[k] for k in range(3)) + m[r][3] for r in range(3)]
                for k in range(3):
                    lo[k], hi[k] = min(lo[k], q[k]), max(hi[k], q[k])

    placed = False

    def walk(index: int, parent: Matrix, depth: int = 0) -> None:
        nonlocal placed
        if not 0 <= index < len(nodes) or depth > 64:
            return
        node = nodes[index]
        m = _times(parent, _node_matrix(node))
        if "mesh" in node:
            take(node["mesh"], m)
            placed = True
        for child in node.get("children", []):
            walk(child, m, depth + 1)

    identity = [[float(r == c) for c in range(4)] for r in range(4)]
    scenes = doc.get("scenes", [])
    scene = doc.get("scene", 0)
    roots = scenes[scene].get("nodes", []) if 0 <= scene < len(scenes) else []
    for root in roots:
        walk(root, identity)
    if not placed:
        for i in range(len(meshes)):
            take(i, identity)
    return (lo, hi) if lo[0] != float("inf") else None
