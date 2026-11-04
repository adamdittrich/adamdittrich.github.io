#!/usr/bin/env python3
"""Attach real HydroBASINS v1c catchment polygons to historical districts.

The original archive is cached unchanged. Selected .shp/.shx/.dbf/.prj files
are extracted without their optional .sbn/.sbx indexes: the publisher's .sbn
index for level 6 is rejected by the installed GDAL. No geometry is inferred
from a map image. All area calculations use EPSG:3035.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import platform
import sqlite3
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import requests
import shapely

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
BASE_DEFAULT = (ROOT / 'inputs/base_v05_inputs.gpkg' if (ROOT / 'inputs/base_v05_inputs.gpkg').exists()
                else PROJECT / 'gis_work/GIS_v04_Preparation/outputs/wave2_completed/historical_gis_czech_lands_v05.gpkg')
SRC = ROOT / 'sources/basins'
OUT = ROOT / 'modules/basins'
AUDIT = ROOT / 'audit'
DOCS = ROOT / 'docs'
URL = 'https://data.hydrosheds.org/file/hydrobasins/standard/hybas_eu_lev01-12_v1c.zip'
PRODUCT_URL = 'https://www.hydrosheds.org/products/hydrobasins'
TECH_URL = 'https://data.hydrosheds.org/file/technical-documentation/HydroBASINS_TechDoc_v1c.pdf'
LAYERS = ['judicial_1930', 'judicial_1921', 'political_1930', 'political_1921']
LEVELS = [6, 8, 12]
CRS = 3035
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(2**20), b''):
            h.update(b)
    return h.hexdigest()


def relative(path):
    return str(Path(path).resolve().relative_to(ROOT))


def fetch(url, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    part = path.with_name(path.name + '.part')
    try:
        with requests.get(url, stream=True, timeout=(30, 120)) as r:
            r.raise_for_status()
            digest = hashlib.sha1()
            n = 0
            with part.open('wb') as f:
                for b in r.iter_content(2**20):
                    if b:
                        f.write(b)
                        digest.update(b)
                        n += len(b)
            if r.headers.get('content-length') and n != int(r.headers['content-length']):
                raise ValueError('Download is incomplete')
            upstream_sha1 = r.headers.get('x-bz-info-large_file_sha1')
            if upstream_sha1 and digest.hexdigest() != upstream_sha1:
                raise ValueError('Download does not match upstream SHA1')
        part.replace(path)
        if path.suffix == '.zip':
            (SRC / 'download_manifest.json').write_text(json.dumps({
                'url': url, 'downloaded_utc': datetime.now(timezone.utc).isoformat(),
                'file': relative(path), 'bytes': n, 'sha256': sha256(path),
                'sha1': digest.hexdigest(), 'upstream_sha1': upstream_sha1,
            }, indent=2), encoding='utf-8')
    finally:
        if part.exists():
            part.unlink()


def check(tests, name, ok, detail='', severity='error'):
    tests.append({'test': name, 'status': 'PASS' if bool(ok) else ('WARN' if severity == 'warning' else 'FAIL'),
                  'detail': str(detail)})
    if not ok and severity == 'error':
        raise AssertionError(name + ': ' + str(detail))


def dict_row(table, variable, unit, definition):
    return {'table': table, 'variable': variable, 'unit': unit, 'definition': definition,
            'source_id': 'hydrobasins_v1c', 'observation_period': 'modern geomorphological model; technical release July 2014',
            'boundary_year': '1921 or 1930 according to geography'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', type=Path, default=BASE_DEFAULT)
    args = parser.parse_args()
    for d in [SRC, OUT, AUDIT, DOCS]:
        d.mkdir(parents=True, exist_ok=True)
    tests = []
    archive = SRC / 'hybas_eu_lev01-12_v1c.zip'
    fetch(URL, archive)
    metadata = json.loads((SRC / 'download_manifest.json').read_text()) if (SRC / 'download_manifest.json').exists() else {}
    check(tests, 'original_archive_sha256', metadata.get('sha256', sha256(archive)) == sha256(archive), sha256(archive))
    try:
        fetch(TECH_URL, SRC / 'HydroBASINS_TechDoc_v1c.pdf')
    except Exception as exc:
        logging.warning('Technical documentation download unavailable: %s', exc)
    extracted = SRC / 'extracted'
    extracted.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        # Exact expected basenames only: do not extract paths supplied by a ZIP.
        for level in LEVELS:
            for ext in ['shp', 'shx', 'dbf', 'prj', 'shp.xml']:
                name = f'hybas_eu_lev{level:02d}_v1c.{ext}'
                if name in z.namelist() and not (extracted / name).exists():
                    (extracted / name).write_bytes(z.read(name))

    districts = {}
    districts_wgs = {}
    for layer in LAYERS:
        d = gpd.read_file(args.base, layer=layer)[['district_year_id', 'boundary_year', 'NAZEV', 'geometry']]
        check(tests, f'{layer}_unique_ids', d.district_year_id.is_unique)
        check(tests, f'{layer}_valid_geometry', d.geometry.notna().all() and d.is_valid.all() and not d.is_empty.any())
        districts_wgs[layer] = d.to_crs(4326)
        districts[layer] = d.to_crs(CRS)
    union = shapely.union_all(np.concatenate([x.geometry.values for x in districts.values()]))
    bbox = gpd.GeoSeries([union], crs=CRS).to_crs(4326).total_bounds
    # Use a bounding box only to fetch candidate polygons. Keep the complete,
    # unchanged polygons actually intersecting the study area (no clipping).
    master_gpkg = OUT / 'basins.gpkg'
    original_gpkg = OUT / 'hydrobasins_region_original.gpkg'
    for p in [master_gpkg, original_gpkg]:
        if p.exists():
            p.unlink()
    summaries, links_all, topology_all, source_reports, dictionary, repairs = [], [], [], [], [], []
    all_source_metadata = []
    for level in LEVELS:
        logging.info('Loading level %02d', level)
        sourcefile = extracted / f'hybas_eu_lev{level:02d}_v1c.shp'
        topology = pyogrio.read_dataframe(sourcefile, read_geometry=False)
        check(tests, f'L{level:02d}_europe_unique_ids', topology.HYBAS_ID.is_unique)
        id_fields = ['HYBAS_ID', 'NEXT_DOWN', 'NEXT_SINK', 'MAIN_BAS', 'PFAF_ID']
        for f in id_fields:
            topology[f] = topology[f].astype('int64')
        all_ids = set(topology.HYBAS_ID)
        check(tests, f'L{level:02d}_downstream_ids_resolve', topology.NEXT_DOWN.isin(all_ids | {0}).all())
        check(tests, f'L{level:02d}_main_basin_ids_resolve', topology.MAIN_BAS.isin(all_ids | {0}).all())
        topology['hybas_level'] = level
        topology_all.append(topology)

        source = gpd.read_file(sourcefile, bbox=tuple(bbox)).to_crs(4326)
        check(tests, f'L{level:02d}_source_geometry_present', source.geometry.notna().all() and not source.is_empty.any())
        original = source.copy()
        invalid_mask = ~source.is_valid
        invalid_before = int(invalid_mask.sum())
        source['source_geometry_repaired'] = invalid_mask.astype(int)
        if invalid_before:
            for idx in source.index[invalid_mask]:
                before = source.geometry.loc[idx]
                after = shapely.make_valid(before)
                repairs.append({'hybas_level': level, 'HYBAS_ID': int(source.loc[idx, 'HYBAS_ID']),
                                'reason': shapely.is_valid_reason(before),
                                'repair': 'shapely.make_valid on original source polygon',
                                'before_type': before.geom_type, 'after_type': after.geom_type,
                                'area_change_square_degrees': shapely.area(after) - shapely.area(before)})
                source.loc[idx, 'geometry'] = after
        projected = source.to_crs(CRS)
        selected = shapely.intersects(projected.geometry.values, union)
        original = original.loc[selected].copy().reset_index(drop=True)
        source = source.loc[selected].copy().reset_index(drop=True)
        projected = projected.loc[selected].copy().reset_index(drop=True)
        for f in id_fields:
            source[f] = source[f].astype('int64')
            projected[f] = projected[f].astype('int64')
        check(tests, f'L{level:02d}_selected_source_geometry_valid', source.is_valid.all() and projected.is_valid.all())
        source['hybas_level'] = level
        source['next_down_in_regional_subset'] = source.NEXT_DOWN.isin(set(source.HYBAS_ID)).astype(int)
        layername = f'hydrobasins_l{level:02d}_region'
        original.to_file(original_gpkg, layer=layername, driver='GPKG', index=False)
        source.to_file(master_gpkg, layer=layername, driver='GPKG', index=False)
        source.drop(columns='geometry').assign(source_layer=layername).pipe(all_source_metadata.append)

        projected['basin_polygon_area_km2'] = projected.area / 1e6
        keep = id_fields + ['SUB_AREA', 'UP_AREA', 'basin_polygon_area_km2', 'geometry']
        for layer in LAYERS:
            d = districts[layer]
            logging.info('Intersecting %s level %02d (%d basins)', layer, level, len(source))
            intersections = gpd.overlay(d[['district_year_id', 'boundary_year', 'geometry']],
                                        projected[keep], how='intersection', keep_geom_type=False)
            intersections['intersection_area_km2'] = intersections.area / 1e6
            intersections = intersections.loc[intersections.intersection_area_km2 > 0].copy()
            district_area = d.set_index('district_year_id').area / 1e6
            intersections['district_area_km2'] = intersections.district_year_id.map(district_area)
            intersections['district_area_share'] = intersections.intersection_area_km2 / intersections.district_area_km2
            intersections['fraction_of_basin_polygon_in_district'] = intersections.intersection_area_km2 / intersections.basin_polygon_area_km2
            intersections['geography'] = layer
            intersections['hybas_level'] = level
            # GeoPackage keeps original basin polygons; intersections are exposed
            # as an auditable table with the exact clipping areas.
            tab = pd.DataFrame(intersections.drop(columns='geometry'))
            tab = tab[['geography', 'district_year_id', 'boundary_year', 'hybas_level'] +
                      id_fields + ['SUB_AREA', 'UP_AREA', 'intersection_area_km2',
                                   'district_area_km2', 'district_area_share', 'basin_polygon_area_km2',
                                   'fraction_of_basin_polygon_in_district']]
            check(tests, f'{layer}_L{level:02d}_link_unique', not tab.duplicated(['district_year_id', 'HYBAS_ID']).any())
            check(tests, f'{layer}_L{level:02d}_link_areas_positive', (tab.intersection_area_km2 > 0).all())
            links_all.append(tab)
            lookup = tab.groupby('district_year_id')
            rows = []
            for row in d.itertuples():
                did = row.district_year_id
                t = lookup.get_group(did) if did in lookup.groups else tab.iloc[:0]
                area = float(district_area.loc[did])
                cov = float(t.intersection_area_km2.sum() / area)
                if len(t):
                    ranked = t.sort_values(['intersection_area_km2', 'HYBAS_ID'], ascending=[False, True])
                    top = ranked.iloc[0]
                    by_main = t.groupby('MAIN_BAS').intersection_area_km2.sum().sort_values(ascending=False)
                    dominant_id = str(int(top.HYBAS_ID))
                    dominant_main = str(int(by_main.index[0]))
                    dominant_share = float(top.district_area_share)
                    main_share = float(by_main.iloc[0] / area)
                else:
                    dominant_id = dominant_main = None
                    dominant_share = main_share = np.nan
                rows.append({'geography': layer, 'district_year_id': did, 'boundary_year': int(row.boundary_year),
                             'hybas_level': level, 'basin_source_coverage_fraction': cov,
                             'n_intersecting_basins': len(t), 'dominant_hybas_id': dominant_id,
                             'dominant_basin_area_share': dominant_share, 'n_main_basins': t.MAIN_BAS.nunique(),
                             'dominant_main_basin_id': dominant_main, 'dominant_main_basin_area_share': main_share})
            summary = pd.DataFrame(rows)
            check(tests, f'{layer}_L{level:02d}_all_districts_preserved', len(summary) == len(d))
            check(tests, f'{layer}_L{level:02d}_coverage_finite', np.isfinite(summary.basin_source_coverage_fraction).all())
            check(tests, f'{layer}_L{level:02d}_no_overlap_excess', (summary.basin_source_coverage_fraction <= 1 + 1e-6).all(),
                  f'max={summary.basin_source_coverage_fraction.max():.12f}')
            check(tests, f'{layer}_L{level:02d}_coverage_99pct', (summary.basin_source_coverage_fraction >= .99).all(),
                  f'min={summary.basin_source_coverage_fraction.min():.12f}', severity='warning')
            # Independently compare the summed clip area to a union, including
            # the most fragmented district and the lowest-coverage district.
            validation_ids = list(dict.fromkeys([
                summary.loc[summary.n_intersecting_basins.idxmax(), 'district_year_id'],
                summary.loc[summary.basin_source_coverage_fraction.idxmin(), 'district_year_id'],
            ]))
            for did in validation_ids:
                parts = intersections.loc[intersections.district_year_id == did].geometry.values
                summed = float(shapely.area(parts).sum())
                merged = float(shapely.area(shapely.union_all(parts)))
                check(tests, f'{layer}_L{level:02d}_union_area_{did}', abs(summed - merged) < max(1, summed * 1e-7),
                      f'sum_m2={summed}; union_m2={merged}')
            summaries.append(summary)
        source_reports.append({'level': level, 'source_features_europe': len(topology),
                               'regional_features': len(source), 'layer': layername,
                               'invalid_source_candidates_repaired': invalid_before,
                               'invalid_regional_geometries_repaired': int(source.source_geometry_repaired.sum()),
                               'original_geometry_file': relative(original_gpkg),
                               'subset_rule': 'whole basin polygons with any intersection with union of all four historical district layers',
                               'source_parts_sha256': {p.name: sha256(p) for p in extracted.glob(f'hybas_eu_lev{level:02d}_v1c.*')},
                               'regional_bounds_wgs84': source.total_bounds.tolist()})

    summaries = pd.concat(summaries, ignore_index=True)
    links = pd.concat(links_all, ignore_index=True)
    topology = pd.concat(topology_all, ignore_index=True)
    source_metadata = pd.concat(all_source_metadata, ignore_index=True)
    summaries.to_csv(OUT / 'gis_basins.csv', index=False, float_format='%.12g')
    links.to_csv(OUT / 'basin_district_links.csv.gz', index=False, float_format='%.12g', compression='gzip')
    topology.to_csv(OUT / 'hydrobasins_topology_europe.csv.gz', index=False, compression='gzip')
    source_metadata.to_csv(OUT / 'hydrobasins_source_metadata.csv', index=False)
    static = summaries[['geography', 'district_year_id', 'boundary_year']].drop_duplicates().copy()
    for level in LEVELS:
        t = summaries.loc[summaries.hybas_level == level].drop(columns=['boundary_year', 'hybas_level']).copy()
        renames = {c: f'basin_l{level:02d}_{c}' for c in t.columns if c not in ['geography', 'district_year_id']}
        renames['basin_source_coverage_fraction'] = f'basin_l{level:02d}_coverage_fraction'
        t.rename(columns=renames, inplace=True)
        static = static.merge(t, on=['geography', 'district_year_id'], validate='one_to_one')
    static['basins_source_status'] = 'complete_actual_source'
    static.to_csv(OUT / 'gis_basins_static.csv', index=False, float_format='%.12g')
    check(tests, 'all_geographies_preserved', len(static) == sum(len(x) for x in districts.values()))
    with sqlite3.connect(master_gpkg) as con:
        for tablename, df in [('gis_basins', summaries), ('gis_basins_static', static),
                              ('gis_basin_district_links', links), ('gis_basin_source_metadata', source_metadata)]:
            df.to_sql(tablename, con, index=False, if_exists='replace')
            con.execute('INSERT OR REPLACE INTO gpkg_contents(table_name,data_type,identifier,description,last_change) VALUES(?,?,?,?,?)',
                        (tablename, 'attributes', tablename, 'HydroBASINS v1c district integration', datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')))
        check(tests, 'geopackage_integrity', con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok')
    definitions = {
        'geography': ('identifier', 'Historical district geography: judicial/political and boundary year.'),
        'district_year_id': ('identifier', 'Stable district key, joined without changing historical geometry.'),
        'boundary_year': ('year', 'Year of the district boundaries; not the date of the basin model.'),
        'hybas_level': ('level', 'HydroBASINS hierarchy level: 6, 8 or 12.'),
        'basin_source_coverage_fraction': ('fraction of district area', 'Sum of basin intersection areas / full district polygon area in EPSG:3035; uncovered areas are retained, not renormalized.'),
        'n_intersecting_basins': ('count', 'Number of different HYBAS_ID polygons with positive area inside the district.'),
        'dominant_hybas_id': ('identifier', 'HYBAS_ID having the largest clipped area in the district; ties resolved by ascending ID.'),
        'dominant_basin_area_share': ('fraction of district area', 'Largest basin intersection area / full district area.'),
        'n_main_basins': ('count', 'Number of distinct source MAIN_BAS identifiers among intersecting basin polygons.'),
        'dominant_main_basin_id': ('identifier', 'MAIN_BAS with the largest combined intersection area in the district.'),
        'dominant_main_basin_area_share': ('fraction of district area', 'Largest summed MAIN_BAS intersection area / full district area.'),
        'HYBAS_ID': ('identifier', 'Original HydroBASINS unique sub-basin ID, preserved as integer in source; use as an identifier.'),
        'NEXT_DOWN': ('identifier', 'Source ID of next downstream basin; 0 at outlet. Target can be outside archived regional geometry.'),
        'NEXT_SINK': ('identifier', 'Source next sink basin ID. See HydroBASINS documentation for virtual links.'),
        'MAIN_BAS': ('identifier', 'Source most downstream basin ID for the corresponding major river basin at this level.'),
        'PFAF_ID': ('identifier', 'Original hierarchical Pfafstetter code.'),
        'SUB_AREA': ('km2', 'Original source sub-basin area attribute, not recalculated polygon area.'),
        'UP_AREA': ('km2', 'Original source upstream area attribute; no historical runoff is inferred.'),
        'DIST_SINK': ('km', 'Source network distance from the basin outlet to its next downstream sink.'),
        'DIST_MAIN': ('km', 'Source network distance from the basin outlet to its major-basin outlet; virtual endorheic links count as zero distance.'),
        'ENDO': ('code', 'Source endorheic status: 0 outside an endorheic basin, 1 within one, 2 its terminal sink.'),
        'COAST': ('flag', 'Source flag for a grouping of small coastal watersheds: 1 yes, 0 no.'),
        'ORDER': ('order', 'Source classical river order: main stem 1, its tributaries 2, etc.; 0 for grouped coastal catchments. This is not Strahler order.'),
        'SORT': ('ordinal', 'Original source record ordering from downstream to upstream.'),
        'source_geometry_repaired': ('flag', '1 if this analytical polygon required make_valid; unchanged original geometry is separately archived.'),
        'next_down_in_regional_subset': ('flag', '1 if NEXT_DOWN resolves to an archived regional polygon at the same level; 0 otherwise, including terminal NEXT_DOWN=0.'),
        'source_layer': ('layer name', 'GeoPackage layer containing this level of regional basin polygons.'),
        'intersection_area_km2': ('km2', 'Area of the exact basin/district intersection calculated in EPSG:3035.'),
        'district_area_km2': ('km2', 'Area of the full historical district polygon calculated in EPSG:3035.'),
        'district_area_share': ('fraction of district area', 'Intersection area divided by full district polygon area.'),
        'basin_polygon_area_km2': ('km2', 'Area of whole basin geometry calculated in EPSG:3035; different from source SUB_AREA.'),
        'fraction_of_basin_polygon_in_district': ('fraction of basin area', 'Intersection area divided by full basin polygon area, both EPSG:3035.'),
    }
    for table, df in [('gis_basins', summaries), ('gis_basin_district_links', links),
                      ('gis_basin_source_metadata', source_metadata), ('hydrobasins_topology_europe', topology)]:
        for col in df:
            unit, definition = definitions.get(col, ('source attribute', 'Original HydroBASINS attribute; see source technical documentation.'))
            dictionary.append(dict_row(table, col, unit, definition))
    for col in static:
        if col in definitions:
            unit, definition = definitions[col]
        elif col == 'basins_source_status':
            unit, definition = 'status', 'complete_actual_source: calculations completed from original HydroBASINS v1c polygons; does not imply historical observations.'
        else:
            prefix = col[:10]
            basecol = col[10:]
            if basecol == 'coverage_fraction':
                basecol = 'basin_source_coverage_fraction'
            unit, definition = definitions[basecol]
            definition = f'At hierarchy level {int(col[7:9])}: ' + definition
        dictionary.append(dict_row('gis_basins_static', col, unit, definition))
    pd.DataFrame(dictionary).to_csv(OUT / 'dictionary.csv', index=False)
    pd.DataFrame(tests).to_csv(AUDIT / 'basins_validation.csv', index=False)
    pd.DataFrame(repairs, columns=['hybas_level', 'HYBAS_ID', 'reason', 'repair', 'before_type', 'after_type', 'area_change_square_degrees']).to_csv(AUDIT / 'basins_geometry_repairs.csv', index=False)
    counts = pd.Series([x['status'] for x in tests]).value_counts().to_dict()
    manifest = {
        'module': 'basins', 'status': 'complete_actual_source', 'dataset': 'HydroBASINS v1c standard Europe',
        'built_utc': datetime.now(timezone.utc).isoformat(), 'base_geopackage': str(args.base.resolve()),
        'base_sha256': sha256(args.base), 'source_url': URL, 'product_url': PRODUCT_URL,
        'source_archive_sha256': sha256(archive), 'source_archive_bytes': archive.stat().st_size,
        'source_archive_in_release': False,
        'source_archive_omission_reason': 'Full European 12-level archive is cached locally; hydrobasins_region_original.gpkg preserves whole original regional polygons. basins.gpkg contains the same polygons with explicit logged make_valid repairs where required. Full Europe topology of selected levels, metadata and reproducible script are archived.',
        'levels': LEVELS, 'crs_area': 'EPSG:3035', 'geographies': {k: len(v) for k, v in districts.items()},
        'temporal_interpretation': 'Modern topographic catchment model; technical release July 2014. No historical flood, flow, river engineering, or navigability observations.',
        'licence': 'HydroSHEDS licence agreement; scientific, educational and commercial use permitted under source terms; see technical documentation and product page.',
        'citation': 'Lehner, B. and Grill, G. (2013), Hydrological Processes 27(15), 2171–2186, doi:10.1002/hyp.9740.',
        'technical_documentation_url': TECH_URL,
        'source_layers': source_reports, 'validation': counts,
        'output_files': [{ 'path': relative(p), 'bytes': p.stat().st_size, 'sha256': sha256(p)} for p in sorted(OUT.iterdir()) if p.is_file() and p.name != 'manifest.json'],
        'environment': {'python': platform.python_version(), 'geopandas': gpd.__version__, 'shapely': shapely.__version__, 'pyogrio': pyogrio.__version__},
        'limitations': ['Polygon source boundaries are derived from a 15 arc-second model; polygon overlays do not increase source resolution.',
                       'The archived regional geometry keeps whole intersecting basins but is not a complete upstream/downstream network. Full European topology is provided separately; source polygon download is required for off-region geometry.',
                       'HydroBASINS provides identifiers, not authoritative historical names of river basins.',
                       'The political_1921 layer retains its pre-existing incomplete area coverage.'],
    }
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    (AUDIT / 'basins_validation_summary.json').write_text(json.dumps(counts, indent=2), encoding='utf-8')
    doc = '''# Povodí HydroBASINS — skutečné připojení ve v0.6

Použit byl původní evropský archiv HydroBASINS v1c, standardní varianta, zveřejněný poskytovatelem. Jeho velikost a SHA256 jsou v manifestu. Zpracovány jsou hierarchické úrovně 6, 8 a 12 pro všechny čtyři původní správní vrstvy.

## Výpočet

Původní polygony povodí se protínají s historickými okresy. Plochy se počítají v rovnoplošném systému EPSG:3035. Okresní podíl je plocha skutečného průniku dělená plochou celého okresu, nikoli celou plochou povodí. Jmenovatel se nezmenšuje podle dostupnosti zdroje; pokrytí je samostatný ukazatel. Dominantní povodí má největší podíl plochy. Vazby MAIN_BAS, NEXT_DOWN, NEXT_SINK a Pfafstetterovy kódy jsou zachované ze zdroje.

Polygony v hydrobasins_region_original.gpkg jsou celé původní zdrojové polygony, které zasahují některý z našich okresů; jejich souřadnice ani atributy nejsou upravené. basins.gpkg obsahuje analytickou kopii, ve které se případné neplatné geometrie opravují funkcí make_valid. Každá taková oprava je zaznamenána v audit/basins_geometry_repairs.csv a příznaku source_geometry_repaired. Polygony nejsou oříznuté na státní hranici. Tabulka basin_district_links.csv.gz zachovává všechny kladné plošné průniky a jejich váhy. hydrobasins_topology_europe.csv.gz obsahuje úplné evropské atributové tabulky vybraných úrovní; geometrie mimo region v balíčku není. Zde se nepočítají meteorologické ani hydrologické hodnoty za celé horní povodí.

V pracovním rozbalení nejsou použity nepovinné soubory prostorového indexu SBN/SBX, které instalovaný GDAL u původního zdroje odmítl. SHP/SHX/DBF/PRJ jsou z archivu převzaty beze změny. Tato volba nemění geometrii ani atributy.

## Význam období

Jde o moderní model hydrografie odvozený z výškových dat, dokumentace verze 1c z července 2014. Rok 1921/1930 označuje pouze hranice okresů. Údaje nejsou měřením meziválečných průtoků, povodní, splavnosti nebo tehdejších říčních úprav. Přesnost odpovídá zdrojovému modelu 15 obloukových sekund.

## Zdroj a licence

HydroBASINS: https://www.hydrosheds.org/products/hydrobasins

Technická dokumentace: https://data.hydrosheds.org/file/technical-documentation/HydroBASINS_TechDoc_v1c.pdf

Citace: Lehner, B., Grill, G. (2013). Global river hydrography and network routing: baseline data and new approaches to study the world's large river systems. Hydrological Processes 27(15), 2171–2186. DOI: 10.1002/hyp.9740.

Licence HydroSHEDS dovoluje vědecké, vzdělávací a komerční použití podle podmínek poskytovatele; nejde o data nově licencovaná licencí kódu R balíčku.
'''
    (DOCS / 'BASINS_METHODS_CZ.md').write_text(doc, encoding='utf-8')
    logging.info('HydroBASINS completed: %s; %d district-level rows, %d links', counts, len(summaries), len(links))


if __name__ == '__main__':
    main()
