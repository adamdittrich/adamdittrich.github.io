#!/usr/bin/env python3
"""Integrate the real UPOL historical rail database with fixed district polygons.

The source ZIP is pinned by SHA256 and retained unchanged. This script never
alters the v0.5 dataset. Annual observations are reconstructed year-end states
under an explicit year-only convention; they are not dated timetable data.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import sqlite3
import urllib.request
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
import pyproj
import shapely
from shapely.geometry import GeometryCollection

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sources/rail"
OUT = ROOT / "modules/rail"
AUDIT = ROOT / "audit"
BASE = ROOT / "inputs/base_v05_inputs.gpkg"
if not BASE.exists():
    BASE = ROOT.parent / "gis_work/GIS_v04_Preparation/outputs/wave2_completed/historical_gis_czech_lands_v05.gpkg"
LAYERS = ["judicial_1930", "judicial_1921", "political_1930", "political_1921"]
YEARS = list(range(1901, 1939))
SNAPSHOTS = [1921, 1930, 1938]
CRS = 3035
SOURCE_URL = "https://dprace.geoinf.upol.cz/dprace/magisterske/bedrunka23/files/ZelezniceCR.zip"
SOURCE_PAGE = "https://dprace.geoinf.upol.cz/dprace/magisterske/bedrunka23/index.html"
SOURCE_DOC = "https://dprace.geoinf.upol.cz/dprace/magisterske/bedrunka23/files/DP_Bedrunka.pdf"
EXPECTED_SHA = "313c13451d56a65ef06f1aaf3ddcce7b0a799f6b02fce065ad67c283c03e0aca"
DATE_FIELDS = {
    "vznik": "rail_opening_year",
    "zanik": "rail_removal_year",
    "Ukonceni_provozu": "rail_closure_year",
    "elektrifikace": "rail_electric_start_year",
    "Zruseni_elektrifikace": "rail_electric_end_year",
}
CHECKS = []
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(2**20), b""):
            h.update(block)
    return h.hexdigest()


def check(name, passed, details="", severity="error"):
    CHECKS.append({"test": name, "status": "PASS" if passed else ("WARN" if severity == "warning" else "FAIL"),
                   "severity": severity, "details": str(details)})
    if not passed and severity == "error":
        pd.DataFrame(CHECKS).to_csv(AUDIT / "rail_validation.csv", index=False)
        raise AssertionError(name + ": " + str(details))


def integer_years(series):
    values = pd.to_numeric(series, errors="raise")
    if not ((values.dropna() % 1) == 0).all():
        raise ValueError("Fractional source year")
    return values.astype("Int64")


def acquire():
    SOURCE.mkdir(parents=True, exist_ok=True)
    archive = SOURCE / "ZelezniceCR.zip"
    if not archive.exists():
        req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "histCzechia-research/0.6"})
        with urllib.request.urlopen(req, timeout=60) as response:
            payload = response.read()
        archive.write_bytes(payload)
    check("source_archive_sha256", sha(archive) == EXPECTED_SHA, sha(archive))
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        check("source_archive_integrity", z.testzip() is None)
        candidates = [n for n in names if n.lower().endswith(".geojson")]
        check("one_base_geojson", candidates == ["ZelezniceCR.geojson"], candidates)
        source_json = SOURCE / "ZelezniceCR.geojson"
        source_json.write_bytes(z.read(candidates[0]))
        pd.DataFrame([{"archive_member": n, "bytes": z.getinfo(n).file_size} for n in names]).to_csv(
            SOURCE / "archive_inventory.csv", index=False)
    return source_json, archive


def source_frame(path):
    source = gpd.read_file(path)
    check("source_record_count", len(source) == 1295, len(source))
    check("source_crs", source.crs is not None and source.crs.to_epsg() == 4326, source.crs)
    check("source_id_unique", source.OBJECTID.is_unique and source.OBJECTID.notna().all())
    source["rail_source_id"] = "UPOL2023-" + source.OBJECTID.astype(str)
    for original, column in DATE_FIELDS.items():
        source[column] = integer_years(source[original])
    check("all_opening_years_known", source.rail_opening_year.notna().all())
    for original, column in DATE_FIELDS.items():
        check("integer_years_plausible_" + column,
              source[column].dropna().between(1800, 2023).all())
    end = source[["rail_removal_year", "rail_closure_year"]].min(axis=1, skipna=True)
    source["rail_operating_end_exclusive_year"] = end.astype("Int64")
    source["rail_geometry_usable"] = (source.geometry.notna() & ~source.geometry.is_empty).astype(int)
    check("usable_geometries_valid", source.loc[source.rail_geometry_usable.eq(1)].is_valid.all())
    check("usable_geometries_linear", source.loc[source.rail_geometry_usable.eq(1)].geom_type.isin(
        ["LineString", "MultiLineString"]).all())
    check("no_end_before_opening", (~source.rail_operating_end_exclusive_year.lt(source.rail_opening_year)).fillna(True).all())
    chronology = source.rail_closure_year.gt(source.rail_removal_year).fillna(False)
    source["rail_source_end_chronology_conflict"] = chronology.astype(int)
    check("source_end_chronology_consistent", not chronology.any(),
          source.loc[chronology, ["rail_source_id", "Trasa", "rail_closure_year", "rail_removal_year"]].to_dict("records"),
          severity="warning")
    check("all_source_geometries_present", source.rail_geometry_usable.eq(1).all(),
          "One original record has NULL geometry; no position or length has been invented.", severity="warning")
    check("all_closure_before_removal_conflicts_outside_analysis",
          (~chronology | source.rail_opening_year.gt(1938) | source.rail_operating_end_exclusive_year.lt(1901)
           | source.rail_operating_end_exclusive_year.gt(1938)).all())
    source.drop(columns="geometry").to_csv(SOURCE / "source_attributes.csv", index=False)
    excluded = source.loc[source.rail_geometry_usable.eq(0)].drop(columns="geometry").copy()
    excluded["exclusion_reason"] = "NULL geometry in original source; cannot spatially allocate; not imputed"
    excluded.to_csv(AUDIT / "rail_excluded_source_records.csv", index=False)
    conflicts = source.loc[chronology].drop(columns="geometry").copy()
    conflicts["handling"] = "Operating end uses minimum of closure and removal; conflict recorded and not edited upstream"
    conflicts.to_csv(AUDIT / "rail_source_chronology_conflicts.csv", index=False)
    duplicates = source[source.geometry.notna()].copy()
    duplicates["geometry_key"] = duplicates.geometry.to_wkb()
    duplicates = duplicates[duplicates.geometry_key.duplicated(keep=False)].drop(columns=["geometry", "geometry_key"])
    duplicates.to_csv(AUDIT / "rail_same_geometry_records.csv", index=False)
    return source


def active_mask(source, year):
    return (source.rail_opening_year.le(year)
            & (source.rail_operating_end_exclusive_year.isna()
               | source.rail_operating_end_exclusive_year.gt(year))).to_numpy(dtype=bool)


def electric_mask(source, year):
    return (source.rail_electric_start_year.notna()
            & source.rail_electric_start_year.le(year)
            & (source.rail_electric_end_year.isna() | source.rail_electric_end_year.gt(year))).fillna(False).to_numpy(dtype=bool)


def union_length(geometries):
    return float(shapely.length(shapely.union_all(geometries))) / 1000 if len(geometries) else 0.0


def reference_points(base, prefix):
    return gpd.GeoSeries(gpd.points_from_xy(base[prefix + "_lon"], base[prefix + "_lat"]), crs=4326).to_crs(CRS).to_numpy()


def nearest_distances(points, geometries):
    tree = shapely.STRtree(geometries)
    chosen = tree.nearest(points)
    return shapely.distance(points, np.asarray(geometries, dtype=object)[chosen]) / 1000


def build_layer(layer, source_valid, full_source, networks, footprint):
    base = gpd.read_file(BASE, layer=layer).to_crs(CRS).reset_index(drop=True)
    check(layer + "_district_ids_unique", base.district_year_id.is_unique)
    check(layer + "_district_geometries_valid", base.is_valid.all() and ~base.is_empty.any())
    expected = {"judicial_1930": 330, "judicial_1921": 328, "political_1930": 151, "political_1921": 151}[layer]
    check(layer + "_district_count", len(base) == expected, len(base))
    check(layer + "_area_denominator_matches", np.allclose(base.area / 1e6, base.area_gis_km2, rtol=1e-8, atol=1e-7))
    # Positive-length intersections only: a point touch is not a railway in a district.
    di, si = source_valid.sindex.query(base.geometry, predicate="intersects")
    intersections = shapely.intersection(base.geometry.to_numpy()[di], source_valid.geometry.to_numpy()[si])
    lengths = shapely.length(intersections) / 1000
    keep = lengths > 1e-9
    di, si, intersections, lengths = di[keep], si[keep], intersections[keep], lengths[keep]
    links = pd.DataFrame({"geography": layer, "district_year_id": base.district_year_id.to_numpy()[di],
                          "rail_source_id": source_valid.rail_source_id.to_numpy()[si],
                          "rail_clipped_source_record_length_km": lengths})
    check(layer + "_source_links_unique", ~links.duplicated(["district_year_id", "rail_source_id"]).any())
    source_meta = source_valid[["rail_source_id"] + list(DATE_FIELDS.values()) + ["rail_operating_end_exclusive_year"]]
    links = links.merge(source_meta, on="rail_source_id", validate="many_to_one")
    local = {j: np.flatnonzero(di == j) for j in range(len(base))}
    centroid = reference_points(base, "centroid")
    interior = reference_points(base, "interior_point")
    edge_c = shapely.distance(centroid, footprint.boundary) / 1000
    edge_i = shapely.distance(interior, footprint.boundary) / 1000
    inside_c = shapely.covers(footprint, centroid)
    inside_i = shapely.covers(footprint, interior)
    missing_routes = set(full_source.loc[full_source.rail_geometry_usable.eq(0), "Trasa"].dropna())
    local_missing_route = np.array([bool(source_valid.iloc[si[local[j]]].Trasa.isin(missing_routes).any())
                                    for j in range(len(base))], dtype=int)
    local_openings = np.array([source_valid.iloc[si[local[j]]].rail_opening_year.min() if len(local[j]) else np.nan
                              for j in range(len(base))], dtype=float)
    base_union = shapely.union_all(base.geometry)
    results, layer_checks = [], []
    clipped_cache = {}
    for year in YEARS:
        active = active_mask(source_valid, year)
        electrified = active & electric_mask(source_valid, year)
        operating_geometries = source_valid.geometry.to_numpy()[active]
        operating_length, electrified_length, counts, events = [], [], [], []
        eventmask = (source_valid.rail_opening_year.eq(year)
                     | source_valid.rail_operating_end_exclusive_year.eq(year)
                     | source_valid.rail_electric_start_year.eq(year)
                     | source_valid.rail_electric_end_year.eq(year)).fillna(False).to_numpy(dtype=bool)
        for j in range(len(base)):
            l = local[j]
            a = l[active[si[l]]]
            e = l[electrified[si[l]]]
            key_a, key_e = tuple(a), tuple(e)
            if key_a not in clipped_cache:
                clipped_cache[key_a] = union_length(intersections[a])
            if key_e not in clipped_cache:
                clipped_cache[key_e] = union_length(intersections[e])
            operating_length.append(clipped_cache[key_a])
            electrified_length.append(clipped_cache[key_e])
            counts.append(len(a))
            events.append(int(eventmask[si[l]].sum()))
        operating_length = np.array(operating_length)
        electrified_length = np.array(electrified_length)
        distances_c = nearest_distances(centroid, operating_geometries)
        distances_i = nearest_distances(interior, operating_geometries)
        global_missing_active = int(active_mask(full_source[full_source.rail_geometry_usable.eq(0)], year).sum())
        result = pd.DataFrame({
            "geography": layer,
            "district_year_id": base.district_year_id,
            "boundary_year": base.boundary_year,
            "calendar_year": year,
            "rail_operating_length_km": operating_length,
            "rail_operating_density_km_per_100km2": operating_length / base.area_gis_km2 * 100,
            "rail_electrified_length_km": electrified_length,
            "rail_electrified_share_of_operating_length": np.divide(electrified_length, operating_length,
                out=np.full(len(base), np.nan), where=operating_length > 0),
            "rail_source_record_count_within_district": counts,
            "rail_has_operating_track": (operating_length > 0).astype(int),
            "rail_first_recorded_opening_year": np.where(local_openings <= year, local_openings, np.nan),
            "rail_distance_centroid_to_track_km": distances_c,
            "rail_distance_interior_to_track_km": distances_i,
            "rail_centroid_foreign_network_censor_possible": ((distances_c >= edge_c - 1e-6) | ~inside_c).astype(int),
            "rail_interior_foreign_network_censor_possible": ((distances_i >= edge_i - 1e-6) | ~inside_i).astype(int),
            "rail_source_null_geometry_active_records": global_missing_active,
            "rail_local_missing_geometry_route_possible": local_missing_route * int(global_missing_active > 0),
            "rail_local_source_year_event_count": events,
            "rail_source_coverage": "present_day_Czechia_source_only",
            "rail_state_convention": "reported_year_changes_applied",
        })
        check(f"{layer}_{year}_lengths_nonnegative", (operating_length >= 0).all() and (electrified_length >= 0).all())
        check(f"{layer}_{year}_electric_subset", (electrified_length <= operating_length + 1e-7).all())
        check(f"{layer}_{year}_distances_finite", np.isfinite(distances_c).all() and np.isfinite(distances_i).all())
        check(f"{layer}_{year}_all_districts_present", len(result) == expected and result.district_year_id.is_unique)
        # Independently intersect the entire annual network with each fixed polygon union.
        network_union = networks[year]
        reference_total = network_union.intersection(base_union).length / 1000
        layer_checks.append({"geography": layer, "calendar_year": year,
                             "sum_district_lengths_km": float(operating_length.sum()),
                             "network_clipped_to_district_union_km": reference_total,
                             "boundary_or_overlap_double_count_km": float(operating_length.sum() - reference_total)})
        check(f"{layer}_{year}_national_union_reconciliation", abs(operating_length.sum() - reference_total) < .1,
              f"Difference {operating_length.sum() - reference_total:.9g} km; very small geometry overlaps/shared boundary may occur")
        if year in SNAPSHOTS:
            # Alternative full-network intersection checks for all districts.
            direct_lengths = shapely.length(shapely.intersection(base.geometry.to_numpy(), network_union)) / 1000
            check(f"{layer}_{year}_independent_all_district_length", np.allclose(operating_length, direct_lengths, atol=1e-7, rtol=1e-9),
                  f"max difference {np.max(np.abs(operating_length-direct_lengths)):.9g} km")
            chosen = np.unique(np.linspace(0, len(base) - 1, min(12, len(base))).astype(int))
            direct_distance = shapely.distance(centroid[chosen], network_union) / 1000
            check(f"{layer}_{year}_independent_distance", np.allclose(distances_c[chosen], direct_distance, atol=1e-9, rtol=1e-9))
        results.append(result)
    annual = pd.concat(results, ignore_index=True)
    check(layer + "_annual_complete_panel", len(annual) == len(base)*len(YEARS)
          and not annual.duplicated(["district_year_id", "calendar_year"]).any())
    # Wide, explicitly dated supplements can be joined to a static master by ID.
    metric_columns = [c for c in annual if c.startswith("rail_") and c not in ["rail_source_coverage", "rail_state_convention"]]
    wide = base[["district_year_id", "boundary_year"]].copy()
    wide.insert(0, "geography", layer)
    for year in SNAPSHOTS:
        part = annual.loc[annual.calendar_year.eq(year), ["district_year_id"] + metric_columns]
        part = part.rename(columns={c: c + "_" + str(year) for c in metric_columns})
        wide = wide.merge(part, on="district_year_id", validate="one_to_one")
    wide["rail_source_coverage"] = "present_day_Czechia_source_only"
    wide["rail_state_convention"] = "reported_year_changes_applied"
    wide.to_csv(OUT / ("gis_rail_static_" + layer + ".csv"), index=False)
    annual.to_csv(OUT / ("gis_rail_annual_" + layer + "_1901_1938.csv.gz"), index=False, compression="gzip")
    logging.info("%s: %s rows, %s positive-length source links", layer, len(annual), len(links))
    return annual, links, layer_checks


def build_dictionary():
    defs = {
        "geography": ("code", "Fixed polygon layer: judicial/political districts of 1921 or 1930"),
        "district_year_id": ("identifier", "Unchanged v0.5 primary key for a district and boundary year"),
        "boundary_year": ("year", "Year of the fixed district polygon; independent of railway calendar year"),
        "calendar_year": ("year", "Reconstructed annual network state, applying events reported in this year; year precision only"),
        "rail_operating_length_km": ("km", "Length of spatial union of operating rail route lines actually inside the district; opening <= year < min(closure, removal); unknown end treated as no recorded end"),
        "rail_operating_density_km_per_100km2": ("km/100 km2", "100 times operating line length divided by the district EPSG:3035 area"),
        "rail_electrified_length_km": ("km", "Length of spatial union of operating and recorded electrified lines within the district; electrification <= year < de-electrification"),
        "rail_electrified_share_of_operating_length": ("fraction", "Electrified operating length divided by all operating length; NA if no operating line"),
        "rail_source_record_count_within_district": ("source records", "Number of active source geometries with positive-length intersection; not stations, railway routes or independent lines"),
        "rail_has_operating_track": ("0/1", "One if source-derived operating line length in the polygon is positive; zero means no represented track, not proof of full historical absence"),
        "rail_first_recorded_opening_year": ("year", "Earliest source opening among positive-length district intersections opened by the observation year; not first passenger station service"),
        "rail_distance_centroid_to_track_km": ("km", "Straight planar distance from archived geometric centroid to nearest operating source track in Czechia; not a station, district town, travel time or population-weighted distance"),
        "rail_distance_interior_to_track_km": ("km", "Straight planar distance from archived within-polygon representative point to nearest operating source track in Czechia"),
        "rail_centroid_foreign_network_censor_possible": ("0/1", "One if centroid-track distance reaches/exceeds centroid distance to the judicial1930 study-footprint boundary (or point outside); omitted foreign track might be nearer; heuristic, not a historical border measure"),
        "rail_interior_foreign_network_censor_possible": ("0/1", "Same edge-distance diagnostic for within-polygon representative point; does not establish source completeness when zero"),
        "rail_source_null_geometry_active_records": ("source records", "National source records active under the year rule but excluded because their original geometry is NULL; spatial contribution unknown"),
        "rail_local_missing_geometry_route_possible": ("0/1", "One for a district intersected by any usable source segment with the same route name as an active NULL-geometry record; precautionary locator only, not exact imputation"),
        "rail_local_source_year_event_count": ("source records", "Number of intersecting records with opening, operating end, electrification or de-electrification reported in the observation year; indicates intra-year temporal ambiguity"),
        "rail_source_coverage": ("text", "Territorial scope of the inherited railway source; excludes a complete foreign network"),
        "rail_state_convention": ("text", "reported_year_changes_applied: opening/electrification start in their stated year, closure/removal/de-electrification stop in their stated year; no exact date asserted"),
    }
    rows = []
    for name, (unit, definition) in defs.items():
        rows.append({"table": "gis_rail_annual", "variable": name, "unit": unit, "definition": definition,
                     "period": "1901-1938; fixed 1921/1930 boundaries", "source": "Ondrej Bedrunka, UPOL (2023), ZelezniceCR.zip",
                     "method": "EPSG:3035 clip/union and nearest-track calculation"})
    for year in SNAPSHOTS:
        for name, (unit, definition) in defs.items():
            if name.startswith("rail_") and name not in ["rail_source_coverage", "rail_state_convention"]:
                rows.append({"table": "gis_rail_static", "variable": name + "_" + str(year), "unit": unit,
                             "definition": definition + f" Snapshot for {year}.", "period": str(year),
                             "source": "Ondrej Bedrunka, UPOL (2023), ZelezniceCR.zip",
                             "method": "Pivot of gis_rail_annual; boundary year remains separately identified"})
    return pd.DataFrame(rows)


def register(connection, table, keys, description):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    connection.execute("INSERT INTO gpkg_contents (table_name,data_type,identifier,description,last_change,srs_id) VALUES (?,?,?,?,?,NULL)",
                       (table, "attributes", table, description, now))
    fields = ",".join('"' + k + '"' for k in keys)
    connection.execute(f'CREATE UNIQUE INDEX "idx_{table}_keys" ON "{table}" ({fields})')


def main():
    global BASE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    args = parser.parse_args()
    BASE = args.base.resolve()
    for directory in [SOURCE, OUT, AUDIT]:
        directory.mkdir(parents=True, exist_ok=True)
    initial_base_sha = sha(BASE)
    raw_path, archive = acquire()
    raw = source_frame(raw_path)
    valid = raw[raw.rail_geometry_usable.eq(1)].to_crs(CRS).reset_index(drop=True)
    footprint = shapely.union_all(gpd.read_file(BASE, layer="judicial_1930").to_crs(CRS).geometry)
    networks, network_summary = {}, []
    snapshots = []
    for year in YEARS:
        mask = active_mask(valid, year)
        active = valid.loc[mask]
        net = shapely.union_all(active.geometry)
        networks[year] = net
        raw_total = float(active.length.sum()/1000)
        net_total = float(net.length/1000)
        unique_minus_raw = raw_total - net_total
        check(f"network_{year}_nonempty", not net.is_empty)
        check(f"network_{year}_union_does_not_increase_length", unique_minus_raw >= -1e-7)
        network_summary.append({"calendar_year": year, "active_usable_source_records": len(active),
                                "raw_record_length_km": raw_total, "unique_operating_length_km": net_total,
                                "duplicate_overlap_removed_km": unique_minus_raw})
        if year in SNAPSHOTS:
            snapshots.append({"calendar_year": year, "source": "Bedrunka_UPOL_2023",
                              "rail_operating_length_km": net_total,
                              "state_convention": "reported_year_changes_applied", "geometry": net})
    frames, linkframes, reconciliation = [], [], []
    for layer in LAYERS:
        frame, links, checks = build_layer(layer, valid, raw, networks, footprint)
        frames.append(frame); linkframes.append(links); reconciliation.extend(checks)
    annual = pd.concat(frames, ignore_index=True)
    links = pd.concat(linkframes, ignore_index=True)
    check("annual_panel_complete_all_layers", len(annual) == (330+328+151+151)*38, len(annual))
    check("annual_panel_keys_unique", not annual.duplicated(["geography", "district_year_id", "calendar_year"]).any())
    check("original_v05_unchanged", sha(BASE) == initial_base_sha)
    annual.to_csv(OUT / "gis_rail_annual.csv.gz", index=False, compression="gzip")
    links.to_csv(OUT / "rail_district_source_links.csv.gz", index=False, compression="gzip")
    pd.DataFrame(reconciliation).to_csv(AUDIT / "rail_length_reconciliation.csv", index=False)
    pd.DataFrame(network_summary).to_csv(AUDIT / "rail_network_year_summary.csv", index=False)
    build_dictionary().to_csv(OUT / "rail_data_dictionary.csv", index=False)
    gpkg = OUT / "rail_module.gpkg"
    temp = OUT / "rail_module.partial.gpkg"
    if temp.exists():
        temp.unlink()
    raw.to_file(temp, layer="rail_source_upol", driver="GPKG")
    gpd.GeoDataFrame(snapshots, crs=CRS).to_crs(4326).to_file(temp, layer="rail_network_snapshots", driver="GPKG")
    with sqlite3.connect(temp) as connection:
        annual.to_sql("gis_rail_annual", connection, index=False, if_exists="fail")
        register(connection, "gis_rail_annual", ["geography", "district_year_id", "calendar_year"],
                 "Railway indicators from UPOL 2023 source; year-only reconstruction; fixed historical boundaries; see RAIL_METHODS_CZ.md")
        links.to_sql("rail_district_source_links", connection, index=False, if_exists="fail")
        register(connection, "rail_district_source_links", ["geography", "district_year_id", "rail_source_id"],
                 "Positive-length source-record intersections. Apply temporal masks and union geometry for total lengths; record lengths can overlap.")
        connection.commit()
        check("module_geopackage_integrity", connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok")
    temp.replace(gpkg)
    summaries = []
    for layer in LAYERS:
        layer_rows = annual[(annual.geography == layer) & (annual.calendar_year == 1930)]
        summaries.append({"geography": layer, "districts": len(layer_rows), "annual_rows": int(annual.geography.eq(layer).sum()),
                          "districts_without_represented_track_1930": int(layer_rows.rail_has_operating_track.eq(0).sum()),
                          "sum_district_rail_km_1930": float(layer_rows.rail_operating_length_km.sum()),
                          "districts_with_missing_geometry_route_flag": int(layer_rows.rail_local_missing_geometry_route_possible.sum())})
    source_manifest = {"source_name": "ZelezniceCR: historical rail network in Czechia, 1827-2022",
                       "author": "Ondrej Bedrunka", "institution": "Palacky University Olomouc, Department of Geoinformatics",
                       "publication_year": 2023, "url": SOURCE_URL, "landing_page": SOURCE_PAGE, "documentation_url": SOURCE_DOC,
                       "archive_filename": archive.name, "archive_bytes": archive.stat().st_size, "archive_sha256": sha(archive),
                       "source_geojson_sha256": sha(raw_path), "accessed_utc": datetime.now(timezone.utc).isoformat(),
                       "source_records": len(raw), "usable_geometry_records": len(valid), "null_geometry_records": int(raw.rail_geometry_usable.eq(0).sum()),
                       "licence_status": "No explicit reusable-data licence found in archive; public download verified; permission for public redistribution remains unconfirmed.",
                       "analysis_use": "Combined privately for the requesting researcher; no public publication performed."}
    (SOURCE / "download_manifest.json").write_text(json.dumps(source_manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    pd.DataFrame(CHECKS).to_csv(AUDIT / "rail_validation.csv", index=False)
    manifest = {"module": "rail", "status": "computed_with_documented_source_limitations", "release": "0.6",
                "source": source_manifest, "base_geopackage": str(BASE), "base_sha256": initial_base_sha,
                "analysis_crs": "EPSG:3035", "calendar_years": [1901,1938], "snapshot_years": SNAPSHOTS,
                "layers": summaries, "annual_rows": len(annual), "source_district_links": len(links),
                "annual_columns": annual.columns.tolist(),
                "geopackage": str(gpkg.relative_to(ROOT)), "feature_layers": ["rail_source_upol", "rail_network_snapshots"],
                "attribute_tables": ["gis_rail_annual", "rail_district_source_links"],
                "annual_csv": str((OUT/"gis_rail_annual.csv.gz").relative_to(ROOT)),
                "static_csvs": {l: str((OUT/("gis_rail_static_"+l+".csv")).relative_to(ROOT)) for l in LAYERS},
                "dictionary_csv": str((OUT/"rail_data_dictionary.csv").relative_to(ROOT)),
                "validation": {s: sum(r["status"]==s for r in CHECKS) for s in ["PASS","WARN","FAIL"]},
                "limitations": ["Reconstructed annual states with year-level dates, not exact historical daily snapshots or timetable service.",
                                "One source record has NULL geometry (Poříčany–Nymburk); no fabricated repair; source-derived zeros are not proof of completeness.",
                                "Source covers present-day Czechia; foreign and Slovak networks are absent; nearest-track distances can be censored near the study edge.",
                                "Modern source geometry and documented historical realignments do not resolve every minor historical alignment change.",
                                "Source record count is not station count or route count; distances are straight to track, not travel time or station access.",
                                "Private research integration; public redistribution rights of source database not yet confirmed."],
                "completed_utc": datetime.now(timezone.utc).isoformat()}
    (OUT/"rail_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"status": manifest["status"], "annual_rows": len(annual), "layers": summaries, "validation": manifest["validation"]}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
