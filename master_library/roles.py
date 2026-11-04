# SPDX-License-Identifier: Apache-2.0
"""A texture set's pictures and their roles (colour, normal, roughness …), as Midgard reads
them: by their names (<name>_<role>.png), or guessed from the common packs' namings."""
import re
from pathlib import Path

IMAGES = (".png", ".jpg", ".jpeg", ".ktx2")

TEXTURE_ROLES: dict[str, str] = {
    "color": "Colour",
    "normal": "Normal",
    "roughness": "Roughness",
    "metallic": "Metallic",
    "metallic_roughness": "Metallic & roughness (combined)",
    "occlusion": "Ambient occlusion",
    "emissive": "Emissive",
    "": "Not used (left out)",
}
# Words in file names that say a role (ambientCG's, Poly Haven's and others' namings).
_ROLE_WORDS = (
    # (A "combined" map: occlusion in red, roughness in green, metallic in blue: glTF reads its
    # green and blue as its metallic & roughness.)
    ("metallic_roughness", ("metallicroughness", "roughnessmetallic", "orm", "arm", "mr",
                            "combined")),
    ("color", ("color", "colour", "basecolor", "basecolour", "albedo", "diffuse", "diff",
               "col", "base", "basecol")),
    ("normal", ("normal", "normalgl", "normaldx", "nor", "norm", "nrm", "nor_gl", "normal_gl")),
    ("roughness", ("roughness", "rough", "rgh")),
    ("metallic", ("metallic", "metalness", "metal", "met")),
    ("occlusion", ("ambientocclusion", "occlusion", "ao")),
    ("emissive", ("emissive", "emission", "emit", "glow")),
)


def guess_role(filename: str) -> str:
    """A picture's role from its name ("rock_Color.png": "color"; "" when it doesn't say, or
    it is a kind Midgard doesn't use, like a height map)."""
    words = [w for w in re.split(r"[^a-z0-9]+", Path(filename).stem.lower()) if w]
    joined = "".join(words)
    # The role word is usually last ("Metal_Floor_001_Emissive" is emissive, not metallic): the
    # words are read from the end.
    for word in reversed(words):
        for role, names in _ROLE_WORDS:
            if word in names:
                return role
    for role, names in _ROLE_WORDS:
        if any(joined.endswith(n) for n in names if len(n) > 4):
            return role
    return ""


def texture_set(paths: list[Path]) -> dict[str, Path]:
    """A texture asset's pictures by role: from their names (<name>_<role>), or guessed from
    them; a lone picture is its colour."""
    pictures = [p for p in paths if p.suffix.lower() in IMAGES and p.is_file()]
    found: dict[str, Path] = {}
    named = sorted((r for r in TEXTURE_ROLES if r), key=len, reverse=True)  # (longest first)
    for p in pictures:
        stem = p.stem.lower()
        role = next((r for r in named if stem.endswith("_" + r)), "") or guess_role(p.name)
        if role and role not in found:
            found[role] = p
    if not found and len(pictures) == 1:
        found["color"] = pictures[0]
    return found
