#!/usr/bin/env python3
"""Verify the GIS assets and advertised downloads after Quarto copies them."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
RELATIVE = Path("assets/files/datasets/historical-gis")

def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()

def verify(base):
    lines = (base / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
    for line in lines:
        expected, name = line.split("  ", 1)
        path = base / name
        if not path.is_file() or digest(path) != expected:
            raise SystemExit("Historical GIS asset missing or changed: " + str(path))
    for item in json.loads((base / "downloads.json").read_text())["items"]:
        path = base / item["url"]
        if not path.is_file():
            raise SystemExit("Historical GIS download missing: " + str(path))
        if "size_bytes" in item and path.stat().st_size != item["size_bytes"]:
            raise SystemExit("Historical GIS download size mismatch: " + str(path))
        if "sha256" in item and digest(path) != item["sha256"]:
            raise SystemExit("Historical GIS download checksum mismatch: " + str(path))
    for figure in json.loads((base / "gallery.json").read_text()):
        for field in ("image", "thumbnail"):
            name = figure.get(field)
            if not name:
                continue
            prefix = RELATIVE.as_posix() + "/"
            if name.startswith(prefix):
                name = name[len(prefix):]
            if not (base / name).is_file():
                raise SystemExit("Historical GIS gallery image missing: " + figure[field])
    print("Validated", len(lines), "historical GIS assets in", base)

for folder in (ROOT / RELATIVE, ROOT / "docs" / RELATIVE):
    verify(folder)
if (ROOT / RELATIVE / "SHA256SUMS.txt").read_bytes() != (ROOT / "docs" / RELATIVE / "SHA256SUMS.txt").read_bytes():
    raise SystemExit("Historical GIS source and website checksum catalogues differ")
