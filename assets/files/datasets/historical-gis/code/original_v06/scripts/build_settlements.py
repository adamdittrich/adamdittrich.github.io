#!/usr/bin/env python3
"""Acquire CZ_RETRO and CSO historical population; link only supported geography.

CZ_RETRO is a multitemporal gazetteer snapshot, not a census of places in 1930.
CSO population data remain in the provider's 2015 municipality geography until a
historically justified crosswalk is available. No point-based reallocation of
municipality populations to historical districts is performed.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
import shapely


ROOT = Path(__file__).resolve().parents[1]
PACKAGED_BASE = ROOT / "inputs/base_v05_inputs.gpkg"
LEGACY_BASE = ROOT.parent / "gis_work/GIS_v04_Preparation/outputs/wave2_completed/historical_gis_czech_lands_v05.gpkg"
DEFAULT_BASE = PACKAGED_BASE if PACKAGED_BASE.exists() else LEGACY_BASE
LAYERS = {"judicial_1930": 330, "judicial_1921": 328, "political_1930": 151, "political_1921": 151}
MAP_URL = "https://geoportal.npu.cz/arcgis/rest/services/CZ_RETRO/CP_CZ_Retro_LS/MapServer"
LAYER_URL = MAP_URL + "/1"
QUERY_URL = LAYER_URL + "/query"
AUTHOR_URL = "https://sovamm.wordpress.com/projekty/aktualni-projekty-sovamm/cz_retro/"
CSU_PAGE = "https://csu.gov.cz/obyvatelstvo-a-domy-v-obcich-podle-vysledku-scitani-od-roku-1869"
CSU_ZIP = "https://csu.gov.cz/docs/107516/0c242a34-ca97-0209-581f-dde18a20a25f/170240-17data.zip?version=1.0"
CSU_SCHEMA = "https://csu.gov.cz/docs/107516/eb201fae-a878-a6be-6d42-a9959ec773aa/170240-17schema.json?version=1.0"
CSU_DOC = "https://csu.gov.cz/docs/107516/9378b376-1a8c-a995-c2a2-aa83cd1349e6/170240-17dds.pdf"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def write_gzip_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    """Publish a gzip CSV only after reading its complete trailer and contents.

    An interrupted write leaves at most a .part file; an existing final export
    remains intact. CSV parsing to EOF also verifies the gzip CRC and trailer.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    try:
        frame.to_csv(temporary, index=False, compression="gzip")
        with gzip.open(temporary, "rt", encoding="utf-8", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            header = next(reader)
            if header != [str(col) for col in frame.columns]:
                raise ValueError(f"Gzip CSV header validation failed: {path}")
            row_count = 0
            for row in reader:
                if len(row) != len(header):
                    raise ValueError(f"Gzip CSV column count validation failed: {path}")
                row_count += 1
            if row_count != len(frame):
                raise ValueError(f"Gzip CSV row count validation failed: {path}")
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def download(url: str, path: Path, params: dict | None = None) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        last = None
        for attempt in range(3):
            try:
                r = requests.get(url, params=params, timeout=(15, 90))
                r.raise_for_status()
                if path.suffix in (".json", ".geojson"):
                    parsed = r.json()
                    if "error" in parsed:
                        raise ValueError(f"Server returned error {parsed['error']}")
                tmp = path.with_suffix(path.suffix + ".part")
                tmp.write_bytes(r.content)
                tmp.replace(path)
                break
            except Exception as exc:
                last = exc
                if attempt == 2:
                    raise
                time.sleep(0.5 * (attempt + 1))
        if not path.exists():
            raise RuntimeError(str(last))
    return {"url": url, "parameters": params, "path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": digest(path)}


def acquire_gazetteer() -> tuple[gpd.GeoDataFrame, dict, list[dict]]:
    src = ROOT / "sources/settlements"
    pages = src / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    sources = []
    for name, url in [("cz_retro_service_metadata.json", MAP_URL), ("cz_retro_layer1_metadata.json", LAYER_URL)]:
        sources.append(download(url, src / name, {"f": "pjson"}))
    # Author's published terms are retained alongside the service copyright.
    sources.append(download(AUTHOR_URL, src / "cz_retro_author.html"))
    ids_path = src / "ids.json"
    sources.append(download(QUERY_URL, ids_path, {"where": "1=1", "returnIdsOnly": "true", "f": "json"}))
    meta = json.loads((src / "cz_retro_layer1_metadata.json").read_text())
    source_ids = sorted(json.loads(ids_path.read_text())["objectIds"])
    if not source_ids or len(source_ids) != len(set(source_ids)):
        raise ValueError("Empty or duplicate source object IDs")
    page_size = min(int(meta["maxRecordCount"]), 2000)
    blocks = [source_ids[i:i + page_size] for i in range(0, len(source_ids), page_size)]

    def page(job):
        i, ids = job
        p = pages / f"cz_retro_{i:03d}.geojson"
        params = {"where": f"OBJECTID >= {ids[0]} AND OBJECTID <= {ids[-1]}", "outFields": "*", "returnGeometry": "true", "outSR": "4326", "orderByFields": "OBJECTID", "f": "geojson"}
        m = download(QUERY_URL, p, params)
        obj = json.loads(p.read_text())
        feats = obj.get("features", [])
        got = [f["properties"]["OBJECTID"] for f in feats]
        if got != ids or obj.get("exceededTransferLimit", False) or obj.get("properties", {}).get("exceededTransferLimit", False):
            raise ValueError(f"Page {i} is truncated or no longer agrees with frozen source ID inventory")
        print(f"CZ_RETRO page {i+1}/{len(blocks)}: {len(feats)} records", flush=True)
        return i, m, feats

    downloaded = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = [pool.submit(page, job) for job in enumerate(blocks)]
        for job in as_completed(jobs):
            i, m, features = job.result()
            downloaded[i] = features
            sources.append(m)
    features = [f for i in range(len(blocks)) for f in downloaded[i]]
    data = gpd.GeoDataFrame.from_features(features, crs=4326)
    if len(data) != len(source_ids) or set(data.OBJECTID) != set(source_ids):
        raise ValueError("Incomplete or duplicate CZ_RETRO download")
    summary = {"source_record_count": len(source_ids), "page_count": len(blocks), "public_query_service": QUERY_URL, "source_service_copyright": json.loads((src / "cz_retro_service_metadata.json").read_text()).get("copyrightText", ""), "retrieved_utc": datetime.now(timezone.utc).isoformat()}
    return data, summary, sources


def build_gazetteer(base: Path) -> dict:
    out = ROOT / "modules/settlements"
    audit = ROOT / "audit"
    docs = ROOT / "docs"
    for p in (out, audit, docs):
        p.mkdir(parents=True, exist_ok=True)
    raw, acquisition, sources = acquire_gazetteer()
    tests = [{"test": "frozen_source_ids_all_downloaded_once", "status": "PASS", "detail": str(len(raw))}]
    # Preserve every raw field; add deliberately explicit reference identifiers.
    raw["gazetteer_record_id"] = "CZRETRO-OID-" + raw.OBJECTID.astype(str)
    raw["gazetteer_locality_id"] = raw.KOD_CZ.map(lambda x: "CZRETRO-" + str(int(x)) if pd.notna(x) else None)
    raw["gazetteer_snapshot_date"] = "2026-11-03"
    # An object-column pd.NA can be serialized by pyogrio as literal "<NA>".
    # Python None is written as a genuine SQL NULL in the GeoPackage.
    raw["historical_activity_year"] = None
    raw["temporal_status"] = "multitemporal_reference_gazetteer_not_1930_census"
    good = raw.geometry.notna() & ~raw.geometry.is_empty & raw.geometry.is_valid & raw.geometry.geom_type.eq("Point")
    excluded = raw.loc[~good].drop(columns="geometry")
    excluded.to_csv(audit / "settlements_excluded_geometry.csv", index=False)
    points = raw.loc[good].copy()
    # Administrative validity dates are NOT settlement foundation/destruction dates.
    for f in ["Platn_od", "Aktualiz", "platn_do", "PL_KK_OD", "AKT_KK", "PL_KK_DO", "AKT_G_KK", "Akt_G", "Akt_A"]:
        if f in points:
            points[f + "_utc"] = pd.to_datetime(points[f], unit="ms", utc=True, errors="coerce").dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    duplicate_codes = points.loc[points.KOD_CZ.duplicated(keep=False)].drop(columns="geometry")
    duplicate_codes.to_csv(audit / "settlements_repeated_locality_codes.csv", index=False)
    # Keep all provider records in the source layer; avoid inventing a primary
    # historical record when the provider has duplicate identifiers.
    subtype_meta = json.loads((ROOT / "sources/settlements/cz_retro_layer1_metadata.json").read_text())
    labels = {}
    renderer = subtype_meta.get("drawingInfo", {}).get("renderer", {})
    for group in renderer.get("uniqueValueGroups", []):
        for c in group.get("classes", []):
            for values in c.get("values", []):
                labels[int(values[0])] = c["label"]
    for c in renderer.get("uniqueValueInfos", []):
        if str(c.get("value", "")).lstrip("-").isdigit():
            labels[int(c["value"])] = c["label"]
    points["gazetteer_subtype_label"] = points.SUBTYP.map(labels)
    points["is_editor_auxiliary_record"] = points.SUBTYP.eq(99).astype(int)
    # Full current public gazetteer is useful for reference, including records
    # outside district coverage; never silently force them into a district.
    gpkg = out / "settlements.gpkg"
    if gpkg.exists():
        gpkg.unlink()
    points.to_file(gpkg, layer="cz_retro_localities_reference", driver="GPKG")
    write_gzip_csv_atomic(points.drop(columns="geometry"), out / "cz_retro_localities_reference.csv.gz")
    pd.DataFrame([{"subtype": k, "label": v} for k, v in sorted(labels.items())]).to_csv(out / "cz_retro_subtype_dictionary.csv", index=False)

    links_all, summaries, ambiguous_all, outside_all = [], [], [], []
    pp = points.to_crs(3035)
    for layer, expected in LAYERS.items():
        districts = gpd.read_file(base, layer=layer)
        if len(districts) != expected or not districts.district_year_id.is_unique:
            raise ValueError(f"Unexpected district count or duplicate IDs: {layer}")
        dd = districts[["district_year_id", "NAZEV", "boundary_year", "geometry"]].to_crs(3035)
        # Intersects includes points exactly on a polygon boundary. Multiple
        # candidates are retained and marked, then excluded from primary counts.
        matches = gpd.sjoin(pp[["gazetteer_record_id", "gazetteer_locality_id", "KOD_CZ", "LOKALITA", "SUBTYP", "is_editor_auxiliary_record", "geometry"]], dd, how="left", predicate="intersects")
        matches["geography"] = layer
        candidate_count = matches.groupby("gazetteer_record_id")["district_year_id"].transform("count")
        matches["district_candidate_count"] = candidate_count
        matches["assignment_status"] = np.select([candidate_count.eq(0), candidate_count.eq(1)], ["outside_available_district_coverage", "unique_point_overlay"], default="multiple_district_candidates")
        matched = matches.loc[matches.district_year_id.notna()].copy()
        matched["link_method"] = "point_intersects_historical_district_polygon"
        matched["temporal_status"] = "location_reference_only_no_historical_activity_year"
        matched["gazetteer_snapshot_date"] = "2026-11-03"
        keep = ["geography", "district_year_id", "boundary_year", "gazetteer_record_id", "gazetteer_locality_id", "KOD_CZ", "LOKALITA", "SUBTYP", "district_candidate_count", "assignment_status", "link_method", "temporal_status", "gazetteer_snapshot_date"]
        link = pd.DataFrame(matched[keep])
        links_all.append(link)
        write_gzip_csv_atomic(link, out / f"gazetteer_district_links_{layer}.csv.gz")
        ambiguous_all.append(pd.DataFrame(matches.loc[candidate_count.gt(1)].drop(columns="geometry")))
        outside_all.append(pd.DataFrame(matches.loc[candidate_count.eq(0)].drop(columns="geometry")))
        primary = matched.loc[matched.district_candidate_count.eq(1) & matched.is_editor_auxiliary_record.eq(0)]
        counts = primary.groupby("district_year_id").agg(gazetteer_reference_record_count=("gazetteer_record_id", "nunique"), gazetteer_reference_locality_code_count=("KOD_CZ", "nunique"))
        summary = pd.DataFrame({"geography": layer, "district_year_id": districts.district_year_id, "boundary_year": districts.boundary_year}).merge(counts, on="district_year_id", how="left", validate="one_to_one")
        for c in ("gazetteer_reference_record_count", "gazetteer_reference_locality_code_count"):
            summary[c] = summary[c].fillna(0).astype(int)
        summary["gazetteer_snapshot_date"] = "2026-11-03"
        summary["gazetteer_temporal_status"] = "multitemporal_reference_not_1930_settlement_count"
        summaries.append(summary)
        summary.to_csv(out / f"gis_gazetteer_reference_{layer}.csv", index=False)
        # Every accepted non-auxiliary record is counted exactly once per layer.
        if summary.gazetteer_reference_record_count.sum() != len(primary):
            raise ValueError("Gazetteer district count conservation failed")
        tests.extend([
            {"test": f"{layer}_all_districts_retained", "status": "PASS", "detail": str(len(summary))},
            {"test": f"{layer}_unique_record_overlay_conservation", "status": "PASS", "detail": f"accepted_records={len(primary)}; ambiguous_records={matches.loc[candidate_count.gt(1),'gazetteer_record_id'].nunique()}; outside_records={matches.loc[candidate_count.eq(0),'gazetteer_record_id'].nunique()}"},
        ])
    links = pd.concat(links_all, ignore_index=True)
    summary_all = pd.concat(summaries, ignore_index=True)
    ambiguous = pd.concat(ambiguous_all, ignore_index=True)
    outside = pd.concat(outside_all, ignore_index=True)
    write_gzip_csv_atomic(links, out / "gazetteer_district_links.csv.gz")
    summary_all.to_csv(out / "gis_gazetteer_reference.csv", index=False)
    ambiguous.to_csv(audit / "settlements_ambiguous_district_links.csv", index=False)
    write_gzip_csv_atomic(outside, audit / "settlements_outside_district_coverage.csv.gz")
    if links.duplicated(["geography", "district_year_id", "gazetteer_record_id"]).any():
        raise ValueError("Duplicate gazetteer link key")
    with sqlite3.connect(gpkg) as conn:
        links.to_sql("gazetteer_district_links", conn, index=False, if_exists="replace")
        summary_all.to_sql("gis_gazetteer_reference", conn, index=False, if_exists="replace")
        for table in ("gazetteer_district_links", "gis_gazetteer_reference"):
            conn.execute("INSERT OR REPLACE INTO gpkg_contents (table_name,data_type,identifier,description,last_change) VALUES (?,?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'))", (table, "attributes", table, "CZ_RETRO reference gazetteer; NOT active settlement census at district-boundary year"))
        conn.execute("CREATE UNIQUE INDEX gazetteer_links_key ON gazetteer_district_links(geography,district_year_id,gazetteer_record_id)")
    tests.append({"test": "gazetteer_link_key_unique", "status": "PASS", "detail": str(len(links))})
    tests.append({"test": "historical_activity_year_never_invented", "status": "PASS", "detail": "All source records explicitly marked multitemporal reference; no 1930 active-locality counts."})
    pd.DataFrame(tests).to_csv(audit / "settlements_validation.csv", index=False)

    definitions = {
        "geography": ("code", "Historical district geography used for spatial overlay."),
        "district_year_id": ("code", "Stable historical district ID; the place is linked by location, not asserted to exist at boundary_year."),
        "boundary_year": ("year", "Year of historical district polygons, not the activity year of a gazetteer place."),
        "gazetteer_record_id": ("code", "Snapshot-specific record identifier derived from provider OBJECTID."),
        "gazetteer_locality_id": ("code", "CZ_RETRO stable locality code KOD_CZ with dataset prefix; more than one source record may share a code."),
        "KOD_CZ": ("code", "Provider's CZ_RETRO locality identifier, preserved unchanged."),
        "LOKALITA": ("text", "Provider's locality name, preserved unchanged."),
        "SUBTYP": ("code", "Provider's locality subtype; labels are in cz_retro_subtype_dictionary.csv."),
        "district_candidate_count": ("count", "Number of intersecting historical district polygons for this point in this geography."),
        "assignment_status": ("text", "Unique point overlay or multiple district candidates; only unique non-auxiliary records enter district reference counts."),
        "link_method": ("text", "Point/polygon intersection using EPSG:3035; no population allocation."),
        "temporal_status": ("text", "Reference location only; no inferred historical existence year."),
        "gazetteer_snapshot_date": ("ISO date", "Date the live gazetteer was acquired; not an observation year for historical settlement activity."),
        "gazetteer_reference_record_count": ("count", "Number of current downloaded multitemporal gazetteer records uniquely located in district, excluding auxiliary subtype99; NOT number of settlements in 1921/1930."),
        "gazetteer_reference_locality_code_count": ("count", "Number of distinct KOD_CZ values among accepted reference records; NOT historical settlement population/count."),
        "gazetteer_temporal_status": ("text", "Explicit warning that the reference gazetteer mixes different periods of settlement existence."),
    }
    dictionary = []
    for table, df in [("gazetteer_district_links", links), ("gis_gazetteer_reference", summary_all)]:
        for col in df.columns:
            unit, definition = definitions[col]
            dictionary.append({"table": table, "variable": col, "unit": unit, "definition": definition, "source": "CZ_RETRO / SOVAMM, public NPÚ service", "license": "Service states CC-BY-SA 4.0 SOVAMM; author page states CC BY-NC-SA 4.0; redistribution clarification required"})
    for col in points.columns:
        if col == "geometry":
            unit, definition = "Point EPSG:4326", "Actual provider point returned by public ArcGIS query outSR4326."
        elif col in definitions:
            unit, definition = definitions[col]
        elif col.endswith("_utc"):
            unit, definition = "UTC date/time", "ISO conversion of the provider's administrative metadata timestamp; NOT place foundation or destruction date."
        elif col == "historical_activity_year":
            unit, definition = "year, missing", "Not supplied: the source does not establish active existence at each historical census year."
        elif col == "gazetteer_subtype_label":
            unit, definition = "text", "Subtype label from the provider layer renderer, preserved for interpretation."
        elif col == "is_editor_auxiliary_record":
            unit, definition = "0/1", "Provider subtype99 denotes an auxiliary editing record; excluded from district reference counts."
        else:
            unit, definition = "source attribute", "Original provider field preserved without reinterpretation; consult archived layer metadata. Administrative metadata dates must not be used as settlement existence dates."
        dictionary.append({"table": "cz_retro_localities_reference", "variable": col, "unit": unit, "definition": definition, "source": "CZ_RETRO / SOVAMM, public NPÚ service", "license": "See module manifest for source license statements"})
    pd.DataFrame(dictionary).to_csv(out / "dictionary.csv", index=False)

    manifest = {"module": "settlements", "status": "completed_reference_gazetteer_and_district_links", "built_utc": datetime.now(timezone.utc).isoformat(), "acquisition": acquisition, "sources": sources, "source_author": "Karel Kuča / SOVAMM; publication via NPÚ public map service", "source_license_statements": {"live_service": acquisition["source_service_copyright"], "author_page": "CC BY-NC-SA 4.0", "older_NPU_catalogue_previously_reported": "CC BY-NC-ND 4.0"}, "redistribution_status": "private_research_integration; resolve conflicting terms before public redistribution", "tables": {"gazetteer_district_links": "modules/settlements/gazetteer_district_links.csv.gz", "gis_gazetteer_reference": "modules/settlements/gis_gazetteer_reference.csv"}, "spatial_file": "modules/settlements/settlements.gpkg", "spatial_layers": ["cz_retro_localities_reference"], "static_by_geography": {layer: f"modules/settlements/gis_gazetteer_reference_{layer}.csv" for layer in LAYERS}, "row_counts": {"source_records": len(raw), "usable_point_records": len(points), "geometry_exclusions": len(excluded), "records_with_repeated_locality_code": len(duplicate_codes), "district_links": len(links), "district_summaries": len(summary_all)}, "validation": {"pass": len(tests), "fail": 0, "file": "audit/settlements_validation.csv"}, "limitations": ["Gazetteer combines existing, extinct, ancient and subsidiary localities; counts are reference-record counts, not settlement counts in 1930.", "Administrative validity/update timestamps are not foundation/destruction dates.", "Multiple district matches are retained and flagged, excluded from primary counts; no forced allocation.", "Political1921 district footprint is known to be incomplete.", "Protected FeatureServer endpoint was not used; the independently public MapServer query service was used."]}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (docs / "SETTLEMENTS_METHODS_CZ.md").write_text("""# CZ_RETRO: referenční sídelní databáze a propojení s okresy\n\nZ veřejné mapové služby NPÚ byla skutečně načtena bodová vrstva Lokalita. Identifikátory byly nejprve zafixovány úplným seznamem OBJECTID; každá stránka GeoJSON je kontrolována proti tomuto seznamu, aby nedošlo k tichému zkrácení výběru. Zdrojové stránky, atributy, metadata a jejich SHA256 jsou archivovány.\n\n## Co bylo připojeno\n\nBody CZ_RETRO se skutečnými místními názvy, původními alternativními názvy a zdrojovým typem lokality. Pro všechny čtyři historické správní vrstvy jsou vytvořeny vazby bod–okres. Jednoznačné průniky jsou odlišeny od bodů s více kandidáty či mimo dostupné polygony. Pomocné editační záznamy typu99 jsou zachovány ve zdroji, ale nezahrnují se do souhrnných počtů.\n\n## Co tyto údaje NEZNAMENAJÍ\n\nDatabáze zahrnuje sídla různých období včetně zaniklých a dávno zaniklých lokalit, místních částí a městských čtvrtí. Počet referenčních záznamů v okresu není počet obcí nebo sídel existujících v roce1930. Rok hranic okresu není rok existence sídla. Zdrojová pole Platn_od, platn_do a aktualizační data jsou metadata platnosti záznamů, nikoli datum založení nebo zániku osady. Pole historical_activity_year je proto záměrně prázdné.\n\n## Licence\n\nAktuální služba uvádí CC-BY-SA4.0 SOVAMM. Autorská stránka SOVAMM uvádí CC BY-NC-SA4.0; ve starších metadatech NPÚ byl nalezen také údaj BY-NC-ND. Přesná znění jsou zachována v manifestu. Jde o soukromé výzkumné propojení; před veřejným přebalením je třeba vyjasnit podmínky s poskytovatelem.\n\nhttps://sovamm.wordpress.com/projekty/aktualni-projekty-sovamm/cz_retro/\n\n## Reprodukce\n\n`python scripts/build_settlements.py --base /cesta/k/historical_gis_czech_lands_v05.gpkg`\n\nVeřejné čtecí dotazy používají službu CP_CZ_Retro_LS/MapServer/1; nebyl obcházen tokenem chráněný FeatureServer.\n""", encoding="utf-8")
    print(json.dumps({"module": "settlements", "rows": manifest["row_counts"], "validation": manifest["validation"]}, ensure_ascii=False), flush=True)
    return manifest


def build_population() -> dict:
    src = ROOT / "sources/population"
    out = ROOT / "modules/population"
    audit = ROOT / "audit"
    docs = ROOT / "docs"
    for p in (src, out, audit, docs):
        p.mkdir(parents=True, exist_ok=True)
    sources = [download(CSU_ZIP, src / "170240-17data.zip"), download(CSU_SCHEMA, src / "170240-17schema.json"), download(CSU_DOC, src / "170240-17dds.pdf"), download(CSU_PAGE, src / "csu_landing.html")]
    with zipfile.ZipFile(src / "170240-17data.zip") as z:
        names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if len(names) != 1:
            raise ValueError("Expected a single CSO population CSV")
        with z.open(names[0]) as f:
            original = pd.read_csv(f, encoding="utf-8-sig", dtype=str)
    data = original.copy()
    data["rok"] = pd.to_numeric(data.rok, errors="raise").astype(int)
    data["hodnota"] = pd.to_numeric(data.hodnota, errors="raise")
    data["municipality_boundary_year"] = 2015
    data["district_crosswalk_status"] = "not_applied_historical_boundary_crosswalk_required"
    data["source_dataset"] = "CSU_170240-17"
    if data.duplicated(["vuzemi_cis", "vuzemi_kod", "rok", "stapro_kod"]).any():
        raise ValueError("Duplicate CSO municipality/indicator/year key")
    if (data.hodnota < 0).any():
        raise ValueError("Negative CSO population or house values")
    hist = data.loc[data.rok.le(1930)].copy()
    write_gzip_csv_atomic(hist, out / "csu_population_houses_1869_1930_municipalities2015.csv.gz")
    write_gzip_csv_atomic(data, out / "csu_population_houses_1869_2011_municipalities2015.csv.gz")
    years = sorted(data.rok.unique().tolist())
    completeness_key = ["vuzemi_kod", "stapro_kod", "rok"]
    expected_keys = pd.MultiIndex.from_product([sorted(data.vuzemi_kod.unique()), sorted(data.stapro_kod.unique()), years], names=completeness_key)
    absent = expected_keys.difference(pd.MultiIndex.from_frame(data[completeness_key])).to_frame(index=False)
    absent = absent.merge(data[["vuzemi_kod", "vuzemi_txt"]].drop_duplicates(), on="vuzemi_kod", how="left")
    absent.to_csv(audit / "population_absent_municipality_indicator_year_rows.csv", index=False)
    if (absent.rok <= 1930).any():
        raise ValueError("Unexpected absent municipality/indicator/year records in historic population subset")
    counts = hist.groupby(["rok", "stapro_kod", "stapro_txt"]).agg(n_municipalities=("vuzemi_kod", "nunique"), total=("hodnota", "sum")).reset_index()
    counts.to_csv(audit / "population_source_summary.csv", index=False)
    tests = [
        {"test": "source_zip_read_and_schema_present", "status": "PASS", "detail": str(len(data))},
        {"test": "municipality_indicator_year_key_unique", "status": "PASS", "detail": "vuzemi_cis,vuzemi_kod,rok,stapro_kod"},
        {"test": "all_counts_nonnegative", "status": "PASS", "detail": "No negative values"},
        {"test": "historic_subset_years", "status": "PASS", "detail": json.dumps(sorted(hist.rok.unique().tolist()))},
        {"test": "historic_subset_complete_municipality_indicator_year_grid", "status": "PASS", "detail": f"All 6253 municipalities × 7 years × 2 indicators through 1930 present; later absent records={len(absent)} and explicitly archived"},
        {"test": "no_unjustified_historical_district_assignment", "status": "PASS", "detail": "No district_year_id added; original municipality geography2015 retained"},
    ]
    pd.DataFrame(tests).to_csv(audit / "population_validation.csv", index=False)
    dictionary = []
    schema = json.loads((src / "170240-17schema.json").read_text(encoding="utf-8-sig"))
    for col in hist.columns:
        if col == "municipality_boundary_year": unit, definition = "year", "All published historical counts are harmonized to municipality structure2015, per CSO metadata."
        elif col == "district_crosswalk_status": unit, definition = "text", "No allocation to historical districts has been performed; a validated historical municipality crosswalk is still required."
        elif col == "source_dataset": unit, definition = "code", "Official CSO product170240-17."
        elif col == "rok": unit, definition = "year", "Historical census observation year, distinct from municipal boundary year2015."
        elif col == "hodnota": unit, definition = "persons or houses per stapro_kod", "Original published count; not allocated to historical districts."
        else: unit, definition = "source attribute", "Original official CSO field; see archived170240-17schema.json and170240-17dds.pdf."
        dictionary.append({"table": "csu_population_houses_reference", "variable": col, "unit": unit, "definition": definition, "source": "Czech Statistical Office,170240-17", "license": "CSO open data, source attribution retained"})
    pd.DataFrame(dictionary).to_csv(out / "dictionary.csv", index=False)
    manifest = {"module": "population", "status": "source_acquired_historical_crosswalk_pending", "built_utc": datetime.now(timezone.utc).isoformat(), "sources": sources, "source_landing_page": CSU_PAGE, "source_dataset": "170240-17", "source_municipality_boundary_year": 2015, "source_observation_years": years, "row_counts": {"all_1869_2011": len(data), "historic_1869_1930": len(hist)}, "indicator_codes": data[["stapro_kod", "stapro_txt"]].drop_duplicates().to_dict("records"), "municipality_count": int(data.vuzemi_kod.nunique()), "reference_tables": {"historic": "modules/population/csu_population_houses_1869_1930_municipalities2015.csv.gz", "all": "modules/population/csu_population_houses_1869_2011_municipalities2015.csv.gz"}, "static_by_geography": {}, "integration_status": "NO_DISTRICT_AGGREGATES_CREATED", "validation": {"pass": len(tests), "fail": 0, "file": "audit/population_validation.csv"}, "limitations": ["Source populations and houses are harmonized to municipal boundaries2015.", "No historical district urbanization or population totals are generated without a validated crosswalk.", "A municipality point or gazetteer name alone does not justify assigning its entire historical population to one1930district."]}
    manifest["absent_source_records"] = absent.to_dict("records")
    manifest["absent_source_records_audit"] = "audit/population_absent_municipality_indicator_year_rows.csv"
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (docs / "POPULATION_REFERENCE_CZ.md").write_text("""# ČSÚ 170240-17: skutečně získaná historická populační data\n\nOficiální ZIP, schéma a dokumentace byly staženy a otevřeny. Archiv obsahuje počty obyvatel a domů za sčítací roky 1869–2011. Pro projekt je připraven nezměněný historický výřez do 1930.\n\n**Všechny tyto historické počty jsou podle poskytovatele převedeny na územní strukturu obcí 2015.** Proto jsou data přiložena jako referenční tabulka v této geografii a nebyla bez podkladů připojena k soudním okresům 1930. Pro správné připojení potřebujeme historicky doložený převodník obcí a částí obcí; prostá poloha dnešního obecního bodu nebo shoda jména nezaručuje správný převod.\n\nVýřez 1869–1930 obsahuje úplných 87 542 záznamů: 6 253 obcí × 7 sčítání × 2 ukazatele. Úplný zdroj 1869–2011 má 175 081 řádků; proti pravoúhlému panelu chybějí tři populační údaje roku 2011 (Libavá, Brdy, Hradiště). Chybějící záznamy jsou vypsány v auditu a nebyly doplněny nulami.\n\nŽádné nové okresní populační hodnoty ani urbanizační podíly z tohoto zdroje nejsou v této verzi vydávány za hotové. Původní censusová data okresů zůstávají zachována.\n\nZdroj: Český statistický úřad, Obyvatelstvo a domy v obcích podle výsledků sčítání 1869–2011, produkt 170240-17. https://csu.gov.cz/obyvatelstvo-a-domy-v-obcich-podle-vysledku-scitani-od-roku-1869\n""", encoding="utf-8")
    print(json.dumps({"module": "population", "status": manifest["status"], "rows": manifest["row_counts"]}, ensure_ascii=False), flush=True)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--stage", choices=["all", "gazetteer", "population"], default="all")
    args = parser.parse_args()
    if args.stage in ("all", "gazetteer"):
        build_gazetteer(args.base)
    if args.stage in ("all", "population"):
        build_population()
