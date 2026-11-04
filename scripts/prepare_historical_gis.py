#!/usr/bin/env python3
"""Assemble downloadable GIS editions from versioned source assets.

The compressed database is a build input. The public ZIP is generated for
GitHub Pages, avoiding duplicate binary archives in the Git history.
Only Python's standard library is needed during the website build.
"""
from pathlib import Path
import hashlib
import json
import lzma
import os
import shutil
import sqlite3
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets/files/datasets/historical-gis"
SOURCE_DIRECTORY = ROOT / "data_sources/historical-gis"
SOURCE_MANIFEST = SOURCE_DIRECTORY / "parts.json"
STAMP = ASSETS / ".archive-inputs.sha256"
DATE = (2026, 11, 4, 0, 0, 0)

def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def copied(source, target):
    """Flush and verify a closed artifact before replacing its destination."""
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".complete")
    with source.open("rb") as reader, partial.open("wb") as writer:
        shutil.copyfileobj(reader, writer, 8 * 1024 * 1024)
        writer.flush()
        os.fsync(writer.fileno())
    if digest(source) != digest(partial):
        raise IOError("Incomplete artifact transfer: " + str(target))
    os.replace(partial, target)

def member(archive, source, name):
    info = zipfile.ZipInfo(name, date_time=DATE)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    with source.open("rb") as reader, archive.open(info, "w", force_zip64=True) as writer:
        shutil.copyfileobj(reader, writer, 8 * 1024 * 1024)

def package(path, files):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, source in sorted(files.items()):
            member(archive, source, name)
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise IOError("Corrupt ZIP member: " + bad)

def publish_catalogue():
    """Describe the files actually supplied and pin every public asset."""
    catalogue = [
        ("Public research edition 0.6.1", "GeoPackage with 46 registered tables, four district geographies, core CSV tables, documentation, quality flags, examples and the R source package. Provider source geometries are linked upstream.", "GIS_Czech_Lands_Public_v0_6_1.zip", "ZIP · GeoPackage + CSV", True),
        ("Complete tabular edition", "CSV tables for all four geographies, full monthly and annual climate panels, railway series, geographical modules, dictionaries and source links. No GIS software required.", "GIS_Czech_Lands_Tables_v0_6_1.zip", "ZIP · CSV / CSV.GZ", False),
        ("Historical map atlas", "42 thematic maps in 39 original-resolution PNG figures, with the gallery catalogue, explanatory captions and source documentation.", "Czech_Lands_Historical_Atlas_42_maps.zip", "ZIP · PNG", False),
        ("histCzechia 0.2.1", "Companion R source package. Reads public edition 0.6.1 and the earlier research releases; installation and examples are included. Not on CRAN.", "histCzechia_0.2.1.tar.gz", "R source · TAR.GZ", False),
        ("District core: judicial districts 1930", "444 source fields for 330 districts, excluding the separately supplied climate normals.", "data/gis_master_judicial_1930_public_v061.csv", "CSV", False),
        ("Climate normals: judicial districts 1930", "18 CRU-derived normal fields, plus geography and district ID. Join explicitly to the core to recover all 462 fields.", "data/climate_normals_judicial_1930.csv", "CSV", False),
        ("Monthly climate: judicial districts 1930", "150,480 district-months for 1901–1938; ten climate variables and station-support diagnostics.", "data/climate_monthly_judicial_1930.csv.gz", "CSV.GZ", False),
        ("Annual climate: judicial districts 1930", "12,540 district-years, seasonal summaries and anomalies.", "data/climate_annual_judicial_1930.csv.gz", "CSV.GZ", False),
        ("Full variable dictionary", "2,259 documented fields across the retained public tables; the browser dictionary covers the 462-field main district record.", "data/GIS_PUBLIC_DATA_DICTIONARY.csv", "CSV", False),
        ("Getting started", "File guide, district geographies, QGIS instructions, explicit joins and Python/R examples.", "docs/README_PUBLIC_EDITION.md", "Markdown", False),
        ("Methods and quality", "Definitions, geographical coverage, known qualifications, display masks and the version 0.6.1 railway correction.", "docs/METHODS_AND_QUALITY.md", "Markdown", False),
        ("Sources and reuse", "Citations, source dates, provider conditions and redistribution notes. Each component retains its own terms.", "docs/SOURCES_AND_REUSE.md", "Markdown", False),
    ]
    items = []
    for title, description, name, format_name, primary in catalogue:
        path = ASSETS / name
        if not path.is_file():
            raise FileNotFoundError(name)
        items.append(dict(title=title, description=description, url=name,
                          format=format_name, size_bytes=path.stat().st_size,
                          sha256=digest(path), primary=primary))
    items.append(dict(title="File checksums", description="SHA-256 fingerprints for every published GIS file, including the three ZIP editions and the R source package.", url="SHA256SUMS.txt", format="SHA-256"))
    (ASSETS / "downloads.json").write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    checksums = []
    for path in sorted(ASSETS.rglob("*")):
        if (not path.is_file() or path.name in ("SHA256SUMS.txt", STAMP.name)
                or any(part.startswith(".") for part in path.relative_to(ASSETS).parts)
                or "__pycache__" in path.parts or path.suffix == ".pyc"):
            continue
        checksums.append(digest(path) + "  " + path.relative_to(ASSETS).as_posix())
    (ASSETS / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    print("Published", len(items), "download entries and", len(checksums), "asset checksums.")

def main():
    manifest = json.loads((ASSETS / "release_manifest.json").read_text())
    source_manifest = json.loads(SOURCE_MANIFEST.read_text())
    source_parts = [SOURCE_DIRECTORY / item["name"] for item in source_manifest["parts"]]
    for path, item in zip(source_parts, source_manifest["parts"]):
        if path.stat().st_size != item["size_bytes"] or digest(path) != item["sha256"]:
            raise ValueError("Compressed database part differs from its manifest: " + path.name)
    table_parts = []
    for table in source_manifest.get("tables", []):
        paths = [SOURCE_DIRECTORY / item["name"] for item in table["parts"]]
        table_parts.extend(paths)
        for path, item in zip(paths, table["parts"]):
            if path.stat().st_size != item["size_bytes"] or digest(path) != item["sha256"]:
                raise ValueError("Compressed table part differs from its manifest: " + path.name)
        target = ASSETS / table["public_path"]
        if not target.is_file() or digest(target) != table["combined_sha256"]:
            with tempfile.TemporaryDirectory(prefix="gis_table_build_") as tmp:
                assembled = Path(tmp) / target.name
                with assembled.open("wb") as writer:
                    for path in paths:
                        with path.open("rb") as reader:
                            shutil.copyfileobj(reader, writer, 8 * 1024 * 1024)
                if digest(assembled) != table["combined_sha256"]:
                    raise ValueError("Reassembled table checksum mismatch: " + target.name)
                copied(assembled, target)
    common = {p.relative_to(ASSETS).as_posix(): p
              for folder in ("docs", "code", "audit")
              for p in (ASSETS / folder).rglob("*") if p.is_file()
              and "__pycache__" not in p.parts and p.suffix != ".pyc"}
    for name in ("CITATION.cff", "citation.bib", "sources.json", "release_manifest.json"):
        common[name] = ASSETS / name
    common["README.md"] = ASSETS / "docs/README_PUBLIC_EDITION.md"
    for required in ("docs/README_PUBLIC_EDITION.md", "docs/METHODS_AND_QUALITY.md",
                     "histCzechia_0.2.1.tar.gz"):
        if not (ASSETS / required).is_file():
            raise FileNotFoundError(required)
    primary = dict(common)
    primary["r_package/histCzechia_0.2.1.tar.gz"] = ASSETS / "histCzechia_0.2.1.tar.gz"
    for p in (ASSETS / "data").iterdir():
        if (p.name.startswith(("gis_master_", "climate_normals_", "GIS_"))
                or p.name in ("publication_quality_flags.csv", "district_index.csv")):
            primary["data/" + p.name] = p
    # The CSV edition includes canonical full-geography analysis tables. The
    # per-geography climate files remain directly downloadable on the website.
    tabular = dict(common)
    for p in (ASSETS / "data").iterdir():
        if p.is_file() and not p.name.startswith(("climate_monthly_", "climate_annual_")):
            tabular["data/" + p.name] = p
    gallery = {name: p for name, p in common.items()
               if name.startswith("docs/") or name in ("CITATION.cff", "citation.bib", "sources.json")}
    gallery["gallery.json"] = ASSETS / "gallery.json"
    for p in (ASSETS / "maps").glob("*.png"):
        gallery["maps/" + p.name] = p
    inputs = set(primary.values()) | set(tabular.values()) | set(gallery.values()) | set(source_parts) | set(table_parts) | {SOURCE_MANIFEST, Path(__file__)}
    signature = hashlib.sha256("\n".join(
        str(p.relative_to(ROOT)) + ":" + digest(p) for p in sorted(inputs)
    ).encode()).hexdigest()
    names = ("GIS_Czech_Lands_Public_v0_6_1.zip", "GIS_Czech_Lands_Tables_v0_6_1.zip",
             "Czech_Lands_Historical_Atlas_42_maps.zip")
    if STAMP.exists() and STAMP.read_text().strip() == signature and all((ASSETS / n).is_file() for n in names):
        print("Historical GIS download archives are current.")
        publish_catalogue()
        return
    with tempfile.TemporaryDirectory(prefix="gis_download_build_") as tmp:
        work = Path(tmp)
        database = work / manifest["public_gpkg_name"]
        compressed = work / "historical_gis_czech_lands_v061.gpkg.xz"
        with compressed.open("wb") as writer:
            for path in source_parts:
                with path.open("rb") as reader:
                    shutil.copyfileobj(reader, writer, 8 * 1024 * 1024)
        if digest(compressed) != source_manifest["combined_sha256"]:
            raise ValueError("Combined compressed database checksum mismatch")
        with lzma.open(compressed, "rb") as reader, database.open("wb") as writer:
            shutil.copyfileobj(reader, writer, 8 * 1024 * 1024)
        if digest(database) != manifest["public_gpkg_sha256"]:
            raise ValueError("Public database checksum does not match its release manifest.")
        with sqlite3.connect("file:" + str(database) + "?mode=ro", uri=True) as db:
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert not db.execute("PRAGMA foreign_key_check").fetchall()
            assert db.execute("SELECT count(*) FROM gpkg_contents").fetchone()[0] == 46
        primary["outputs/" + database.name] = database
        for name, contents in zip(names, (primary, tabular, gallery)):
            path = work / name
            package(path, contents)
            copied(path, ASSETS / name)
            print("Prepared", name, path.stat().st_size, "bytes")
    STAMP.write_text(signature + "\n")
    publish_catalogue()

if __name__ == "__main__":
    main()
