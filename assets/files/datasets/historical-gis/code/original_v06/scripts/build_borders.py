#!/usr/bin/env python3
"""Attach documented CShapes state-boundary distances to historical districts.

This is a model-based distance module, not a cadastral reconstruction of annexation.
The original historical districts and all pre-existing values are read only.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Geod
import requests
import shapely


ROOT = Path(__file__).resolve().parents[1]
PACKAGED_BASE = ROOT / "inputs/base_v05_inputs.gpkg"
LEGACY_BASE = ROOT.parent / "gis_work/GIS_v04_Preparation/outputs/wave2_completed/historical_gis_czech_lands_v05.gpkg"
DEFAULT_BASE = PACKAGED_BASE if PACKAGED_BASE.exists() else LEGACY_BASE
SOURCE_URL = "https://icr.ethz.ch/data/cshapes/CShapes-2.0.geojson"
LANDING_URL = "https://icr.ethz.ch/data/cshapes/"
LAYERS = {"judicial_1930": 330, "judicial_1921": 328, "political_1930": 151, "political_1921": 151}
SNAPSHOTS = {
    "1921": "1921-01-01",
    "1930": "1930-01-01",
    "1938_pre": "1938-09-29",
    "1938_oct": "1938-10-01",
    "1938_end": "1938-12-31",
}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def fetch(url: str, path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        r = requests.get(url, timeout=(20, 120))
        r.raise_for_status()
        tmp = path.with_suffix(path.suffix + ".part")
        tmp.write_bytes(r.content)
        tmp.replace(path)
    return {"url": url, "file": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": digest(path)}


def run(base: Path) -> None:
    source_dir = ROOT / "sources/borders"
    out = ROOT / "modules/borders"
    audit = ROOT / "audit"
    docs = ROOT / "docs"
    for p in (source_dir, out, audit, docs):
        p.mkdir(parents=True, exist_ok=True)
    src = source_dir / "CShapes-2.0.geojson"
    source = fetch(SOURCE_URL, src)
    original = gpd.read_file(src)
    original["source_row_number"] = np.arange(len(original), dtype=int)
    country = original.loc[original.cntry_name.eq("Czechoslovakia")].copy()
    assert len(country) > 0 and country.crs.to_epsg() == 4326
    # Do not parse the provider's locale-dependent timestamp strings: they are
    # displayed one hour before midnight. Its explicit Y/M/D fields are canonical.
    country["valid_from"] = pd.to_datetime(dict(year=country.gwsyear, month=country.gwsmonth, day=country.gwsday))
    country["valid_to"] = pd.to_datetime(dict(year=country.gweyear, month=country.gwemonth, day=country.gweday))
    used = []
    snapshot_rows = []
    for name, day in SNAPSHOTS.items():
        date = pd.Timestamp(day)
        chosen = country.loc[country.valid_from.le(date) & country.valid_to.ge(date)]
        if len(chosen) != 1:
            raise ValueError(f"Exactly one Czechoslovakia geometry required for {day}; got {len(chosen)}")
        row = chosen.iloc[0]
        used.append(int(row.source_row_number))
        snapshot_rows.append({"snapshot_id": name, "reference_date": day, "source_period_id": int(row.source_row_number), "source_start_date": row.valid_from.strftime("%Y-%m-%d"), "source_end_date": row.valid_to.strftime("%Y-%m-%d"), "country_name": row.cntry_name, "source_country_code": int(row.gwcode)})
    periods = country.loc[country.source_row_number.isin(used)].copy()
    if periods.geometry.isna().any() or periods.is_empty.any() or not periods.is_valid.all():
        raise ValueError("CShapes Czechoslovakia source geometry invalid; manual investigation required")
    projected = periods.to_crs(3035).set_index("source_row_number")
    snapshots = pd.DataFrame(snapshot_rows)
    snapshots.to_csv(out / "border_snapshots.csv", index=False)

    gpkg = out / "borders.gpkg"
    if gpkg.exists():
        gpkg.unlink()
    export_periods = periods.copy()
    export_periods["valid_from"] = export_periods.valid_from.dt.strftime("%Y-%m-%d")
    export_periods["valid_to"] = export_periods.valid_to.dt.strftime("%Y-%m-%d")
    export_periods["source_dataset"] = "CShapes 2.0"
    export_periods["source_url"] = SOURCE_URL
    export_periods["license"] = "CC BY-NC-SA 4.0"
    export_periods.to_file(gpkg, layer="cshapes_czechoslovakia_periods", driver="GPKG")
    border_lines = export_periods.copy()
    border_lines.geometry = export_periods.geometry.boundary
    border_lines.to_file(gpkg, layer="cshapes_czechoslovakia_borders", driver="GPKG")

    rows, static_rows, tests, spatial_qa = [], [], [], []
    tests.append({"test": "source_czechoslovakia_geometries_valid", "status": "PASS", "detail": f"{len(periods)} selected country periods"})
    tests.append({"test": "snapshot_dates_select_unique_country_period", "status": "PASS", "detail": json.dumps(SNAPSHOTS)})
    geod = Geod(ellps="WGS84")
    for layer, expected in LAYERS.items():
        d = gpd.read_file(base, layer=layer)
        if len(d) != expected or not d.district_year_id.is_unique:
            raise ValueError(f"Bad district count or IDs for {layer}")
        if not d.is_valid.all():
            raise ValueError(f"Invalid district polygons in {layer}")
        centroid = gpd.GeoSeries(gpd.points_from_xy(d.centroid_lon, d.centroid_lat), crs=4326).to_crs(3035)
        interior = gpd.GeoSeries(gpd.points_from_xy(d.interior_point_lon, d.interior_point_lat), crs=4326).to_crs(3035)
        district = d.to_crs(3035)
        if not np.all(shapely.covers(district.geometry.array, interior.array)):
            raise ValueError(f"Stored interior point outside district: {layer}")
        static = pd.DataFrame({"geography": layer, "district_year_id": d.district_year_id, "boundary_year": d.boundary_year})
        for spec in snapshot_rows:
            polygon = projected.loc[spec["source_period_id"]].geometry
            boundary = polygon.boundary
            dist_c = shapely.distance(centroid.array, boundary) / 1000
            dist_i = shapely.distance(interior.array, boundary) / 1000
            inside_c = shapely.covers(polygon, centroid.array)
            inside_i = shapely.covers(polygon, interior.array)
            if not (np.isfinite(dist_c).all() and np.isfinite(dist_i).all() and (dist_c >= 0).all() and (dist_i >= 0).all()):
                raise ValueError("Nonfinite/negative boundary distance")
            item = pd.DataFrame({"geography": layer, "district_year_id": d.district_year_id, "boundary_year": d.boundary_year, **{k: v for k, v in spec.items()}, "calendar_year": int(spec["reference_date"][:4]), "dist_centroid_czechoslovakia_border_km": dist_c, "dist_interior_point_czechoslovakia_border_km": dist_i, "centroid_inside_czechoslovakia_model": inside_c.astype(int), "interior_point_inside_czechoslovakia_model": inside_i.astype(int), "source_quality_flag": "generalized_state_boundary_not_local_delimitation"})
            rows.append(item)
            # Main ready-to-join table uses explicit observation/snapshot suffixes.
            suffix = spec["snapshot_id"]
            static[f"border_dist_centroid_km_{suffix}"] = dist_c
            static[f"border_dist_interior_km_{suffix}"] = dist_i
            static[f"border_centroid_inside_country_{suffix}"] = inside_c.astype(int)
            static[f"border_interior_inside_country_{suffix}"] = inside_i.astype(int)
            # Independent check: geodesic distance to the computed nearest point.
            lines = shapely.shortest_line(centroid.array, boundary)
            endpoint = shapely.get_point(lines, -1)
            endpoint_ll = gpd.GeoSeries(endpoint, crs=3035).to_crs(4326)
            geodesic_m = np.abs(geod.inv(d.centroid_lon.to_numpy(), d.centroid_lat.to_numpy(), endpoint_ll.x.to_numpy(), endpoint_ll.y.to_numpy())[2])
            relative = np.abs(geodesic_m / 1000 - dist_c) / np.maximum(dist_c, 0.001)
            if (relative > 0.015).any():
                raise ValueError("Unexpectedly large LAEA versus geodesic boundary-distance difference")
            tests.append({"test": f"{layer}_{suffix}_geodesic_distance_consistency", "status": "PASS", "detail": f"max_relative_difference={relative.max():.8f}; tolerance=0.015"})
            tests.append({"test": f"{layer}_{suffix}_complete_finite_distances", "status": "PASS", "detail": f"{len(d)} districts; inside_centroid={inside_c.sum()}; inside_interior={inside_i.sum()}"})
            if suffix == "1930":
                footprint = shapely.union_all(district.geometry)
                inside_area = shapely.intersection(footprint, polygon).area
                spatial_qa.append({"geography": layer, "district_footprint_area_km2": footprint.area / 1e6, "footprint_inside_cshapes_country_fraction": inside_area / footprint.area, "centroids_outside_model_count": int((~inside_c).sum()), "interior_points_outside_model_count": int((~inside_i).sum()), "note": "QA only; geometry disagreement is not evidence of historical foreign territory."})
        static["border_geometry_quality"] = "CShapes_generalized_state_geometry"
        static_rows.append(static)
        static.to_csv(out / f"gis_borders_static_{layer}.csv", index=False, float_format="%.10g")
        tests.append({"test": f"{layer}_all_districts_preserved", "status": "PASS", "detail": str(expected)})

    panel = pd.concat(rows, ignore_index=True)
    joined = pd.concat(static_rows, ignore_index=True)
    if panel.duplicated(["geography", "district_year_id", "snapshot_id"]).any():
        raise ValueError("Duplicate boundary panel key")
    panel.to_csv(out / "gis_borders.csv", index=False, float_format="%.10g")
    joined.to_csv(out / "gis_borders_static.csv", index=False, float_format="%.10g")
    with sqlite3.connect(gpkg) as conn:
        panel.to_sql("gis_borders", conn, index=False, if_exists="replace")
        joined.to_sql("gis_borders_static", conn, index=False, if_exists="replace")
        snapshots.to_sql("border_snapshots", conn, index=False, if_exists="replace")
        for table in ("gis_borders", "gis_borders_static", "border_snapshots"):
            conn.execute("INSERT OR REPLACE INTO gpkg_contents (table_name,data_type,identifier,description,last_change) VALUES (?,?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'))", (table, "attributes", table, "CShapes 2.0 derived state-boundary distances / documented temporal snapshots"))
        conn.execute("CREATE UNIQUE INDEX borders_key ON gis_borders(geography,district_year_id,snapshot_id)")
    tests.append({"test": "combined_panel_unique_key", "status": "PASS", "detail": str(len(panel))})
    pd.DataFrame(tests).to_csv(audit / "borders_validation.csv", index=False)
    pd.DataFrame(spatial_qa).to_csv(audit / "borders_geometry_disagreement.csv", index=False)

    defs = {
        "geography": ("code", "Historical district layer; alternative geographies are not independent observations."),
        "district_year_id": ("code", "Stable historical district identifier from the unchanged v0.5 base."),
        "boundary_year": ("year", "Year of district boundaries, distinct from the state-boundary reference date."),
        "snapshot_id": ("code", "Named state-boundary snapshot; use border_snapshots.csv for exact dates."),
        "reference_date": ("ISO date", "Requested date of the source state-boundary snapshot; the source is a generalized de jure model."),
        "calendar_year": ("year", "Calendar year of reference_date, not the district-boundary year."),
        "country_name": ("text", "Czechoslovakia; the full state includes Slovakia and Subcarpathian Ruthenia in the source where applicable."),
        "source_country_code": ("code", "Gleditsch-Ward country code used by CShapes; 315 denotes Czechoslovakia."),
        "source_period_id": ("integer", "Zero-based source-row index in the archived official CShapes 2.0 GeoJSON."),
        "source_start_date": ("ISO date", "Inclusive source validity start reconstructed from explicit gwsyear/gwsmonth/gwsday."),
        "source_end_date": ("ISO date", "Inclusive source validity end reconstructed from explicit gweyear/gwemonth/gweday."),
        "dist_centroid_czechoslovakia_border_km": ("km", "Shortest planar EPSG:3035 distance from stored district centroid to full Czechoslovakia boundary. After annexation this remains distance to Czechoslovakia, even for points outside that state."),
        "dist_interior_point_czechoslovakia_border_km": ("km", "Shortest planar EPSG:3035 distance from stored in-district reference point to full Czechoslovakia boundary. It is not distance from the district seat or a population-weighted center."),
        "centroid_inside_czechoslovakia_model": ("0/1", "Whether the stored centroid is covered by generalized CShapes Czechoslovakia geometry; not an authoritative historical territorial assignment."),
        "interior_point_inside_czechoslovakia_model": ("0/1", "Whether the stored interior reference point is covered by generalized CShapes Czechoslovakia geometry; not an authoritative historical territorial assignment."),
        "source_quality_flag": ("text", "Explicit warning that CShapes state boundaries are generalized and cannot resolve precise local demarcation."),
    }
    dictionary = [{"table": "gis_borders", "variable": key, "unit": value[0], "definition": value[1], "source": "CShapes 2.0", "license": "CC BY-NC-SA 4.0"} for key, value in defs.items()]
    for col in joined.columns:
        if col in defs:
            unit, definition = defs[col]
        elif col == "border_geometry_quality":
            unit, definition = "text", "Source-resolution qualifier; generalized state geometry, not local cadastral demarcation."
        else:
            snapshot = next(s for s in sorted(SNAPSHOTS, key=len, reverse=True) if col.endswith("_" + s))
            date = SNAPSHOTS[snapshot]
            if col.startswith("border_dist_centroid"):
                unit, definition = "km", f"Shortest centroid-to-Czechoslovakia-model-boundary distance, EPSG:3035, snapshot {date}; straight-line distance, not travel distance."
            elif col.startswith("border_dist_interior"):
                unit, definition = "km", f"Shortest in-district-reference-point-to-Czechoslovakia-model-boundary distance, EPSG:3035, snapshot {date}; reference point is not the district seat."
            elif col.startswith("border_centroid_inside"):
                unit, definition = "0/1", f"Centroid covered by generalized source country polygon at {date}; model classification, not historical local verification."
            else:
                unit, definition = "0/1", f"Interior reference point covered by generalized source country polygon at {date}; model classification, not historical local verification."
        dictionary.append({"table": "gis_borders_static", "variable": col, "unit": unit, "definition": definition, "source": "CShapes 2.0", "license": "CC BY-NC-SA 4.0"})
    pd.DataFrame(dictionary).to_csv(out / "dictionary.csv", index=False)
    manifest = {
        "module": "borders", "status": "completed_model_based_distances", "built_utc": datetime.now(timezone.utc).isoformat(),
        "source": source, "source_landing_page": LANDING_URL, "source_license": "CC BY-NC-SA 4.0", "source_version": "CShapes 2.0 official downloadable GeoJSON, accessed 2026-11-03",
        "source_citation": "Schvitz et al. (2022), Mapping The International System, 1886-2017: The CShapes 2.0 Dataset, Journal of Conflict Resolution 66(1):144-161.",
        "base_file": str(base), "base_sha256": digest(base), "district_crs": "EPSG:4326", "distance_crs": "EPSG:3035", "snapshots": snapshot_rows,
        "tables": {"gis_borders": "modules/borders/gis_borders.csv", "gis_borders_static": "modules/borders/gis_borders_static.csv", "border_snapshots": "modules/borders/border_snapshots.csv"},
        "spatial_file": "modules/borders/borders.gpkg", "spatial_layers": ["cshapes_czechoslovakia_periods", "cshapes_czechoslovakia_borders"],
        "static_by_geography": {layer: f"modules/borders/gis_borders_static_{layer}.csv" for layer in LAYERS},
        "row_counts": {"gis_borders": len(panel), "gis_borders_static": len(joined), "source_country_periods": len(periods)},
        "validation": {"pass": len(tests), "fail": 0, "file": "audit/borders_validation.csv"}, "qa_geometry_disagreement": spatial_qa,
        "limitations": ["Country boundaries are generalized. Source circa-1930 territory does not exactly coincide with historical district geometry.", "No annexed district-area or population share is asserted.", "State validity dates describe the source's de jure coding, not the day each local border segment was physically occupied or demarcated.", "CShapes uses the full Czechoslovak state; the Czech-lands/Slovakia division is never treated as a foreign state boundary.", "The 1938 distances are to Czechoslovakia's remaining boundary even when the district reference point lies outside its source polygon.", "Centroids and interior points are not district seats or population centers."]
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (docs / "BORDERS_METHODS_CZ.md").write_text("""# Státní hranice: CShapes 2.0\n\nSkutečný oficiální GeoJSON byl stažen a archivován; kontrolní součet a adresa jsou v manifestu. Pro všechny čtyři správní vrstvy jsou vypočteny vzdálenosti od uloženého centroidu a vnitřního referenčního bodu k hranici **celého Československa**. Vnitřní hranice českých zemí se Slovenskem se nepoužívá jako zahraniční hranice.\n\n## Časové řezy\n\nPoužité dny: 1921-01-01, 1930-01-01, 1938-09-29, 1938-10-01, 1938-12-31. Výběr země je proveden podle explicitních celočíselných polí roku, měsíce a dne začátku a konce platnosti, včetně koncových dnů. Textová časová pole poskytovatele se nepoužívají kvůli odlišnému zobrazení časové zóny. Přesné zdrojové intervaly jsou v border_snapshots.csv.\n\n## Výpočet a jednotky\n\nJde o nejkratší geometrickou vzdálenost v EPSG:3035, vydělenou 1000 a vyjádřenou v kilometrech. Kontrola porovnává projektovanou vzdálenost s geodetickou vzdáleností na WGS84 k nejbližšímu bodu zdrojové hranice. Vzdálenosti nejsou cestovní dobou. Referenční body nejsou automaticky okresní města.\n\n## Interpretace a přesnost\n\nCShapes představuje generalizovanou rekonstrukci státních hranic a právně vymezených států. Není lokální hraniční operát a nekóduje všechny malé územní změny. Z tohoto důvodu nejsou vytvořeny proměnné vydávající podíl okresu odstoupený v roce 1938 za přesné historické pozorování. Diagnostika porovnání modelové státní geometrie s okresy je samostatně v audit/borders_geometry_disagreement.csv. Ani příznak bodu uvnitř či vně modelové hranice není místním historickým verdiktem. U roku 1938 vzdálenost stále označuje vzdálenost k hranici zbývajícího Československa, i když příslušný okresní bod leží vně tohoto státu.\n\n## Licence a citace\n\nCShapes 2.0: CC BY-NC-SA 4.0. Schvitz, G. et al. (2022), Mapping The International System, 1886–2017: The CShapes 2.0 Dataset, Journal of Conflict Resolution 66(1):144–161. https://icr.ethz.ch/data/cshapes/\n\n## Reprodukce\n\n`python scripts/build_borders.py --base /cesta/k/historical_gis_czech_lands_v05.gpkg`\n\nSkript nepřepisuje vstupní GeoPackage. Zdroj je cacheován v sources/borders; hotové tabulky a polygony jsou v modules/borders.\n""", encoding="utf-8")
    print(json.dumps({"module": "borders", "status": manifest["status"], "rows": manifest["row_counts"], "validation": manifest["validation"]}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    run(parser.parse_args().base)
