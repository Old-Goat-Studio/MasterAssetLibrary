# The library format

Version 2. Followed by the Master Asset Library and by Midgard (a project's Asset Library), so
assets move between them as plain folders. Version 1 is what Midgard 5.13a wrote; every version 1
asset is a valid version 2 asset, and readers of version 2 read both.

## A library

A library is a folder of asset folders, one folder per type (and per kind, or album), one folder
per asset:

```
<library>/
    library.json                         (a Master library only: below)
    textures/metal/rusty_plates/         an asset: its files, and
        asset.json                       what programs read (below)
        LICENSE.md                       the same for people, written from asset.json
        rusty_plates_basecolor.png ...
    models/superhero/ ...
    music/<album, or miscellaneous>/<asset>/ ...
```

- **A Master library** is any folder with a `library.json` in it (by default
  `Documents\Master Asset Library`).
- **A project's library** is the `library/` folder in a Midgard project. It has no
  `library.json`: the project is what it belongs to.

An asset's **path** is its folder relative to the library, with `/` between parts:
`textures/metal/rusty_plates`. Folder names are lower case, words joined by `_` (made from the
asset's name; a number is added, `_2`, when the name is taken).

### Types, kinds and albums

| Folder | Name shown | Sorted into | Files it may hold |
|---|---|---|---|
| `gui` | GUI | | .png .jpg .jpeg .ktx2 |
| `fonts` | Fonts | | .ttf .otf .fnt .png |
| `textures` | Textures | a kind: metal, wood, stone, concrete, bark, brick, fabric, floor, ground, leather, road, roof, wall, miscellaneous | .png .jpg .jpeg .ktx2 |
| `images` | Images | | .png .jpg .jpeg .ktx2 |
| `icons` | Icons | | .png .jpg .jpeg .ktx2 .ico |
| `music` | Music | an album (its name), or miscellaneous | .ogg .opus .wav .mp3 .flac |
| `ambiance` | Ambiance | an album, or miscellaneous | as music |
| `effects` | FX | an album, or miscellaneous | as music |
| `models` | Models | | .glb .gltf .bin and images |
| `objects` | Objects | | .glb .gltf .bin .json and images |

Any asset may also keep text about itself: `.md`, `.txt`, `.pdf` (licences, read-mes, receipts).

## library.json (a Master library)

```json
{
  "format": 2,
  "kind": "master",
  "id": "5f0c2a3e-8a3b-4d0e-9a51-1d2b6c7e8f90",
  "name": "Master Asset Library",
  "created": "2026-11-03"
}
```

- `id`: made once, when the library is made (a random UUID). A project's copy of an asset
  records it, so it knows which Master the asset came from.

## asset.json

```json
{
  "format": 2,
  "id": "0b7e4c1d-3f2a-4e59-8c6b-2a9d1e7f5c33",
  "version": 3,
  "name": "Rusty Plates",
  "type": "textures",
  "category": "metal",
  "description": "Riveted steel plates, rusted at the seams.",
  "tags": ["sci-fi", "industrial"],
  "licence": "CC-BY-4.0",
  "author": "Ana Ruiz",
  "source": "https://example.org/rusty",
  "title": "Rusty Plates",
  "imported": "2026-11-03",
  "files": [
    {"path": "rusty_plates_basecolor.png", "sha256": "9f2c…", "bytes": 1048576}
  ],
  "fingerprint": "41d8…",
  "purchase": null,
  "origin": null
}
```

| Field | Meaning |
|---|---|
| `format` | 2 (1 for assets written before this format; see *Version 1* below). |
| `id` | The asset's own id (a random UUID), the same in the Master and in every project's copy of it. |
| `version` | 1 when it is first imported; one more each time its files change. |
| `name`, `type`, `category`, `description` | What it is and where it goes (the category is the texture kind, or the album). |
| `tags` | Words to find it by (lower case). |
| `licence` | One of the licences below. |
| `author`, `source`, `title` | Who made it, where it came from, the work's own title (for its credit). |
| `imported` | The date it came into this library (`YYYY-MM-DD`). |
| `files` | Every file of the asset but `asset.json` and `LICENSE.md`: its path in the asset folder (with `/`), its SHA-256 and its size. |
| `fingerprint` | The asset's files as one SHA-256 (below): equal fingerprints, the same files. |
| `purchase` | For a purchased asset: where it was bought (below); otherwise `null`. |
| `origin` | In a project's copy: where it was copied from (below); otherwise `null`. |

### The fingerprint

The SHA-256 of one line per file, `<path>` then a tab then `<sha256>` then a newline, the lines
sorted by path (as UTF-8 bytes). `asset.json` and `LICENSE.md` are never part of it. So an
asset's fingerprint changes when, and only when, its files do.

### Licences

| `licence` | Name | Credit needed | May be given away as originals |
|---|---|---|---|
| `CC0-1.0` | CC0 1.0 (public domain) | no | yes |
| `CC-BY-4.0` | CC BY 4.0 | yes | yes, with the credit |
| `CC-BY-3.0` | CC BY 3.0 | yes | yes, with the credit |
| `CC-BY-SA-4.0` | CC BY-SA 4.0 | yes | yes, with the credit, and changed versions under the same licence |
| `CC-BY-SA-3.0` | CC BY-SA 3.0 | yes | as CC BY-SA 4.0 |
| `Purchased` | Purchased | if its licence asks (`purchase.credit`) | **no** |

- **Credit needed:** the asset's `author`, and its `title` or `source`, are required, and games
  using it list its credit (`"Rusty Plates" by Ana Ruiz (https://example.org/rusty), CC BY 4.0
  (https://creativecommons.org/licenses/by/4.0/)`) in their CREDITS.txt.
- **Share-alike (CC BY-SA)** is marked, so you decide each time: a game that changes the asset
  (recolours it, cuts it up) must offer the changed asset under CC BY-SA too.
- **Purchased** assets may be used in your games (where they are cooked into the game's own
  files) but their original files are never given away: not copied into anything shared (sample
  sets, a project sent to someone else) without a warning first.

### purchase

```json
{
  "seller": "Example Asset Store",
  "product": "Fantasy Village Pack",
  "order": "SS-104455",
  "date": "2026-08-14",
  "licence_file": "LICENSE-purchase.txt",
  "credit": false
}
```

- `licence_file`: the seller's licence, kept in the asset's folder as one of its files (so it is
  in `files` and travels with every copy).
- `credit`: whether the licence asks for a credit; if so the asset is credited like CC BY.

### origin (a project's copy)

```json
{
  "library": "5f0c2a3e-8a3b-4d0e-9a51-1d2b6c7e8f90",
  "path": "textures/metal/rusty_plates",
  "version": 3,
  "fingerprint": "41d8…",
  "copied": "2026-11-04"
}
```

The Master it came from (`library.json`'s `id`), the asset's path there, and its version and
fingerprint when it was copied. When the Master's asset with the same `id` has a higher version,
the project can offer the newer one. When the copy's own fingerprint no longer matches
`origin.fingerprint`, the copy has been changed in the project.

## LICENSE.md

Written from `asset.json` whenever it is written, for people: the asset's name and description,
its licence (with its deed), title, author, source, the date it came in, its credit if it needs
one, what was bought and from whom if purchased, and its files. Programs never read it.

## Version 1

Midgard 5.13a's assets (`"format": 1`) have no `id`, `version`, `tags`, `fingerprint`,
`purchase` or `origin`, and only the CC0 and CC BY licences. Read as version 2, they get an `id`
(a UUID made from their library path, so it stays the same each time they are read), version 1,
no tags, and the fingerprint of their files. They are written back as version 2 only when they
are changed.

## Copying

Assets are always **copied** between libraries, never linked: a project's library is complete by
itself. Copying an asset copies its whole folder, writes `origin` into the copy's `asset.json`,
and leaves the asset's `id`, `version` and `fingerprint` as they are.
