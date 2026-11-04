#!/usr/bin/env python3
"""Area-allocate actual LUCC Czechia ZUJ totals to historical districts.

The provider supplies category totals by stable spatial unit, NOT polygons of
individual fields or forests. Every derived district value explicitly retains
that allocation assumption and the source observation year. No 1930 estimate is
interpolated between the source's 1845 and 1948 observations.
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
import requests
from scipy.sparse import csr_matrix
import shapely


ROOT = Path(__file__).resolve().parents[1]
PACKAGED_BASE = ROOT / "inputs/base_v05_inputs.gpkg"
LEGACY_BASE = ROOT.parent / "gis_work/GIS_v04_Preparation/outputs/wave2_completed/historical_gis_czech_lands_v05.gpkg"
DEFAULT_BASE = PACKAGED_BASE if PACKAGED_BASE.exists() else LEGACY_BASE
SOURCE_URL = "https://web.natur.cuni.cz/ksgrrsek/lucc/wp-content/uploads/2017/06/zuj1.zip"
METADATA_URL = "https://web.natur.cuni.cz/ksgrrsek/lucc/wp-content/uploads/2017/06/info_zuj.pdf"
METHOD_URL = "https://web.natur.cuni.cz/ksgrrsek/lucc/wp-content/uploads/2017/06/text1.pdf"
SOURCE_SHA256 = "5f88af6ce1e476d58ac40ce1ff983d33d3971624953780348044418c08c66d88"
RESUMABLE_BASE_SHA256 = "e12e39b14e421394d5f6f083f454ef28178bec5ad8ec62b6f116408c1d4c8748"
LAYERS = {"judicial_1930": 330, "judicial_1921": 328, "political_1930": 151, "political_1921": 151}
YEARS = {1845: "45", 1948: "48", 1990: "90", 2000: "00"}
CATEGORIES = {
    "arable": "ORNA", "permanent_crops": "TRVKULT", "meadows": "LOUKY",
    "pastures": "PASVINY", "forest": "LESY", "water": "VODY",
    "built_up": "ZASTAV", "other": "OSTATNI", "farmland": "ZPF",
}
PRIMITIVES = ["ORNA", "TRVKULT", "LOUKY", "PASVINY", "LESY", "VODY", "ZASTAV", "OSTATNI"]
SOURCE_LABELS = {"ORNA": "orná půda", "TRVKULT": "trvalé kultury", "LOUKY": "louky", "PASVINY": "pastviny", "LESY": "lesy", "VODY": "vodní plochy", "ZASTAV": "zastavěné plochy", "OSTATNI": "ostatní plochy", "ZPF": "zemědělský půdní fond = ORNA + TRVKULT + LOUKY + PASVINY", "JINE": "jiné plochy = VODY + ZASTAV + OSTATNI", "CELKEM": "celková výměra"}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def download(url: str, path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        r = requests.get(url, timeout=(20, 120))
        r.raise_for_status()
        temp = path.with_suffix(path.suffix + ".part")
        temp.write_bytes(r.content)
        temp.replace(path)
    return {"url": url, "path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": digest(path)}


def run(base: Path, min_coverage: float = 0.95, resume: bool = False) -> None:
    if not 0 < min_coverage <= 1:
        raise ValueError("min_coverage must be in (0,1]")
    if resume and digest(base) != RESUMABLE_BASE_SHA256:
        raise ValueError("Resume cache belongs to the pinned v0.5 base; changed inputs require a full build without --resume")
    src = ROOT / "sources/landuse"
    out = ROOT / "modules/landuse"
    audit = ROOT / "audit"
    docs = ROOT / "docs"
    for p in (src, out, audit, docs):
        p.mkdir(parents=True, exist_ok=True)
    archive = src / "zuj1_wp.zip"
    sources = [download(SOURCE_URL, archive), download(METADATA_URL, src / "info_zuj.pdf"), download(METHOD_URL, src / "text1.pdf")]
    if digest(archive) != SOURCE_SHA256:
        raise ValueError("LUCC source differs from the validated 2026-11-03 archive; inspect and deliberately update the pinned source version")
    # DBF contains two different historical encodings in separate name fields.
    # Latin-1 is used as a reversible byte mapping, then each text column is
    # decoded correctly; numeric source values and identifiers remain unchanged.
    source = gpd.read_file(f"/vsizip/{archive.resolve()}/zuj1/zuj1.shp", encoding="latin1")
    source["ZUJ"] = source.ZUJ.map(lambda s: s.encode("latin1").decode("cp1250"))
    source["ZUJ_ALT"] = source.ZUJ_ALT.map(lambda s: s.encode("latin1").decode("cp852"))
    if len(source) != 8903 or not source.CISLO_ZUJ.is_unique:
        raise ValueError("Unexpected LUCC unit count / duplicate IDs")
    if source.geometry.isna().any() or source.is_empty.any() or not source.is_valid.all():
        raise ValueError("Invalid LUCC source geometry")
    source["landuse_unit_id"] = "LUCC-ZUJ-" + source.CISLO_ZUJ.astype(str)
    source["source_dataset"] = "LUCC Czechia, zuj1 archive"
    source["category_geometry_status"] = "category_totals_only_no_parcel_category_polygons"
    projected = source.to_crs(3035)
    sg = projected.geometry.array
    unit_area_m2 = shapely.area(sg)
    if (unit_area_m2 <= 0).any():
        raise ValueError("Nonpositive LUCC unit geometry area")
    source["source_geometry_area_km2"] = unit_area_m2 / 1e6
    source_union = shapely.union_all(sg)
    source_overlap_km2 = float((unit_area_m2.sum() - source_union.area) / 1e6)
    source_year_valid = {}
    issues = []
    tests = [
        {"test": "LUCC_source_archive_checksum", "status": "PASS", "detail": SOURCE_SHA256},
        {"test": "LUCC_source_unit_ids_unique_and_count", "status": "PASS", "detail": "8903 units"},
        {"test": "LUCC_source_geometries_valid", "status": "PASS", "detail": "All source polygons valid; original CRS EPSG:5514"},
        {"test": "LUCC_names_decoded_without_replacement", "status": "PASS", "detail": "ZUJ Windows-1250; ZUJ_ALT CP852; no numeric values changed"},
    ]
    for year, suffix in YEARS.items():
        cols = [f"{cat}_{suffix}" for cat in SOURCE_LABELS]
        vals = source[cols].to_numpy(float)
        total = source[f"CELKEM_{suffix}"].to_numpy(float)
        finite = np.isfinite(vals).all(axis=1)
        nonnegative = (vals >= 0).all(axis=1)
        closure = source[[f"{cat}_{suffix}" for cat in PRIMITIVES]].sum(axis=1).to_numpy() - total
        zpf_diff = source[[f"{cat}_{suffix}" for cat in PRIMITIVES[:4]]].sum(axis=1).to_numpy() - source[f"ZPF_{suffix}"].to_numpy()
        other_diff = source[[f"{cat}_{suffix}" for cat in ["VODY", "ZASTAV", "OSTATNI"]]].sum(axis=1).to_numpy() - source[f"JINE_{suffix}"].to_numpy()
        valid = finite & nonnegative & (total > 0) & (np.abs(closure) <= 0.5) & (np.abs(zpf_diff) <= 0.5) & (np.abs(other_diff) <= 0.5)
        source_year_valid[year] = valid
        source[f"valid_composition_{year}"] = valid.astype(int)
        statuses = []
        for i in range(len(source)):
            reasons = []
            if not finite[i]: reasons.append("nonfinite_source_value")
            if not nonnegative[i]: reasons.append("negative_source_category_area")
            if total[i] <= 0: reasons.append("zero_or_negative_source_total_missing_composition")
            if abs(closure[i]) > 0.5: reasons.append("source_category_sum_differs_from_total_over_0_5ha")
            if abs(zpf_diff[i]) > 0.5: reasons.append("source_farmland_sum_inconsistent_over_0_5ha")
            if abs(other_diff[i]) > 0.5: reasons.append("source_other_combined_sum_inconsistent_over_0_5ha")
            statuses.append(";".join(reasons) if reasons else "valid_source_composition")
            if reasons:
                issues.append({"landuse_unit_id": source.landuse_unit_id.iloc[i], "CISLO_ZUJ": int(source.CISLO_ZUJ.iloc[i]), "ZUJ": source.ZUJ.iloc[i], "calendar_year": year, "reason": ";".join(reasons), "source_total_ha": total[i], "component_sum_minus_total_ha": closure[i], "source_geometry_area_km2": unit_area_m2[i] / 1e6, **{c: float(source[c].iloc[i]) for c in cols}})
        source[f"source_quality_{year}"] = statuses
        tests.append({"test": f"LUCC_{year}_invalid_unit_years_explicitly_excluded", "status": "PASS", "detail": f"valid={valid.sum()}, excluded={(~valid).sum()}; no repair, imputation or zero filling"})
    pd.DataFrame(issues).to_csv(audit / "landuse_source_unit_year_exclusions.csv", index=False)
    source.drop(columns="geometry").to_csv(out / "lucc_source_units_attributes.csv.gz", index=False, compression="gzip")
    gpkg = out / "landuse.gpkg"
    if gpkg.exists():
        gpkg.unlink()
    source.to_file(gpkg, layer="lucc_source_units", driver="GPKG")
    link_rows, panel_rows, static_rows, geometry_qa = [], [], [], []
    for layer, expected in LAYERS.items():
        print(f"LUCC: {layer}: loading districts and saved intersections", flush=True)
        d = gpd.read_file(base, layer=layer, columns=["district_year_id", "boundary_year"])
        if len(d) != expected or not d.district_year_id.is_unique:
            raise ValueError(f"Unexpected district keys/count {layer}")
        d = d.to_crs(3035)
        dg = d.geometry.array
        district_area_m2 = shapely.area(dg)
        saved_links = out / f"landuse_district_unit_links_{layer}.csv.gz"
        saved_static = out / f"gis_landuse_static_{layer}.csv"
        cached_static = None
        if resume and saved_static.exists():
            cached_static = pd.read_csv(saved_static).set_index("district_year_id").reindex(d.district_year_id)
            if len(cached_static) != len(d) or cached_static.geography.isna().any() or not cached_static.geography.eq(layer).all():
                raise ValueError("Cached LUCC static geography/keys do not match current base")
        if resume and saved_links.exists():
            cached_links = pd.read_csv(saved_links)
            didx = pd.Index(d.district_year_id).get_indexer(cached_links.district_year_id)
            sidx = pd.Index(source.landuse_unit_id).get_indexer(cached_links.landuse_unit_id)
            if (didx < 0).any() or (sidx < 0).any() or not cached_links.geography.eq(layer).all() or cached_links.duplicated(["district_year_id", "landuse_unit_id"]).any():
                raise ValueError("Cached LUCC intersection keys do not match current source/base")
            area = cached_links.intersection_area_km2.to_numpy() * 1e6
            if not np.allclose(cached_links.fraction_of_source_unit_geometry, area / unit_area_m2[sidx], atol=1e-10, rtol=1e-10):
                raise ValueError("Cached LUCC weights do not match current source geometry area")
            clipped = None if cached_static is not None else shapely.intersection(dg[didx], sg[sidx])
        else:
            didx, sidx = projected.sindex.query(d.geometry, predicate="intersects")
            clipped = shapely.intersection(dg[didx], sg[sidx])
            area = shapely.area(clipped)
            keep = area > 1e-6  # only zero/numerically zero line or point contacts dropped
            didx, sidx, clipped, area = didx[keep], sidx[keep], clipped[keep], area[keep]
        fraction_source = area / unit_area_m2[sidx]
        if (fraction_source > 1 + 1e-8).any() or (fraction_source <= 0).any():
            raise ValueError("Invalid source-area allocation fractions")
        fraction_source = np.minimum(fraction_source, 1.0)
        is_partial = fraction_source < 1 - 1e-6
        weight = csr_matrix((fraction_source, (didx, sidx)), shape=(len(d), len(source)))
        count_matrix = csr_matrix((np.ones(len(area)), (didx, sidx)), shape=(len(d), len(source)))
        links = pd.DataFrame({"geography": layer, "district_year_id": d.district_year_id.to_numpy()[didx], "boundary_year": d.boundary_year.to_numpy()[didx], "landuse_unit_id": source.landuse_unit_id.to_numpy()[sidx], "CISLO_ZUJ": source.CISLO_ZUJ.to_numpy()[sidx], "intersection_area_km2": area / 1e6, "fraction_of_source_unit_geometry": fraction_source, "fraction_of_district_geometry": area / district_area_m2[didx], "source_unit_partially_allocated": is_partial.astype(int), "source_unit_geometry_area_km2": unit_area_m2[sidx] / 1e6, "allocation_method": "area_prorated_source_unit_category_totals"})
        links.to_csv(out / f"landuse_district_unit_links_{layer}.csv.gz", index=False, compression="gzip")
        link_rows.append(links)
        if cached_static is not None:
            total_covered = cached_static.landuse_geometric_source_coverage_share.to_numpy() * district_area_m2
        else:
            total_covered = np.array([shapely.union_all(clipped[didx == i]).area for i in range(len(d))])
        coverage = total_covered / district_area_m2
        if (coverage > 1 + 1e-8).any() or (coverage < 0).any():
            raise ValueError("Invalid geometry coverage fraction")
        # Independent conservation: compare sum of district intersections to a
        # single intersection with the union of all district polygons.
        footprint = shapely.union_all(dg)
        # A prepared containment test avoids repeatedly intersecting thousands
        # of interior source polygons with the entire national outline.
        # Only the polygons actually cut by the outer footprint need overlay.
        shapely.prepare(footprint)
        wholly_inside = shapely.covers(footprint, sg)
        independent_fraction = np.ones(len(source))
        independent_fraction[~wholly_inside] = shapely.area(shapely.intersection(sg[~wholly_inside], footprint)) / unit_area_m2[~wholly_inside]
        summed_fraction = np.asarray(weight.sum(axis=0)).ravel()
        double_count_area_km2 = float(np.sum((summed_fraction - independent_fraction) * unit_area_m2) / 1e6)
        if abs(double_count_area_km2) > 0.02:
            raise ValueError(f"Unexpected overlapping historical districts: {layer}, {double_count_area_km2} km2")
        geometry_qa.append({"geography": layer, "district_union_area_km2": footprint.area / 1e6, "district_area_sum_km2": district_area_m2.sum() / 1e6, "source_unit_overlap_total_km2": source_overlap_km2, "district_intersection_double_count_area_km2": double_count_area_km2, "minimum_geometric_source_coverage_share": float(coverage.min()), "mean_geometric_source_coverage_share": float(coverage.mean()), "links": len(links)})
        tests.append({"test": f"{layer}_independent_footprint_intersection_conservation", "status": "PASS", "detail": f"sum-of-district minus union intersections={double_count_area_km2:.10f} km2"})
        static = pd.DataFrame({"geography": layer, "district_year_id": d.district_year_id, "boundary_year": d.boundary_year, "landuse_geometric_source_coverage_share": coverage, "landuse_allocation_method": "area_prorated_source_unit_category_totals"})
        for year, suffix in YEARS.items():
            valid = source_year_valid[year]
            if cached_static is not None:
                valid_covered = cached_static[f"landuse_{year}_valid_source_coverage_share"].to_numpy() * district_area_m2
            else:
                valid_covered = np.array([shapely.union_all(clipped[(didx == i) & valid[sidx]]).area for i in range(len(d))])
            valid_coverage = valid_covered / district_area_m2
            n_valid = np.asarray(count_matrix @ valid.astype(int)).ravel().astype(int)
            n_excluded = np.asarray(count_matrix @ (~valid).astype(int)).ravel().astype(int)
            src_total = source[f"CELKEM_{suffix}"].to_numpy(float)
            allocated_total = np.asarray(weight @ np.where(valid, src_total, 0.0)).ravel()
            if cached_static is not None:
                partial_area = cached_static[f"landuse_{year}_partial_unit_area_share_of_district"].to_numpy() * district_area_m2
            else:
                partial_area = np.zeros(len(d))
                for di in range(len(d)):
                    chosen = (didx == di) & is_partial & valid[sidx]
                    if chosen.any():
                        partial_area[di] = shapely.union_all(clipped[chosen]).area
            partial_fraction_district = partial_area / district_area_m2
            partial_fraction_covered = np.divide(partial_area, valid_covered, out=np.full(len(d), np.nan), where=valid_covered > 0)
            usable = (valid_coverage >= min_coverage) & (allocated_total > 0)
            result = pd.DataFrame({"geography": layer, "district_year_id": d.district_year_id, "boundary_year": d.boundary_year, "calendar_year": year, "landuse_source_total_area_allocated_ha": allocated_total, "landuse_valid_source_coverage_share": valid_coverage, "landuse_geometric_source_coverage_share": coverage, "landuse_partial_unit_area_share_of_district": partial_fraction_district, "landuse_partial_unit_area_share_of_valid_coverage": partial_fraction_covered, "landuse_source_unit_count": n_valid, "landuse_excluded_source_unit_count": n_excluded, "landuse_share_values_usable": usable.astype(int), "landuse_min_coverage_threshold": min_coverage, "landuse_allocation_method": "area_prorated_source_unit_category_totals", "landuse_quality_flag": np.where(usable, "area_allocated_estimate", "shares_withheld_insufficient_valid_source_coverage")})
            primitive_allocated = []
            for name, original_name in CATEGORIES.items():
                original_vals = source[f"{original_name}_{suffix}"].to_numpy(float)
                allocated = np.asarray(weight @ np.where(valid, original_vals, 0.0)).ravel()
                share = np.divide(allocated, allocated_total, out=np.full(len(d), np.nan), where=allocated_total > 0)
                share[~usable] = np.nan
                if (share[np.isfinite(share)] < -1e-10).any() or (share[np.isfinite(share)] > 1 + 1e-4).any():
                    raise ValueError("Invalid allocated land-use share")
                result[f"landuse_{name}_area_allocated_ha"] = allocated
                result[f"landuse_{name}_area_allocated_share"] = share
                static[f"landuse_{name}_{year}_area_allocated_share"] = share
                if original_name in PRIMITIVES:
                    primitive_allocated.append(allocated)
                # National/category total is independently checked against the
                # intersection of source polygons with the whole district footprint.
                expected_total = float(np.dot(independent_fraction, np.where(valid, original_vals, 0.0)))
                observed_total = float(allocated.sum())
                if not np.isclose(observed_total, expected_total, rtol=1e-7, atol=0.25):
                    raise ValueError(f"Independent land-use total check failed: {layer}/{year}/{name}")
            diff = np.sum(primitive_allocated, axis=0) - allocated_total
            # Eight primitive categories are disjoint; farmland is an aggregate
            # and must not be added to them a second time.
            result["landuse_primitive_sum_minus_total_ha"] = diff
            allowed_rounding = np.asarray(weight @ np.where(valid, np.abs(source[[f"{c}_{suffix}" for c in PRIMITIVES]].sum(axis=1).to_numpy() - src_total), 0.0)).ravel() + 1e-7
            if (np.abs(diff) > allowed_rounding + 1e-6).any():
                raise ValueError("Unexpected category closure beyond archived source rounding")
            static[f"landuse_total_{year}_area_allocated_ha"] = allocated_total
            static[f"landuse_{year}_valid_source_coverage_share"] = valid_coverage
            static[f"landuse_{year}_partial_unit_area_share_of_district"] = partial_fraction_district
            static[f"landuse_{year}_share_values_usable"] = usable.astype(int)
            static[f"landuse_{year}_excluded_source_unit_count"] = n_excluded
            panel_rows.append(result)
            result.to_csv(out / f"gis_landuse_{layer}_{year}.csv", index=False, float_format="%.10g")
            tests.extend([
                {"test": f"{layer}_{year}_all_districts_and_unique_keys", "status": "PASS", "detail": str(len(result))},
                {"test": f"{layer}_{year}_independent_source_total_conservation", "status": "PASS", "detail": "Nine categories checked against source intersection with district union"},
                {"test": f"{layer}_{year}_component_closure_within_source_rounding", "status": "PASS", "detail": f"max_absolute_difference_ha={abs(diff).max():.8f}"},
                {"test": f"{layer}_{year}_low_coverage_shares_withheld", "status": "PASS", "detail": f"usable={usable.sum()}; withheld={(~usable).sum()}; min_valid_coverage={valid_coverage.min():.8f}; threshold={min_coverage}"},
            ])
        static.to_csv(out / f"gis_landuse_static_{layer}.csv", index=False, float_format="%.10g")
        static_rows.append(static)
        print(f"LUCC: {layer}: complete, {len(links)} intersections", flush=True)
    links_all = pd.concat(link_rows, ignore_index=True)
    panel = pd.concat(panel_rows, ignore_index=True)
    static_all = pd.concat(static_rows, ignore_index=True)
    if links_all.duplicated(["geography", "district_year_id", "landuse_unit_id"]).any() or panel.duplicated(["geography", "district_year_id", "calendar_year"]).any():
        raise ValueError("Duplicate LUCC district/source/year keys")
    links_all.to_csv(out / "landuse_district_unit_links.csv.gz", index=False, compression="gzip")
    panel.to_csv(out / "gis_landuse.csv", index=False, float_format="%.10g")
    static_all.to_csv(out / "gis_landuse_static.csv", index=False, float_format="%.10g")
    pd.DataFrame(geometry_qa).to_csv(audit / "landuse_geometry_coverage.csv", index=False)
    pd.DataFrame(tests).to_csv(audit / "landuse_validation.csv", index=False)
    with sqlite3.connect(gpkg) as conn:
        panel.to_sql("gis_landuse", conn, index=False, if_exists="replace")
        static_all.to_sql("gis_landuse_static", conn, index=False, if_exists="replace")
        links_all.to_sql("landuse_district_unit_links", conn, index=False, if_exists="replace")
        for table in ("gis_landuse", "gis_landuse_static", "landuse_district_unit_links"):
            conn.execute("INSERT OR REPLACE INTO gpkg_contents (table_name,data_type,identifier,description,last_change) VALUES (?,?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'))", (table, "attributes", table, "LUCC category-area allocation; original observation years1845/1948/1990/2000; no1930interpolation"))
        conn.execute("CREATE UNIQUE INDEX landuse_panel_key ON gis_landuse(geography,district_year_id,calendar_year)")
        conn.execute("CREATE UNIQUE INDEX landuse_links_key ON landuse_district_unit_links(geography,district_year_id,landuse_unit_id)")

    definitions = {
        "geography": ("code", "Historical district layer; alternative geographies are not independent observations."),
        "district_year_id": ("code", "Historical district identifier from the unchanged base."),
        "boundary_year": ("year", "District-boundary vintage, distinct from land-use observation year."),
        "calendar_year": ("year", "Provider's LUCC time label: 1845, 1948, 1990 or 2000; never an interpolated 1930 value. The 1845 label represents the Stable Cadastre written records based on mapping approximately 1826–1843. Source category harmonization is documented separately."),
        "landuse_source_total_area_allocated_ha": ("ha", "Sum of valid source CELKEM totals multiplied by district intersection/source-unit geometry fractions; denominator of category shares, not the GIS area of the entire district."),
        "landuse_valid_source_coverage_share": ("fraction0–1", "Union of intersecting source polygons with valid composition for this year divided by full district GIS area."),
        "landuse_geometric_source_coverage_share": ("fraction0–1", "Union of all source-unit geometry inside district divided by full district GIS area; independent of source-year attribute validity."),
        "landuse_partial_unit_area_share_of_district": ("fraction0–1", "District GIS-area fraction covered by valid source units that lie only partly in this district (source fraction<1−1e-6); union-based, quantifies exposure to within-unit allocation assumptions."),
        "landuse_partial_unit_area_share_of_valid_coverage": ("fraction0–1", "Same partial-unit area divided by valid covered GIS area; not the fraction of observations directly measured at district level."),
        "landuse_source_unit_count": ("count", "Number of intersecting valid source units for this observation year."),
        "landuse_excluded_source_unit_count": ("count", "Number of intersecting source units excluded because year-specific totals/composition failed source checks."),
        "landuse_share_values_usable": ("0/1", "One when valid source coverage reaches configured threshold and allocated source total is positive; does not remove uncertainty from area allocation."),
        "landuse_min_coverage_threshold": ("fraction", "Explicit coverage threshold used to withhold main category shares, default0.95; analyst choice, not a confidence level."),
        "landuse_allocation_method": ("text", "Category totals are apportioned by geometric area fractions; no exact field/forest polygons are available within each source ZUJ."),
        "landuse_quality_flag": ("text", "Area-allocated estimate or shares withheld for insufficient valid coverage."),
        "landuse_primitive_sum_minus_total_ha": ("ha", "Sum of the eight primitive allocated category areas minus allocated source CELKEM; small residuals reflect source rounding."),
        "landuse_unit_id": ("code", "Stable LUCC unit identifier derived from CISLO_ZUJ."),
        "CISLO_ZUJ": ("code", "Original provider unit identifier; ZUJ labels do not correspond to administrative municipalities."),
        "intersection_area_km2": ("km2", "Actual geometry overlap between source unit and district in EPSG:3035."),
        "fraction_of_source_unit_geometry": ("fraction0–1", "Intersection GIS area divided by total source-unit GIS area; multiplier for source category hectares."),
        "fraction_of_district_geometry": ("fraction0–1", "Intersection GIS area divided by district GIS area."),
        "source_unit_partially_allocated": ("0/1", "One where less than1−1e-6 of source unit geometry falls into this district."),
        "source_unit_geometry_area_km2": ("km2", "Area of full source-unit geometry in EPSG:3035, distinct from provider's year-specific CELKEM hectares."),
        "allocation_method": ("text", "Uniform areal allocation of source-unit category totals to the intersecting district fragment."),
    }
    dictionary = []
    license_note = "Academic/study use only; no commercial use; source citation required (provider info_zuj.pdf)"
    for table, frame in [("gis_landuse", panel), ("gis_landuse_static", static_all), ("landuse_district_unit_links", links_all)]:
        for col in frame.columns:
            if col in definitions:
                unit, definition = definitions[col]
            elif col.startswith("landuse_") and col.endswith("area_allocated_share"):
                unit, definition = "fraction0–1", "Area-allocated category total divided by allocated valid source CELKEM total for the explicit observation year. Missing below the stated coverage threshold. Category distribution inside split source units is assumed uniform. Farmland is an aggregate of arable/permanent crops/meadows/pastures and must not be added to the eight primitive shares."
            elif col.startswith("landuse_") and col.endswith("area_allocated_ha"):
                unit, definition = "ha", "Actual source category or CELKEM total, multiplied by district/source polygon area fractions and summed over valid source units; applies only to covered valid source area, not extrapolated to the entire district."
            elif col.endswith("valid_source_coverage_share"):
                unit, definition = definitions["landuse_valid_source_coverage_share"]
            elif col.endswith("partial_unit_area_share_of_district"):
                unit, definition = definitions["landuse_partial_unit_area_share_of_district"]
            elif col.endswith("share_values_usable"):
                unit, definition = definitions["landuse_share_values_usable"]
            elif col.endswith("excluded_source_unit_count"):
                unit, definition = definitions["landuse_excluded_source_unit_count"]
            else:
                raise ValueError("Missing dictionary definition: " + col)
            if ("_water_" in col or "_other_" in col) and (table != "gis_landuse_static" or "_1948_" in col):
                definition += " Provider adjustment for 1948: running-water area from 1845 was added to recorded 1948 standing-water area and subtracted from 1948 other area; this inherited harmonization is not a new calculation here."
            dictionary.append({"table": table, "variable": col, "unit": unit, "definition": definition, "source": "LUCC Czechia, zuj1", "license": license_note})
    for col in source.columns:
        if col == "geometry": unit, definition = "Polygon/MultiPolygon EPSG:5514", "Original provider ZUJ polygon, not a polygon of each land-use category."
        elif col in definitions: unit, definition = definitions[col]
        elif col in ("ZUJ", "ZUJ_ALT"): unit, definition = "text", "Original locality label decoded from its actual DBF text encoding; names are orientational, not historical municipal IDs."
        elif col.startswith("valid_composition_"): unit, definition = "0/1", "Whether this source unit/year passes nonnegative positive-total and composition-sum checks."
        elif col.startswith("source_quality_"): unit, definition = "text", "Explicit reason for excluding this source unit/year; original provider numbers remain present."
        elif col in ("source_dataset", "category_geometry_status"): unit, definition = "text", "Source provenance / warning that categories have unit totals, not within-unit geometries."
        elif col == "source_geometry_area_km2": unit, definition = "km2", "Area of original source polygon after transformation to EPSG:3035."
        elif "_" in col and col.rsplit("_", 1)[0] in SOURCE_LABELS:
            cat, yy = col.rsplit("_", 1)
            year = next(y for y, s in YEARS.items() if s == yy)
            unit, definition = "ha", f"Original unmodified source {SOURCE_LABELS[cat]} for {year}; anomalous/zero totals are preserved and flagged, never silently repaired."
            if col in ("VODY_48", "OSTATNI_48"):
                definition += " Provider had already added 1845 running-water area to 1948 water and subtracted it from 1948 other area to harmonize categories."
        else: raise ValueError("Missing source dictionary definition: " + col)
        dictionary.append({"table": "lucc_source_units", "variable": col, "unit": unit, "definition": definition, "source": "LUCC Czechia, zuj1", "license": license_note})
    pd.DataFrame(dictionary).to_csv(out / "dictionary.csv", index=False)

    coverage_summary = panel.groupby(["geography", "calendar_year"]).agg(districts=("district_year_id", "size"), usable_districts=("landuse_share_values_usable", "sum"), min_valid_coverage=("landuse_valid_source_coverage_share", "min"), mean_valid_coverage=("landuse_valid_source_coverage_share", "mean"), mean_partial_unit_area_share=("landuse_partial_unit_area_share_of_district", "mean")).reset_index()
    coverage_summary.to_csv(audit / "landuse_coverage_by_geography_year.csv", index=False)
    manifest = {"module": "landuse", "status": "completed_area_allocated_estimates_with_source_exclusions", "built_utc": datetime.now(timezone.utc).isoformat(), "sources": sources, "source_author": "Ivan Bičík, Zbyněk Janoušek, Jan Kabrda a kol., Přírodovědecká fakulta Univerzity Karlovy", "source_citation": "Databáze LUCC Czechia: Databáze dlouhodobých změn využití ploch Česka (1845–2000), dokumentace13.3.2015", "source_license": license_note, "source_name_encoding": {"ZUJ": "CP1250", "ZUJ_ALT": "CP852"}, "source_observation_years": list(YEARS), "source_unit_count": len(source), "source_year_exclusion_counts": {str(y): int((~v).sum()) for y, v in source_year_valid.items()}, "source_geometry_overlap_km2": source_overlap_km2, "source_crs": "EPSG:5514", "area_crs": "EPSG:3035", "min_valid_coverage_for_main_shares": min_coverage, "tables": {"gis_landuse": "modules/landuse/gis_landuse.csv", "gis_landuse_static": "modules/landuse/gis_landuse_static.csv", "landuse_district_unit_links": "modules/landuse/landuse_district_unit_links.csv.gz"}, "spatial_file": "modules/landuse/landuse.gpkg", "spatial_layers": ["lucc_source_units"], "static_by_geography": {layer: f"modules/landuse/gis_landuse_static_{layer}.csv" for layer in LAYERS}, "row_counts": {"source_units": len(source), "district_unit_links": len(links_all), "district_year_panel": len(panel), "static_districts": len(static_all)}, "validation": {"pass": len(tests), "fail": 0, "file": "audit/landuse_validation.csv"}, "source_exclusion_file": "audit/landuse_source_unit_year_exclusions.csv", "coverage_summary": coverage_summary.to_dict("records"), "limitations": ["All district statistics are explicitly area-allocated source-unit category totals, not exact within-unit forest/field locations.", "Shares use allocated valid source CELKEM as denominator; geographic source coverage is separately reported against full district area.", "No land-use observations or interpolation for1930 are created.", "18 units have zero1845totals; three have negative1948category values; one has inconsistent1990totals. Original values are archived and whole unit/year compositions excluded.", "Main shares are withheld below95%valid source coverage by default; partial allocated hectares remain explicit, not inflated to cover missing areas.", "1948/1990/2000 are later observations and must not be treated as pre1930covariates.", "Small provider geometry overlaps are quantified; categories have no independent within-unit polygon geometry."]}
    manifest["source_temporal_and_classification_notes"] = {
        "1845": "Provider time label approximately representing Stable Cadastre written records based on mapping circa 1826–1843; not a single-date 1845 survey.",
        "1948_water_other": "Provider water area for 1948 combines reported standing water in 1948 with running-water area from 1845; the latter was subtracted from other area in 1948. Original harmonized values are retained unchanged.",
        "spatial_units": "Provider combined cadastral units using 1990 as area reference and a target of at most 1% area change; documented exceptions remain. Source geometry is harmonized, not a separate parcel-boundary map for each year.",
        "missing_1845": "The methodological text reports 19 Hlucinsko units without 1845 data; this exact archived data version contains 18 source units with nonpositive 1845 total. The actual values are audited, rather than forcing the prose count."
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    text = """# LUCC Czechia: skutečné historické využití půdy a plošný převod na okresy

## Zdroj a časové řezy

Byl stažen a otevřen oficiální archiv `zuj1.zip` (8 036 575 bytů). Obsahuje **8 903 polygonů základních územních jednotek** s kategoriálními výměrami v hektarech pro roky **1845, 1948, 1990 a 2000**. Původní čísla jsou zachována ve zdrojové vrstvě i ZIPu. ZÚJ nejsou naše historické okresy ani automaticky obce. Názvy v polích ZUJ a ZUJ_ALT jsou dekódovány z Windows-1250 a CP852; číselné údaje se tím nemění.

Rok **1845 je označení časového řezu poskytovatele**: vychází z písemného operátu stabilního katastru a mapování přibližně 1826–1843. Nejde o jednodenní měření roku 1845. Autoři sjednotili starší katastry do prostorově srovnatelných ZÚJ s referenční rozlohou roku 1990 a cílovou změnou rozlohy nejvýše 1 %; dokumentují i výjimky. Zdrojová geometrie proto nepředstavuje samostatnou mapu parcel pro každý historický rok.

U vodních a ostatních ploch **1948 existuje již ve zdroji zvláštní rekonstrukce**: autoři přidali k evidovaným stojatým vodám roku 1948 výměru tekoucích vod roku 1845 a tutéž výměru odečetli od ostatních ploch roku 1948. Tyto harmonizované původní hodnoty zachováváme; všechny kategorie roku 1948 nelze označit za čistě přímá pozorování téhož roku.

## Co přesně znamená připojený údaj

Vypočteme průnik historického okresu d a zdrojové jednotky u v plošné projekci EPSG:3035. Váha je `plocha(průnik d,u) / plocha(u)`. Touto vahou násobíme každou původní kategoriální výměru v hektarech a součty za okres sečteme. Jmenovatelem podílů je stejně přidělená původní celková výměra CELKEM, nikoli automaticky GIS plocha celého okresu.

**Kategorie uvnitř jednotky nemají vlastní geometrii.** Pokud ZÚJ přesahuje okres, přidělení výměry lesa nebo orné půdy do jeho části předpokládá rovnoměrné rozložení této kategorie v jednotce. Proto všechny odvozené hodnoty nesou označení `area_allocated`. Výměry nejsou přesnou mapou polí nebo lesa uvnitř historického okresu. Samostatně je uveden podíl okresní plochy pocházející z částečně přiřazených zdrojových jednotek. Původní podrobná váhová tabulka je přiložena.

Podíl plochy z dělených ZÚJ je diagnostika použití plošného převodu, **nikoli velikost statistické chyby**. I jednotka zahrnutá z více než 99 % se označí jako dělená, pokud chybějící zlomek překračuje 0,0001 % její geometrické plochy. Drobné odchylky obou nezávisle vytvořených hranic mohou tento ukazatel zvýšit. V detailní tabulce je proto zachován skutečný zlomek přiřazení každé jednotky; samotný souhrnný ukazatel nelze interpretovat jako procento nepřesných dat.

## Pokrytí a zdrojové problémy

Plošné pokrytí se počítá vůči **celé GIS ploše okresu**, a to z geometrického sjednocení zdrojových polygonů. Platné pokrytí je určeno samostatně pro každý zdrojový rok. Hlavní podíly jsou při platném pokrytí pod 95 % ponechány jako NA; nejde o nulový výskyt dané kategorie. Hranice 95 % je explicitní analytická volba, ne interval spolehlivosti. V dlouhé tabulce zůstávají dílčí přidělené hektary a jejich jmenovatel; chybějící část okresu se neextrapoluje.

Kontrola skutečných souborů zjistila:

- 18 jednotek na Hlučínsku s nulovou celkovou výměrou roku 1845;
- záporné ostatní plochy roku 1948 ve třech jednotkách: Hustopeče nad Bečvou, Skalička u Hranic a Špičky;
- nesoulad součtu kategorií a CELKEM o 27 ha v Heroltovicích roku 1990.

Tyto jednotky–roky jsou z kompozičních agregací vyřazeny, zachovány v původním zdroji a popsány v auditu. Čísla se neopravují odhadem. Drobné ostatní součtové rozdíly jsou kontrolovány proti zaokrouhlení původních údajů na desetinu hektaru. Malé překryvy zdrojových geometrií jsou zvlášť kvantifikovány. Metodický text hovoří o 19 hlučínských ZÚJ bez dat 1845, ale tento konkrétní archiv obsahuje 18 jednotek s nulovým celkovým údajem. Audit vychází z jeho skutečných řádků a tento rozdíl neskrývá.

## Kategorie a časová interpretace

Osm základních kategorií: orná půda, trvalé kultury, louky, pastviny, lesy, vody, zastavěné a ostatní plochy. Zemědělský půdní fond je součet prvních čtyř a nesmí se k nim přičíst podruhé. Rok 1930 nebyl vytvořen interpolací. Pozorování 1948, 1990 a 2000 jsou pozdější stavy, nikoli charakteristika krajiny před rokem 1930.

## Licence a reprodukce

Poskytovatel určuje databázi pro studijní a akademické účely, zakazuje komerční užití a vyžaduje citaci. Zdroj: Databáze LUCC Czechia, Ivan Bičík a kolektiv, PřF UK. Přesné adresy, kontrolní součty a původní dokumentace jsou v `sources/landuse` a manifestu.

`python scripts/build_landuse.py --base /cesta/k/historical_gis_czech_lands_v05.gpkg --min-coverage 0.95`

Vstupní okresy ani jejich dosavadní statistiky se nepřepisují. Výsledky jsou v `modules/landuse`, kontrolní tabulky v `audit/landuse_*`.
"""
    (docs / "LANDUSE_METHODS_CZ.md").write_text(text, encoding="utf-8")
    print(json.dumps({"module": "landuse", "status": manifest["status"], "rows": manifest["row_counts"], "validation": manifest["validation"], "coverage_summary": manifest["coverage_summary"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--min-coverage", type=float, default=0.95)
    parser.add_argument("--resume", action="store_true", help="Reuse saved intersection weights and completed geometry diagnostics after validation against current keys/source areas")
    args = parser.parse_args()
    run(args.base, args.min_coverage, args.resume)
