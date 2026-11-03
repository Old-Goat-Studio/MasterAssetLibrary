# Master Asset Library

One library of every asset you have (downloaded, bought, made yourself, or collected from your
[Midgard](https://github.com/Old-Goat-Studio/Midgard) projects), that each Midgard project's
own Asset Library takes copies from.

- Projects keep their **own copies**, so a project is always complete by itself: it exports,
  moves to another computer and goes into version control without the Master.
- Every asset keeps its **description and licence** (CC0, CC-BY with automatic credits, and
  purchased assets with their seller, order and licence text), and a fingerprint so a project
  can tell when the Master has a newer version.
- Midgard and this program follow one written [library format](docs/library_format.md).

## Running it from source

```
python -m venv .venv
.venv\Scripts\pip install -e .[dev]
.venv\Scripts\python -m master_library
```

## Tests and checks

```
.venv\Scripts\pytest -q
.venv\Scripts\ruff check .
```

## Packaging

`python tools/package.py --installer` (on Windows, with Inno Setup 6) raises the build number
and makes `build\installer\MasterAssetLibrary-Setup-<version>.<build>.exe`.

## Licence

Apache License 2.0 (see `LICENSE`). Third-party components: `THIRD_PARTY_NOTICES.md`.
