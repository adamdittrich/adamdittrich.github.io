#!/usr/bin/env python3
"""Integrate the actual public CGS B/D/P/R inventory as a modern reference.

This module never interprets the contemporary registry or its current mining
status labels as evidence of mines operating in 1921 or 1930.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import logging
import platform
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
import shapely

ROOT = Path(__file__).resolve().parents[1]
BASE = (ROOT / 'inputs/base_v05_inputs.gpkg' if (ROOT / 'inputs/base_v05_inputs.gpkg').exists()
        else ROOT.parent / 'gis_work/GIS_v04_Preparation/outputs/wave2_completed/historical_gis_czech_lands_v05.gpkg')
SRC = ROOT / 'sources/minerals'
OUT = ROOT / 'modules/minerals'
AUDIT = ROOT / 'audit'
DOCS = ROOT / 'docs'
SOURCES = {
    'BPR': ('https://mapy.geology.cz/arcgis/rest/services/Suroviny/loziska_zdroje/MapServer/0', SRC),
    'D': ('https://mapy.geology.cz/arcgis/rest/services/Suroviny/Surovinovy_informacni_system/MapServer/13', SRC / 'registry_d'),
}
LAYERS = ['judicial_1930', 'judicial_1921', 'political_1930', 'political_1921']
CRS = 3035
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(2**20), b''):
            h.update(chunk)
    return h.hexdigest()


def relative(path):
    return str(Path(path).resolve().relative_to(ROOT))


def check(tests, name, ok, detail='', warning=False):
    tests.append({'test': name, 'status': 'PASS' if bool(ok) else ('WARN' if warning else 'FAIL'), 'detail': str(detail)})
    if not ok and not warning:
        pd.DataFrame(tests).to_csv(AUDIT / 'minerals_validation.csv', index=False)
        raise AssertionError(name + ': ' + str(detail))


def request_json(url, params):
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=(30, 90))
            r.raise_for_status()
            data = r.json()
            if 'error' in data:
                raise ValueError(str(data['error']))
            return r, data
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2)


def acquire(group, url, directory):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'minerals_source.geojson'
    if path.exists():
        return path
    r, _ = request_json(url, {'f': 'pjson'})
    (directory / 'layer_metadata.json').write_bytes(r.content)
    r, info = request_json(url + '/query', {'where': '1=1', 'returnIdsOnly': 'true', 'f': 'json'})
    (directory / 'source_ids.json').write_bytes(r.content)
    ids = sorted(info['objectIds'])
    chunks = [ids[i:i+300] for i in range(0, len(ids), 300)]

    def one(pair):
        i, values = pair
        r, data = request_json(url + '/query', {
            'where': f'objectid >= {values[0]} AND objectid <= {values[-1]}',
            'outFields': '*', 'outSR': 4326, 'returnGeometry': 'true', 'f': 'geojson'})
        if data.get('exceededTransferLimit') or {f['properties']['objectid'] for f in data['features']} != set(values):
            raise ValueError(f'Incomplete {group} source page {i}')
        (directory / f'page_{i:03}.geojson').write_bytes(r.content)
        return i, data, r.url

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        parts = list(pool.map(one, enumerate(chunks)))
    features = [f for _, data, _ in sorted(parts) for f in data['features']]
    path.write_text(json.dumps({'type': 'FeatureCollection', 'features': features}, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    manifest = {'source_url': url, 'query_endpoint': url + '/query',
                'downloaded_utc': datetime.now(timezone.utc).isoformat(),
                'features': len(features), 'bytes': path.stat().st_size, 'sha256': sha256(path),
                'queries': [{'page': i, 'url': u, 'features': len(d['features'])} for i, d, u in sorted(parts)]}
    (directory / 'download_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return path


def polygon_only(geom):
    if geom.geom_type in ['Polygon', 'MultiPolygon']:
        return geom
    polygons = []
    for part in shapely.get_parts(geom):
        if part.geom_type in ['Polygon', 'MultiPolygon']:
            polygons.append(part)
        elif part.geom_type == 'GeometryCollection':
            polygons.append(polygon_only(part))
    return shapely.union_all(polygons)


def nearest(points, deposits):
    """One deterministic nearest ID; explicitly retain all equal-distance IDs."""
    tree = shapely.STRtree(deposits.geometry.values)
    pairs, distances = tree.query_nearest(points.values, all_matches=True, return_distance=True)
    records = pd.DataFrame({'point_index': pairs[0], 'deposit_id': deposits.deposit_id.to_numpy()[pairs[1]],
                            'distance_km': distances / 1000})
    output = []
    for i, group in records.groupby('point_index', sort=True):
        ids = sorted(set(group.deposit_id.tolist()))
        output.append({'point_index': i, 'distance_km': float(group.distance_km.min()),
                       'nearest_deposit_id': ids[0], 'nearest_ids': json.dumps(ids), 'n_tied': len(ids)})
    return pd.DataFrame(output).set_index('point_index').reindex(range(len(points)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', type=Path, default=BASE)
    args = parser.parse_args()
    for directory in [SRC, OUT, AUDIT, DOCS]:
        directory.mkdir(parents=True, exist_ok=True)
    tests, source_frames, source_manifests, repairs = [], [], [], []
    for group, (url, directory) in SOURCES.items():
        path = acquire(group, url, directory)
        manifest = json.loads((directory / 'download_manifest.json').read_text())
        original_ids = sorted(json.loads((directory / 'source_ids.json').read_text())['objectIds'])
        frame = gpd.read_file(path)
        check(tests, f'{group}_source_hash', sha256(path) == manifest['sha256'])
        check(tests, f'{group}_complete_source_id_enumeration', sorted(frame.objectid.tolist()) == original_ids)
        check(tests, f'{group}_unique_source_objectids', frame.objectid.is_unique)
        check(tests, f'{group}_source_geometries_present', frame.geometry.notna().all() and not frame.is_empty.any())
        check(tests, f'{group}_wgs84_source', frame.crs.to_epsg() == 4326)
        frame['source_group'] = group
        for col in frame.columns:
            if col not in ['objectid', 'geometry']:
                frame[col] = frame[col].astype('string').str.strip().replace('', pd.NA)
        source_frames.append(frame)
        source_manifests.append({'group': group, 'source_url': url, 'path': relative(path),
                                 'bytes': path.stat().st_size, 'sha256': sha256(path),
                                 'features': len(frame), 'downloaded_utc': manifest['downloaded_utc'],
                                 'download_manifest': relative(directory / 'download_manifest.json')})
    source = gpd.GeoDataFrame(pd.concat(source_frames, ignore_index=True), crs=4326)
    check(tests, 'source_part_ids_unique', source.cislo_gf.is_unique)
    check(tests, 'deposit_ids_present', source.cis_loz.notna().all())
    source['registry_code'] = source.subregistr.str.slice(0, 1)
    check(tests, 'registry_scope_exactly_bdpr', set(source.registry_code) == {'B', 'D', 'P', 'R'})
    attrs = ['nazev_loz', 'surovina', 'subregistr', 'tezba', 'registry_code']
    for field in attrs:
        check(tests, f'deposit_{field}_consistent_across_parts',
              (source.groupby('cis_loz')[field].nunique(dropna=False) == 1).all())
    source['source_geometry_repaired'] = (~source.is_valid).astype(int)
    for i in source.index[~source.is_valid]:
        original = source.loc[i, 'geometry']
        fixed = polygon_only(shapely.make_valid(original))
        source.loc[i, 'geometry'] = fixed
        repairs.append({'source_group': source.loc[i, 'source_group'], 'source_objectid': int(source.loc[i, 'objectid']),
                        'deposit_id': source.loc[i, 'cis_loz'], 'reason': shapely.is_valid_reason(original),
                        'repair': 'make_valid, polygon components retained'})
    check(tests, 'analytical_source_geometries_valid', source.is_valid.all() and not source.is_empty.any())
    projected = source.to_crs(CRS)
    check(tests, 'analytical_source_positive_area', (projected.area > 0).all())
    # CIS_LOZ identifies a deposit/resource; CISLO_GF and objectid identify its
    # mapped parts. Count the deposit once even if multiple parts touch a district.
    deposits = projected[['cis_loz'] + attrs + ['geometry']].dissolve(by='cis_loz', as_index=False)
    deposits.rename(columns={'cis_loz': 'deposit_id', 'nazev_loz': 'deposit_name',
                             'surovina': 'mineral_description', 'subregistr': 'registry_label',
                             'tezba': 'mining_status_current_inventory'}, inplace=True)
    counts = source.groupby('cis_loz').size()
    deposits['source_part_count'] = deposits.deposit_id.map(counts).astype(int)
    deposits['deposit_area_km2'] = deposits.area / 1e6
    check(tests, 'dissolved_deposit_ids_unique', deposits.deposit_id.is_unique)
    check(tests, 'dissolved_deposit_geometries_valid', deposits.is_valid.all())
    check(tests, 'dissolved_deposit_part_count_reconciles', deposits.source_part_count.sum() == len(source))
    all_union = shapely.union_all(deposits.geometry.values)
    gpkg = OUT / 'minerals.gpkg'
    if gpkg.exists():
        gpkg.unlink()
    source.to_file(gpkg, layer='minerals_current_source_parts', driver='GPKG', index=False)
    deposits.to_crs(4326).to_file(gpkg, layer='minerals_current_deposits', driver='GPKG', index=False)
    inventory = pd.DataFrame(deposits.drop(columns='geometry'))
    inventory.to_csv(OUT / 'minerals_inventory.csv', index=False)
    summaries, links, categories, geography_reports = [], [], [], []
    reference_date = max(m['downloaded_utc'][:10] for m in source_manifests)

    for layer in LAYERS:
        logging.info('Integrating contemporary mineral inventory with %s', layer)
        districts = gpd.read_file(args.base, layer=layer)[['district_year_id', 'boundary_year', 'geometry']].to_crs(CRS)
        check(tests, f'{layer}_district_keys_unique', districts.district_year_id.is_unique)
        check(tests, f'{layer}_district_geometries_valid', districts.is_valid.all())
        fullarea = districts.set_index('district_year_id').area / 1e6
        overlap = gpd.overlay(districts, deposits, how='intersection', keep_geom_type=False)
        overlap['intersection_area_km2'] = overlap.area / 1e6
        overlap = overlap.loc[overlap.intersection_area_km2 > 0].copy()
        overlap['district_area_share'] = overlap.intersection_area_km2 / overlap.district_year_id.map(fullarea)
        overlap['geography'] = layer
        tab = pd.DataFrame(overlap[['geography', 'district_year_id', 'boundary_year', 'deposit_id',
                                   'registry_code', 'intersection_area_km2', 'district_area_share']])
        check(tests, f'{layer}_district_deposit_links_unique', not tab.duplicated(['district_year_id', 'deposit_id']).any())
        check(tests, f'{layer}_positive_link_areas', (tab.intersection_area_km2 > 0).all())
        check(tests, f'{layer}_link_shares_bounded', tab.district_area_share.between(0, 1+1e-8).all())
        links.append(tab)
        centroid = districts.geometry.centroid
        inside = districts.geometry.representative_point()
        centroid_nearest = nearest(centroid, deposits)
        interior_nearest = nearest(inside, deposits)
        # Distance is to the deposit/resource polygon, hence zero for a point
        # inside it. It is not distance to a mine entrance, works or settlement.
        check(tests, f'{layer}_centroid_nearest_distances_valid',
              np.isfinite(centroid_nearest.distance_km).all() and (centroid_nearest.distance_km >= 0).all())
        check(tests, f'{layer}_interior_nearest_distances_valid',
              np.isfinite(interior_nearest.distance_km).all() and (interior_nearest.distance_km >= 0).all())
        check(tests, f'{layer}_interior_points_inside', shapely.covers(districts.geometry.values, inside.values).all())
        lookup = overlap.groupby('district_year_id')
        rows = []
        for i, district in enumerate(districts.itertuples()):
            did = district.district_year_id
            subset = lookup.get_group(did) if did in lookup.groups else overlap.iloc[:0]
            union_area = float(shapely.union_all(subset.geometry.values).area / 1e6) if len(subset) else 0.0
            row = {'geography': layer, 'district_year_id': did, 'boundary_year': int(district.boundary_year),
                   'minerals_inventory_date': reference_date,
                   'minerals_current_n_deposits': int(len(subset)),
                   'minerals_current_footprint_km2': union_area,
                   'minerals_current_footprint_share': union_area / float(fullarea.loc[did]),
                   'minerals_current_sum_deposit_area_km2': float(subset.intersection_area_km2.sum()),
                   'minerals_current_overlap_excess_km2': max(0.0, float(subset.intersection_area_km2.sum()) - union_area),
                   'minerals_centroid_outside_district': int(not district.geometry.covers(centroid.iloc[i])),
                   'minerals_source_status': 'complete_actual_source_bdpr_modern_reference'}
            for code in ['B', 'D', 'P', 'R']:
                row[f'minerals_current_n_registry_{code.lower()}'] = int((subset.registry_code == code).sum())
            for name, data in [('centroid', centroid_nearest), ('interior', interior_nearest)]:
                item = data.iloc[i]
                row[f'minerals_current_{name}_distance_km'] = float(item.distance_km)
                row[f'minerals_current_{name}_nearest_id'] = str(item.nearest_deposit_id)
                row[f'minerals_current_{name}_nearest_ids'] = item.nearest_ids
                row[f'minerals_current_{name}_nearest_ties'] = int(item.n_tied)
            rows.append(row)
        summary = pd.DataFrame(rows)
        check(tests, f'{layer}_all_districts_preserved', len(summary) == len(districts))
        check(tests, f'{layer}_count_matches_unique_links', summary.minerals_current_n_deposits.sum() == len(tab))
        check(tests, f'{layer}_registry_counts_reconcile',
              (summary[[f'minerals_current_n_registry_{c}' for c in 'bdpr']].sum(axis=1) == summary.minerals_current_n_deposits).all())
        check(tests, f'{layer}_footprint_shares_bounded', summary.minerals_current_footprint_share.between(0, 1+1e-8).all())
        check(tests, f'{layer}_union_not_greater_than_sum',
              (summary.minerals_current_footprint_km2 <= summary.minerals_current_sum_deposit_area_km2 + 1e-8).all())
        # Independent distance verification against the national union.
        check(tests, f'{layer}_nearest_matches_union_distance', np.allclose(
            summary.minerals_current_centroid_distance_km.to_numpy(),
            shapely.distance(centroid.values, all_union) / 1000, rtol=0, atol=1e-8))
        summaries.append(summary)
        catrows = []
        dimensions = {'registry': 'registry_label', 'mineral_description': 'mineral_description',
                      'mining_status_current_inventory': 'mining_status_current_inventory'}
        for dimension, column in dimensions.items():
            for (did, label), group in overlap.groupby(['district_year_id', column], dropna=False):
                a = float(shapely.union_all(group.geometry.values).area / 1e6)
                catrows.append({'geography': layer, 'district_year_id': did,
                                'boundary_year': int(group.boundary_year.iloc[0]),
                                'category_dimension': dimension, 'category_label': label,
                                'n_deposits': len(group), 'union_area_km2': a,
                                'district_area_share': a / float(fullarea.loc[did]),
                                'inventory_date': reference_date})
        category = pd.DataFrame(catrows)
        for dimension in dimensions:
            check(tests, f'{layer}_{dimension}_counts_reconcile',
                  category.loc[category.category_dimension == dimension, 'n_deposits'].sum() == len(tab))
        categories.append(category)
        geography_reports.append({'geography': layer, 'districts': len(summary), 'district_deposit_links': len(tab),
                                  'districts_with_deposit_footprints': int((summary.minerals_current_n_deposits > 0).sum()),
                                  'maximum_footprint_share': float(summary.minerals_current_footprint_share.max())})
    summary = pd.concat(summaries, ignore_index=True)
    link = pd.concat(links, ignore_index=True)
    category = pd.concat(categories, ignore_index=True)
    summary.to_csv(OUT / 'gis_minerals.csv', index=False, float_format='%.12g')
    link.to_csv(OUT / 'minerals_district_links.csv.gz', index=False, compression='gzip', float_format='%.12g')
    category.to_csv(OUT / 'minerals_district_categories.csv.gz', index=False, compression='gzip', float_format='%.12g')
    tables = [('gis_minerals', summary), ('gis_minerals_district_links', link),
              ('gis_minerals_categories', category), ('gis_minerals_inventory', inventory)]
    with sqlite3.connect(gpkg) as con:
        for table, data in tables:
            data.to_sql(table, con, index=False, if_exists='replace')
            con.execute('INSERT OR REPLACE INTO gpkg_contents(table_name,data_type,identifier,description,last_change) VALUES(?,?,?,?,?)',
                        (table, 'attributes', table, 'Modern CGS B/D/P/R inventory joined to historical district boundaries',
                         datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')))
        check(tests, 'geopackage_integrity', con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok')
    definitions = {
        'geography': ('identifier', 'Historical geography and boundary year.'),
        'district_year_id': ('identifier', 'Stable original district key.'),
        'boundary_year': ('year', 'District boundary year; not the observation year of this inventory.'),
        'minerals_inventory_date': ('ISO date', 'Download date of the contemporary inventory, not a historical observation date or guaranteed last update date of each deposit.'),
        'minerals_current_n_deposits': ('count', 'Unique CIS_LOZ deposits/resources with positive polygon area inside the district. Source parts are dissolved by deposit ID.'),
        'minerals_current_footprint_km2': ('km2', 'Union footprint of the selected current B/D/P/R inventory inside the district, avoiding overlap double counting.'),
        'minerals_current_footprint_share': ('fraction of district area', 'Union inventory footprint / full district area, EPSG:3035. This is not mineral abundance, currently mined area, or 1930 mining land use.'),
        'minerals_current_sum_deposit_area_km2': ('km2', 'Sum of individual deposit intersection areas; overlapping deposits are counted separately here.'),
        'minerals_current_overlap_excess_km2': ('km2', 'Summed individual deposit areas minus their union footprint, bounded below at zero.'),
        'minerals_centroid_outside_district': ('0/1', '1 if the geometric EPSG:3035 district centroid lies outside its district.'),
        'minerals_source_status': ('status', 'Actual complete ID enumeration of the selected B/D/P/R public layers, modern reference only. Does not assert all mineral occurrences or historical workings are known.'),
        'deposit_id': ('identifier', 'Original CIS_LOZ identifier of a deposit/resource, preserved as a string.'),
        'deposit_name': ('original Czech text', 'Original NAZEV_LOZ, outer whitespace normalized.'),
        'mineral_description': ('original Czech text', 'Original SUROVINA string, including mixed commodity descriptions. No splitting or unverified recoding.'),
        'registry_code': ('B/D/P/R', 'First character of the original SUBREGISTR label.'),
        'registry_label': ('original Czech text', 'Original SUBREGISTR label.'),
        'mining_status_current_inventory': ('original Czech text', 'Current downloaded TEZBA label. Earlier/current mining labels have no historical dates and must not be assigned to 1930.'),
        'source_part_count': ('count', 'Number of source CISLO_GF polygon parts combined into this deposit.'),
        'deposit_area_km2': ('km2', 'Area of the full dissolved source deposit polygon in EPSG:3035.'),
        'intersection_area_km2': ('km2', 'Area of this deposit polygon inside the district; EPSG:3035.'),
        'district_area_share': ('fraction of district area', 'Individual deposit area or category union area inside district / full district area. Different deposits or categories can overlap and are not compositional shares.'),
        'category_dimension': ('registry/mineral_description/mining_status_current_inventory', 'Grouping dimension, preserving complete original source labels.'),
        'category_label': ('original Czech text', 'Original source label for this dimension; mineral mixtures are kept as one original label.'),
        'n_deposits': ('count', 'Unique deposit IDs intersecting district in this category. No row means zero deposits for that category in this selected inventory.'),
        'union_area_km2': ('km2', 'Union of category deposit footprints within district, EPSG:3035. Footprints may overlap other categories.'),
        'inventory_date': ('ISO date', 'Download date of contemporary reference inventory.'),
    }
    registry_definitions = {'b': 'B – výhradní ložisko', 'd': 'D – ložisko nevyhrazeného nerostu',
                            'p': 'P – předpokládané ložisko vyhrazeného nerostu', 'r': 'R – předpokládané ložisko nevyhrazeného nerostu'}
    for code, meaning in registry_definitions.items():
        definitions[f'minerals_current_n_registry_{code}'] = ('count', f'Unique deposit IDs in original registry {meaning}, with positive area inside district; contemporary inventory.')
    for point in ['centroid', 'interior']:
        description = 'geometric centroid' if point == 'centroid' else 'interior representative point'
        definitions[f'minerals_current_{point}_distance_km'] = ('km', f'Planar EPSG:3035 distance from district {description} to nearest B/D/P/R deposit polygon across the full Czech source inventory. Zero inside a deposit; not distance to a mine entrance or town.')
        definitions[f'minerals_current_{point}_nearest_id'] = ('identifier', 'Nearest deposit ID; lexicographically first ID if exact distance ties occur.')
        definitions[f'minerals_current_{point}_nearest_ids'] = ('JSON list of identifiers', 'All deposit IDs tied at the nearest distance; several polygons can contain a point.')
        definitions[f'minerals_current_{point}_nearest_ties'] = ('count', 'Number of deposit IDs at the nearest distance.')
    dictionary = []
    for table, frame in tables:
        for field in frame:
            unit, definition = definitions[field]
            dictionary.append({'table': table, 'variable': field, 'unit': unit, 'definition': definition,
                               'source_id': 'cgs_suris_current_bdpr', 'observation_period': reference_date + ' download; not 1921/1930',
                               'boundary_year': '1921/1930 according to geography'})
    pd.DataFrame(dictionary).to_csv(OUT / 'dictionary.csv', index=False)
    pd.DataFrame(repairs, columns=['source_group', 'source_objectid', 'deposit_id', 'reason', 'repair']).to_csv(AUDIT / 'minerals_geometry_repairs.csv', index=False)
    pd.DataFrame(tests).to_csv(AUDIT / 'minerals_validation.csv', index=False)
    validation = pd.Series([test['status'] for test in tests]).value_counts().to_dict()
    (AUDIT / 'minerals_validation_summary.json').write_text(json.dumps(validation, indent=2), encoding='utf-8')
    manifest = {'module': 'minerals', 'status': 'complete_actual_source_modern_reference',
                'source_id': 'cgs_suris_current_bdpr', 'built_utc': datetime.now(timezone.utc).isoformat(),
                'base_geopackage': str(args.base.resolve()), 'base_sha256': sha256(args.base),
                'source_downloads': source_manifests, 'source_parts': len(source), 'unique_deposits': len(deposits),
                'registry_deposit_counts': inventory.groupby('registry_code').size().to_dict(),
                'registry_part_counts': source.groupby('registry_code').size().to_dict(),
                'inventory_reference_date': reference_date, 'actual_record_update_dates': 'not provided by queried source layers',
                'scope': 'Selected official current registries B, D, P, R only. N/Q/U/V/Z and other SurIS objects are not included.',
                'analysis_crs': 'EPSG:3035', 'distance_method': 'Planar metric distance to polygon footprints from geometric centroid/interior representative point; not geodesic travel or mine-entrance distance.',
                'source_geometry_repairs': len(repairs), 'geographies': geography_reports,
                'validation': validation, 'licence_url': 'https://cgs.gov.cz/en/copyright',
                'licence_note': 'Official public CGS services; retain attribution and source-data terms. Source dataset permission is separate from the R/software licence; these REST exports are not automatically relicensed under MIT.',
                'initial_download_failures': [
                    {'url': 'https://od.geology.cz/loziska_zdroje_ner_sur.zip', 'http_status': 503, 'detail': 'upstream connection timeout; alternate official public REST queries succeeded'},
                    {'url': 'https://m4eu.geology.cz/m4eu/services/m4eu?service=WFS&version=2.0.0&request=GetCapabilities', 'http_status': 503, 'detail': 'upstream connection timeout; alternate official public REST queries succeeded'}],
                'limitations': ['Current inventory joined to historical boundaries; no historical operating mine counts or production volumes are inferred.',
                                'Inventory absence is not evidence that no mineral occurrence or historical mine existed.',
                                'Deposit polygons and different categories may overlap. Summary footprint uses a union; raw deposit links and category shares need not sum to one.',
                                'Source mineral descriptions can combine several commodities. Original labels are preserved intact.',
                                'The selected source covers the current Czech Republic; no systematic inventory of neighbouring-country deposits is included.'],
                'output_files': [{'path': relative(path), 'bytes': path.stat().st_size, 'sha256': sha256(path)}
                                 for path in sorted(OUT.iterdir()) if path.is_file() and path.name != 'manifest.json'],
                'environment': {'python': platform.python_version(), 'geopandas': gpd.__version__, 'shapely': shapely.__version__}}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    (DOCS / 'MINERALS_METHODS_CZ.md').write_text(f'''# Ložiska a prognózní zdroje ČGS — moderní referenční modul v0.6

## Připojená skutečná data

Veřejné služby České geologické služby poskytly úplnou enumeraci vybraných vrstev B/P/R a samostatné vrstvy D. Staženo a zkontrolováno {len(source):,} polygonových částí, které náležejí {len(deposits):,} unikátním identifikátorům CIS_LOZ. Stav stažení je {reference_date}; služba neposkytuje datum poslední aktualizace každého záznamu. Registr B znamená výhradní ložisko, D ložisko nevyhrazeného nerostu, P a R předpokládaná ložiska/prognózní zdroje vyhrazených a nevyhrazených nerostů. Jiné registry SurIS N/Q/U/V/Z tento modul nezahrnuje.

Zdroj B/P/R: {SOURCES['BPR'][0]}

Zdroj D: {SOURCES['D'][0]}

## Historická interpretace

Jde o dnešní evidenci přepočtenou na hranice okresů 1921/1930. Sloupec TEZBA vyjadřuje původní kategorii evidence při stažení, například „současná povrchová“ nebo „dřívější hlubinná“. Není opatřen historickými daty a nelze z něj odvozovat činnost dolu za první republiky. Nulový počet znamená pouze nulový počet evidovaných polygonů vybraných registrů v tomto datasetu. Nevylučuje zaniklé či neevidované historické provozy. Nepřipojují se objemy těžby, pracovníci ani rok zahájení těžby.

## Výpočty a klíče

Všechny čtyři správní geografie zachovávají původní klíč `geography, district_year_id` a rok hranic `boundary_year`. Části stejného CIS_LOZ se nejprve spojí; ložisko je v okresu započítáno jednou, pokud má uvnitř polygonu kladnou plochu. Hraniční dotek bez plochy se nepočítá. Přeshraniční ložisko může patřit do více okresů. Sloupec `minerals_current_n_deposits` tedy není národně aditivním rozdělením ložisek.

Plochy jsou měřeny v EPSG:3035. Celková okresní plocha ložisek používá geometrickou unii, takže překrývající se ložiska se zde nezdvojují. Jednotlivé vazby a různé kategorie se překrývat mohou; jejich součet není složením do 100 %. Jmenovatelem podílů je celá plocha okresu. Kategorie zachovávají celé původní české texty SUROVINA, SUBREGISTR a TEZBA bez vymyšleného dělení nebo převodu surovin.

Vzdálenosti jsou přímé rovinné vzdálenosti v EPSG:3035 ke skutečnému polygonu ložiska, od geometrického centroidu a samostatně od bodu zaručeně uvnitř okresu. Bod uvnitř ložiska má vzdálenost nula. Při shodné nejbližší vzdálenosti jsou uchována všechna ID jako JSON; jednotlivé reprezentativní ID je první lexikograficky. Není to vzdálenost od okresního města, obyvatelstva, vchodu do dolu ani po dopravní síti. Výběr nejbližšího objektu používá celou českou zdrojovou vrstvu, včetně ložisek mimo daný okres; nezahrnuje soustavně sousední státy.

## Výstupy

- `gis_minerals`: 960 okresních řádků, počty, footprint, dvě vzdálenosti a diagnostika.
- `gis_minerals_district_links`: jedno ložisko × okres, klíč `geography, district_year_id, deposit_id`.
- `gis_minerals_categories`: původní kategorie podle okresů, klíč `geography, district_year_id, category_dimension, category_label`.
- `gis_minerals_inventory`: jedno ložisko, klíč `deposit_id`, původní názvy a popisy, počet zdrojových částí.
- `minerals_current_source_parts` a `minerals_current_deposits`: zdrojové části a spojené polygonové objekty v GeoPackage.

## Kontrola, původ a podmínky použití

Každá stažená stránka je ověřena proti úplnému seznamu zdrojových OBJECTID; nevydává se limitovaný serverový výsledek za úplný. Původní GeoJSON exporty, metadata a dotazy jsou archivovány pod `sources/minerals`. SHA256 zdrojů, výstupů a vstupního GIS jsou v manifestu. Ověřují se unikátní identifikátory, shoda názvů a kategorií mezi částmi, geometrie, počty, plošné unie a vzdálenosti nezávisle proti národní unii. Audit je v `audit/minerals_validation.csv` a slovník proměnných v `modules/minerals/dictionary.csv`.

Autor dat: Česká geologická služba. Podmínky zdrojů: https://cgs.gov.cz/en/copyright . Software licence R balíčku se automaticky nevztahuje na data ČGS; pro veřejnou distribuci se zachovají podmínky konkrétního zdroje a citace. Původní ZIP a WFS při tomto běhu vracely HTTP 503; úplná skutečná data byla získána uvedenými veřejnými službami ČGS.
''', encoding='utf-8')
    logging.info('Minerals complete: %s; %d deposits, %d district links', validation, len(deposits), len(link))
    print(json.dumps({'status': manifest['status'], 'source_parts': len(source), 'unique_deposits': len(deposits),
                      'districts': len(summary), 'district_links': len(link), 'category_rows': len(category),
                      'validation': validation}, indent=2))


if __name__ == '__main__':
    main()
