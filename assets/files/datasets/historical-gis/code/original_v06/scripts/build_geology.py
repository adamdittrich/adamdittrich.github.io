#!/usr/bin/env python3
"""Integrate the CGS geological map 1:500,000 using actual vector features.

Source: official ArcGIS map layer 2, CGS_Bedrock_Geology / GM500 G JEDNOTKY.
Original Czech/English legend descriptions are retained. This script does not
invent broad lithology groups or interpret contemporary geology as a 1930
survey. Full district area is always the denominator of composition shares.
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
PROJECT = ROOT.parent
BASE_DEFAULT = (ROOT / 'inputs/base_v05_inputs.gpkg' if (ROOT / 'inputs/base_v05_inputs.gpkg').exists()
                else PROJECT / 'gis_work/GIS_v04_Preparation/outputs/wave2_completed/historical_gis_czech_lands_v05.gpkg')
SRC = ROOT / 'sources/geology'
OUT = ROOT / 'modules/geology'
AUDIT = ROOT / 'audit'
DOCS = ROOT / 'docs'
LAYER_URL = 'https://mapy.geology.cz/arcgis/rest/services/Projekty/CGS_Bedrock_Geology/MapServer/2'
PRODUCT_URL = 'https://cgs.gov.cz/en/maps-and-data/provision-of-data'
LICENCE_URL = 'https://cgs.gov.cz/en/copyright'
LAYERS = ['judicial_1930', 'judicial_1921', 'political_1930', 'political_1921']
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


def check(tests, name, ok, detail='', severity='error'):
    tests.append({'test': name, 'status': 'PASS' if bool(ok) else ('WARN' if severity == 'warning' else 'FAIL'), 'detail': str(detail)})
    if not ok and severity == 'error':
        raise AssertionError(name + ': ' + str(detail))


def request_json(url, params):
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=(30, 90))
            r.raise_for_status()
            d = r.json()
            if 'error' in d:
                raise ValueError(str(d['error']))
            return r, d
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2)


def acquire():
    p = SRC / 'geology_source.geojson'
    if p.exists():
        return p
    r, m = request_json(LAYER_URL, {'f': 'pjson'})
    (SRC / 'layer_metadata.json').write_bytes(r.content)
    r, info = request_json(LAYER_URL + '/query', {'where': '1=1', 'returnIdsOnly': 'true', 'f': 'json'})
    (SRC / 'source_ids.json').write_bytes(r.content)
    ids = sorted(info['objectIds'])
    chunks = [ids[i:i+350] for i in range(0, len(ids), 350)]

    def one_chunk(pair):
        i, values = pair
        # An objectIds list with hundreds of IDs exceeds this server's GET URL
        # length limit. A short range predicate returns the same enumerated IDs.
        params = {'where': f'objectid >= {values[0]} AND objectid <= {values[-1]}',
                  'outFields': '*', 'outSR': 4326, 'returnGeometry': 'true', 'f': 'geojson'}
        rr, d = request_json(LAYER_URL + '/query', params)
        if d.get('exceededTransferLimit') or len(d.get('features', [])) != len(values):
            raise ValueError(f'Incomplete source page {i}')
        if set(f['properties']['objectid'] for f in d['features']) != set(values):
            raise ValueError(f'Wrong source IDs in page {i}')
        (SRC / f'page_{i:03}.geojson').write_bytes(rr.content)
        logging.info('Downloaded geology page %d: %d features', i, len(values))
        return i, d, rr.url

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        parts = list(pool.map(one_chunk, enumerate(chunks)))
    features = [feature for _, d, _ in sorted(parts) for feature in d['features']]
    if len(features) != len(ids):
        raise ValueError('Incomplete combined source data')
    p.write_text(json.dumps({'type': 'FeatureCollection', 'features': features}, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    manifest = {'source_url': LAYER_URL, 'query_endpoint': LAYER_URL + '/query',
                'query_parameters': {'where': 'objectid range covering full enumerated IDs, batches of 350',
                                     'outFields': '*', 'outSR': 4326, 'returnGeometry': 'true', 'f': 'geojson'},
                'downloaded_utc': datetime.now(timezone.utc).isoformat(), 'features': len(features),
                'bytes': p.stat().st_size, 'sha256': sha256(p),
                'queries': [{'page': i, 'url': u, 'features': len(d['features'])} for i, d, u in sorted(parts)]}
    (SRC / 'download_manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    return p


def polygon_only(g):
    if g.geom_type in ['Polygon', 'MultiPolygon']:
        return g
    pieces = []
    for part in shapely.get_parts(g):
        if part.geom_type in ['Polygon', 'MultiPolygon']:
            pieces.append(part)
        elif part.geom_type == 'GeometryCollection':
            nested = polygon_only(part)
            if not nested.is_empty:
                pieces.append(nested)
    return shapely.union_all(pieces)


def dictionary_row(table, variable, unit, definition):
    return {'table': table, 'variable': variable, 'unit': unit, 'definition': definition,
            'source_id': 'cgs_geological_map_500k_2007',
            'observation_period': 'geological map 2007, official vector service accessed 2026-11-03; not a historical land-use observation',
            'boundary_year': '1921 or 1930 according to geography'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', type=Path, default=BASE_DEFAULT)
    args = parser.parse_args()
    for d in [SRC, OUT, AUDIT, DOCS]:
        d.mkdir(parents=True, exist_ok=True)
    tests, repairs, summaries, all_links, compositions = [], [], [], [], []
    source_path = acquire()
    acquisition = json.loads((SRC / 'download_manifest.json').read_text())
    check(tests, 'source_sha256', sha256(source_path) == acquisition['sha256'])
    source_ids = sorted(json.loads((SRC / 'source_ids.json').read_text())['objectIds'])
    raw = gpd.read_file(source_path)
    check(tests, 'source_unique_objectids', raw.objectid.is_unique)
    check(tests, 'complete_source_id_enumeration', sorted(raw.objectid.tolist()) == source_ids)
    check(tests, 'source_geometries_present', raw.geometry.notna().all() and not raw.is_empty.any())
    check(tests, 'source_is_wgs84', raw.crs.to_epsg() == 4326)
    check(tests, 'source_legend_codes_present', raw.leg.notna().all())
    check(tests, 'source_legend_codes_integer', np.array_equal(raw.leg.to_numpy(), raw.leg.astype('int64').to_numpy()))
    check(tests, 'original_and_corrected_legend_codes_agree', (raw.leg == raw.leg_oprav).all())
    raw['objectid'] = raw.objectid.astype('int64')
    raw['leg'] = raw.leg.astype('int64')
    source = raw.copy()
    for c in ['hornina', 'rocks', 'stari', 'age', 'nadpis1', 'nadpis2', 'nadpis3', 'nadpis4', 'title1', 'title2', 'title3', 'title4', 'souvrstvi', 'formation', 'region', 'index_']:
        source[c] = source[c].astype('string').str.strip().replace('', pd.NA)
    # Complete source labels remain untouched in geology_source.geojson. Empty
    # string normalization above only creates the explicitly analytical copy.
    check(tests, 'legend_has_unique_czech_lithology', (source.groupby('leg').hornina.nunique(dropna=False) <= 1).all())
    check(tests, 'legend_has_unique_english_lithology', (source.groupby('leg').rocks.nunique(dropna=False) <= 1).all())
    original_projected = raw.to_crs(CRS)
    invalid = ~source.is_valid
    source['source_geometry_repaired'] = invalid.astype(int)
    for idx in source.index[invalid]:
        old = source.geometry.loc[idx]
        repaired = polygon_only(shapely.make_valid(old))
        if repaired.is_empty or not repaired.is_valid:
            raise ValueError(f'Cannot repair source objectid {source.loc[idx, "objectid"]}')
        source.loc[idx, 'geometry'] = repaired
        after_area = gpd.GeoSeries([repaired], crs=4326).to_crs(CRS).area.iloc[0]
        before_area = original_projected.geometry.loc[idx].area
        repairs.append({'source_objectid': int(source.loc[idx, 'objectid']),
                        'reason': shapely.is_valid_reason(old),
                        'repair': 'shapely.make_valid; polygonal components retained',
                        'before_type': old.geom_type, 'after_type': repaired.geom_type,
                        'before_area_m2_3035': before_area, 'after_area_m2_3035': after_area,
                        'area_change_fraction': (after_area - before_area) / before_area if before_area > 0 else np.nan})
    projected = source.to_crs(CRS)
    # Millimetre precision in the metric analysis CRS prevents numerical
    # slivers along nominally shared map edges. The untouched original export
    # and the unsnapped repaired source layer are retained separately.
    before_precision_area = projected.area.copy()
    projected.geometry = shapely.set_precision(projected.geometry.values, grid_size=0.001)
    precision_area_delta_m2 = projected.area - before_precision_area
    check(tests, 'analysis_precision_area_change_small',
          ((precision_area_delta_m2.abs() < 1) | (precision_area_delta_m2.abs() / before_precision_area < 1e-4)).all(),
          f'max_relative_change={(precision_area_delta_m2.abs() / before_precision_area).max():.12g}')
    check(tests, 'analytical_source_geometries_valid', source.is_valid.all() and projected.is_valid.all())
    check(tests, 'analytical_source_areas_positive', (projected.area > 0).all())
    repair_table = pd.DataFrame(repairs, columns=['source_objectid', 'reason', 'repair', 'before_type', 'after_type', 'before_area_m2_3035', 'after_area_m2_3035', 'area_change_fraction'])
    if len(repair_table):
        check(tests, 'repairs_small_area_change', (repair_table.area_change_fraction.abs() < 1e-4).all(),
              f'max absolute fraction={repair_table.area_change_fraction.abs().max():.12g}', severity='warning')
    logging.info('Union of %d geological features, %d repaired', len(source), int(invalid.sum()))
    coverage_geometry = shapely.union_all(projected.geometry.values)
    check(tests, 'source_union_valid', coverage_geometry.is_valid)

    # The original geological map contains small genuine polygon overlaps.
    # Merge overlaps within one legend class, but do not choose arbitrarily
    # between different LEG classes. Cross-class overlap is kept as an explicit
    # ambiguous area and excluded from the default classified composition.
    logging.info('Resolving source polygon overlaps without assigning conflicting labels')
    pairs = projected.sindex.query(projected.geometry, predicate='intersects')
    first, second = pairs[:, pairs[0] < pairs[1]]
    pair_geoms = shapely.intersection(projected.geometry.values[first], projected.geometry.values[second])
    pair_areas = shapely.area(pair_geoms)
    positive = pair_areas > 0
    first, second = first[positive], second[positive]
    pair_geoms, pair_areas = pair_geoms[positive], pair_areas[positive]
    different = projected.leg.to_numpy()[first] != projected.leg.to_numpy()[second]
    ambiguous_geometry = shapely.union_all(pair_geoms[different])
    source_overlap_table = pd.DataFrame({
        'source_objectid_a': projected.objectid.to_numpy()[first],
        'source_objectid_b': projected.objectid.to_numpy()[second],
        'legend_code_a': projected.leg.to_numpy()[first],
        'legend_code_b': projected.leg.to_numpy()[second],
        'overlap_area_m2_3035': pair_areas,
        'different_legend_categories': different.astype(int),
    })
    source_overlap_table.to_csv(AUDIT / 'geology_source_overlaps.csv.gz', index=False, compression='gzip', float_format='%.12g')
    classified_units = projected[['leg', 'geometry']].dissolve(by='leg').reset_index()
    # Use the same conflict union locally. Subtracting the country-wide union
    # from every detailed multipart unit is needlessly expensive. Every area
    # ambiguous for a LEG category occurs in a positive pair involving that
    # category, so these local differences are mathematically equivalent.
    conflicts_by_leg = {}
    for a, b, geom in zip(projected.leg.to_numpy()[first[different]],
                          projected.leg.to_numpy()[second[different]],
                          pair_geoms[different]):
        conflicts_by_leg.setdefault(int(a), []).append(geom)
        conflicts_by_leg.setdefault(int(b), []).append(geom)
    for idx, row in classified_units.iterrows():
        if int(row.leg) in conflicts_by_leg:
            conflict = shapely.union_all(conflicts_by_leg[int(row.leg)])
            classified_units.loc[idx, 'geometry'] = polygon_only(shapely.difference(row.geometry, conflict))
        if idx % 50 == 0:
            logging.info('Resolved geological category %d/%d', idx + 1, len(classified_units))
    classified_units = classified_units.loc[classified_units.area > 0].copy()
    check(tests, 'classified_geological_units_valid', classified_units.is_valid.all())
    source_overlay_residual_m2 = coverage_geometry.area - classified_units.area.sum() - ambiguous_geometry.area
    check(tests, 'classified_plus_ambiguous_equals_coverage_within_numeric_tolerance',
          abs(source_overlay_residual_m2) / coverage_geometry.area < 1e-7,
          f'residual_m2={source_overlay_residual_m2}; relative={source_overlay_residual_m2 / coverage_geometry.area}; tolerance_fraction=1e-7')

    gpkg = OUT / 'geology.gpkg'
    if gpkg.exists():
        gpkg.unlink()
    # These two source lengths/areas are in the source S-JTSK coordinate system;
    # name them explicitly so users do not confuse them with overlay measures.
    source.rename(columns={'st_area(shape)': 'source_area_m2_5514', 'st_length(shape)': 'source_perimeter_m_5514'}, inplace=True)
    source.to_file(gpkg, layer='geology_500k_source', driver='GPKG', index=False)
    classified_units.to_crs(4326).to_file(gpkg, layer='geology_unambiguous_legend_units', driver='GPKG', index=False)
    if not ambiguous_geometry.is_empty:
        gpd.GeoDataFrame({'meaning': ['area covered by two or more different source LEG classes'],
                          'area_km2_3035': [ambiguous_geometry.area / 1e6]},
                         geometry=[ambiguous_geometry], crs=CRS).to_crs(4326).to_file(
            gpkg, layer='geology_ambiguous_overlap', driver='GPKG', index=False)
    # REGION is a feature's location-specific setting; several regions share
    # the same original LEG category. Keep REGION in source features, not as
    # part of a supposedly one-to-one legend table.
    legend_columns = ['leg', 'hornina', 'rocks', 'stari', 'age', 'nadpis1', 'nadpis2', 'nadpis3', 'nadpis4',
                      'title1', 'title2', 'title3', 'title4', 'souvrstvi', 'formation', 'index_']
    legend = source[legend_columns].drop_duplicates().sort_values('leg').reset_index(drop=True)
    check(tests, 'legend_codes_unique', legend.leg.is_unique)
    legend.rename(columns={'leg': 'geology_legend_code', 'hornina': 'lithology_cz', 'rocks': 'lithology_en',
                           'stari': 'geologic_age_cz', 'age': 'geologic_age_en'}, inplace=True)
    legend.to_csv(OUT / 'geology_legend.csv', index=False)
    lithology_labels = source[['hornina', 'rocks']].drop_duplicates()
    # Some Czech rock descriptions recur in several map units with different
    # English translations. Preserve every original variant as a JSON list;
    # do not silently select or translate one of them.
    english_labels = lithology_labels.groupby('hornina', dropna=False).rocks.apply(
        lambda x: json.dumps(sorted(set(x.dropna().tolist())), ensure_ascii=False)).to_dict()
    label_catalogue = pd.DataFrame([{'lithology_cz': k, 'lithology_en_variants': v}
                                    for k, v in english_labels.items()])
    label_catalogue.to_csv(OUT / 'geology_lithology_labels.csv', index=False)
    # Spatially index individual pieces rather than bounding boxes of 315
    # country-wide multipart categories, to keep district overlays efficient.
    classified_pieces = classified_units.explode(index_parts=False).reset_index(drop=True)
    classified_pieces = classified_pieces.loc[classified_pieces.area > 0].copy()
    ambiguous_pieces = gpd.GeoDataFrame(geometry=[g for g in shapely.get_parts(ambiguous_geometry) if g.area > 0], crs=CRS)
    ambiguous_pieces = ambiguous_pieces.explode(index_parts=False).reset_index(drop=True)
    all_geo_reports = []

    for layer in LAYERS:
        d = gpd.read_file(args.base, layer=layer)[['district_year_id', 'boundary_year', 'geometry']].to_crs(CRS)
        check(tests, f'{layer}_district_keys_unique', d.district_year_id.is_unique)
        check(tests, f'{layer}_district_geometry_valid', d.is_valid.all() and not d.is_empty.any())
        district_area = d.set_index('district_year_id').area / 1e6
        logging.info('Intersecting geology with %s', layer)
        intersects = gpd.overlay(d, projected[['objectid', 'leg', 'hornina', 'rocks', 'geometry']],
                                 how='intersection', keep_geom_type=False)
        intersects['intersection_area_km2'] = intersects.area / 1e6
        intersects = intersects.loc[intersects.intersection_area_km2 > 0].copy()
        intersects['district_area_share'] = intersects.intersection_area_km2 / intersects.district_year_id.map(district_area)
        intersects['geography'] = layer
        tab = pd.DataFrame(intersects.drop(columns='geometry')).rename(columns={
            'objectid': 'source_objectid', 'leg': 'geology_legend_code', 'hornina': 'lithology_cz', 'rocks': 'lithology_en'})
        tab = tab[['geography', 'district_year_id', 'boundary_year', 'source_objectid', 'geology_legend_code',
                   'lithology_cz', 'lithology_en', 'intersection_area_km2', 'district_area_share']]
        check(tests, f'{layer}_source_feature_links_unique', not tab.duplicated(['district_year_id', 'source_objectid']).any())
        check(tests, f'{layer}_link_areas_positive', (tab.intersection_area_km2 > 0).all())
        check(tests, f'{layer}_link_shares_bounded', tab.district_area_share.between(0, 1 + 1e-7).all())
        all_links.append(tab)
        logging.info('Intersecting %d unambiguous pieces with %s', len(classified_pieces), layer)
        classified_intersections = gpd.overlay(d, classified_pieces, how='intersection', keep_geom_type=False)
        classified_intersections['intersection_area_km2'] = classified_intersections.area / 1e6
        classified_intersections = classified_intersections.loc[classified_intersections.intersection_area_km2 > 0].copy()
        classified_intersections['district_area_share'] = classified_intersections.intersection_area_km2 / classified_intersections.district_year_id.map(district_area)
        classified_intersections['geography'] = layer
        comp = pd.DataFrame(classified_intersections.drop(columns='geometry')).rename(columns={'leg': 'geology_legend_code'})
        comp = comp.groupby(['geography', 'district_year_id', 'boundary_year', 'geology_legend_code'], as_index=False)[['intersection_area_km2', 'district_area_share']].sum()
        raw_counts = tab.groupby(['district_year_id', 'geology_legend_code']).source_objectid.nunique().rename('n_source_polygons').reset_index()
        comp = comp.merge(raw_counts, on=['district_year_id', 'geology_legend_code'], how='left', validate='one_to_one')
        comp = comp.merge(legend[['geology_legend_code', 'lithology_cz', 'lithology_en', 'geologic_age_cz', 'geologic_age_en']],
                          on='geology_legend_code', how='left', validate='many_to_one')
        compositions.append(comp)
        logging.info('Computing union coverage for %s', layer)
        # Intersection distributes over union. Unite the already clipped
        # original features locally, instead of intersecting every district
        # with a country-wide multipart geometry containing all boundaries.
        covered_areas = intersects.groupby('district_year_id').geometry.apply(
            lambda x: shapely.union_all(x.values).area / 1e6).reindex(d.district_year_id).fillna(0)
        coverage = covered_areas / district_area
        if len(ambiguous_pieces):
            ambiguous_intersections = gpd.overlay(d, ambiguous_pieces, how='intersection', keep_geom_type=False)
            ambiguous_intersections['__area_km2'] = ambiguous_intersections.area / 1e6
            ambiguous_areas = ambiguous_intersections.groupby('district_year_id').__area_km2.sum().reindex(d.district_year_id).fillna(0)
            ambiguity = ambiguous_areas / district_area
        else:
            ambiguity = pd.Series(0.0, index=d.district_year_id)
        lookup = tab.groupby('district_year_id')
        classified_lookup = comp.groupby('district_year_id')
        rows = []
        for row in d.itertuples():
            did = row.district_year_id
            t = lookup.get_group(did) if did in lookup.groups else tab.iloc[:0]
            tc = classified_lookup.get_group(did) if did in classified_lookup.groups else comp.iloc[:0]
            fullarea = float(district_area.loc[did])
            sumfrac = float(t.intersection_area_km2.sum() / fullarea)
            cov = float(coverage.loc[did])
            if len(tc):
                unit_areas = tc.groupby('geology_legend_code').intersection_area_km2.sum().sort_values(ascending=False)
                # The original lithology strings can denote mixed rocks. This
                # is a share of map units with that label, not a pure mineral share.
                rock_areas = tc.groupby('lithology_cz', dropna=False).intersection_area_km2.sum().sort_values(ascending=False)
                topunit = str(int(unit_areas.index[0]))
                toprock = rock_areas.index[0]
                topunitshare = float(unit_areas.iloc[0] / fullarea)
                toprockshare = float(rock_areas.iloc[0] / fullarea)
                toprocken = english_labels.get(toprock)
            else:
                topunit = toprock = toprocken = None
                topunitshare = toprockshare = np.nan
            rows.append({'geography': layer, 'district_year_id': did, 'boundary_year': int(row.boundary_year),
                         'geology_coverage_fraction': cov, 'geology_unit_area_sum_fraction': sumfrac,
                         'geology_overlap_fraction': max(0.0, sumfrac - cov),
                         'geology_ambiguous_fraction': float(ambiguity.loc[did]),
                         'geology_unambiguous_coverage_fraction': float(tc.intersection_area_km2.sum() / fullarea),
                         'geology_overlay_residual_fraction': cov - float(ambiguity.loc[did]) - float(tc.intersection_area_km2.sum() / fullarea),
                         'geology_n_legend_units': tc.geology_legend_code.nunique(),
                         'geology_n_source_polygons': len(t),
                         'geology_dominant_legend_code': topunit,
                         'geology_dominant_legend_area_share': topunitshare,
                         'geology_dominant_lithology_cz': toprock,
                         'geology_dominant_lithology_en_variants': toprocken,
                         'geology_dominant_lithology_area_share': toprockshare,
                         'geology_source_status': 'complete_actual_source'})
        summary = pd.DataFrame(rows)
        check(tests, f'{layer}_all_districts_preserved', len(summary) == len(d))
        check(tests, f'{layer}_coverage_finite', np.isfinite(summary.geology_coverage_fraction).all())
        check(tests, f'{layer}_coverage_bounded', summary.geology_coverage_fraction.between(0, 1 + 1e-7).all())
        check(tests, f'{layer}_coverage_99pct', (summary.geology_coverage_fraction >= .99).all(),
              f'min={summary.geology_coverage_fraction.min():.12g}', severity='warning')
        check(tests, f'{layer}_overlap_below_0_01pct', (summary.geology_overlap_fraction <= 1e-4).all(),
              f'max={summary.geology_overlap_fraction.max():.12g}', severity='warning')
        check(tests, f'{layer}_dominant_share_bounded', summary.geology_dominant_lithology_area_share.dropna().between(0, 1 + 1e-7).all())
        # Verify table aggregation independently of the summary loop.
        unit_sums = comp.groupby('district_year_id').district_area_share.sum().reindex(summary.district_year_id).fillna(0)
        check(tests, f'{layer}_composition_equals_unambiguous_area', np.allclose(unit_sums.values, summary.geology_unambiguous_coverage_fraction, rtol=0, atol=1e-10))
        check(tests, f'{layer}_classified_plus_ambiguous_equals_coverage', np.allclose(
            summary.geology_unambiguous_coverage_fraction + summary.geology_ambiguous_fraction,
            summary.geology_coverage_fraction, rtol=0, atol=1e-6),
            f'max_absolute_residual_fraction={summary.geology_overlay_residual_fraction.abs().max()}; tolerance_fraction=1e-6')
        check(tests, f'{layer}_default_composition_never_exceeds_one', (unit_sums.values <= 1 + 1e-7).all())
        summaries.append(summary)
        all_geo_reports.append({'geography': layer, 'districts': len(d), 'links': len(tab), 'composition_rows': len(comp),
                                'minimum_coverage_fraction': float(summary.geology_coverage_fraction.min()),
                                'median_coverage_fraction': float(summary.geology_coverage_fraction.median()),
                                'maximum_overlap_fraction': float(summary.geology_overlap_fraction.max()),
                                'maximum_ambiguous_fraction': float(summary.geology_ambiguous_fraction.max()),
                                'maximum_absolute_overlay_residual_fraction': float(summary.geology_overlay_residual_fraction.abs().max()),
                                'districts_below_99pct_coverage': summary.loc[summary.geology_coverage_fraction < .99, 'district_year_id'].tolist()})

    summary = pd.concat(summaries, ignore_index=True)
    links = pd.concat(all_links, ignore_index=True)
    composition = pd.concat(compositions, ignore_index=True)
    summary.to_csv(OUT / 'gis_geology.csv', index=False, float_format='%.12g')
    links.to_csv(OUT / 'geology_district_links.csv.gz', index=False, compression='gzip', float_format='%.12g')
    composition.to_csv(OUT / 'geology_district_composition.csv.gz', index=False, compression='gzip', float_format='%.12g')
    repair_table.to_csv(AUDIT / 'geology_geometry_repairs.csv', index=False, float_format='%.12g')
    with sqlite3.connect(gpkg) as con:
        for tablename, df in [('gis_geology', summary), ('gis_geology_district_links', links),
                              ('gis_geology_composition', composition), ('gis_geology_legend', legend),
                              ('gis_geology_lithology_labels', label_catalogue)]:
            df.to_sql(tablename, con, index=False, if_exists='replace')
            con.execute('INSERT OR REPLACE INTO gpkg_contents(table_name,data_type,identifier,description,last_change) VALUES(?,?,?,?,?)',
                        (tablename, 'attributes', tablename, 'CGS geological map 1:500,000; historical district integration', datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')))
        check(tests, 'geopackage_integrity', con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok')
    defs = {
        'geography': ('identifier', 'Judicial or political geography and boundary year.'),
        'district_year_id': ('identifier', 'Stable key of the original historical district.'),
        'boundary_year': ('year', 'Year of the district boundaries, not the observation date of the geology map.'),
        'geology_coverage_fraction': ('fraction of district area', 'Union area of all source geological polygons inside the district divided by full district area in EPSG:3035. No renormalization for uncovered area.'),
        'geology_unit_area_sum_fraction': ('fraction of district area', 'Sum of source polygon intersection areas divided by full district area. Compare with coverage to diagnose overlaps.'),
        'geology_overlap_fraction': ('fraction of district area', 'Maximum of zero and summed unit areas minus their union coverage, divided by full district area.'),
        'geology_ambiguous_fraction': ('fraction of district area', 'Union area covered by two or more different source LEG categories / full district area. This area is explicitly excluded from classified compositions, not assigned arbitrarily.'),
        'geology_unambiguous_coverage_fraction': ('fraction of district area', 'Area covered by one unambiguous LEG class / full district area. Equals the sum of the default geological composition shares.'),
        'geology_overlay_residual_fraction': ('fraction of district area', 'Numerical residual: union coverage minus unambiguous class sum minus ambiguous overlap. Millimetre precision geometry operations are validated at absolute tolerance 1e-6 of district area. No rescaling or reassignment is applied to hide the residual.'),
        'geology_n_legend_units': ('count', 'Number of different original LEG categories with positive area in the district.'),
        'geology_n_source_polygons': ('count', 'Number of source objectid polygons intersecting the district by positive area; not a count of mines or deposits.'),
        'geology_dominant_legend_code': ('identifier', 'Original LEG code with the largest total area inside the district.'),
        'geology_dominant_legend_area_share': ('fraction of district area', 'Unambiguous area of dominant LEG / full district area. Polygons within the same LEG are united; overlap with other LEG classes is excluded.'),
        'geology_dominant_lithology_cz': ('original Czech label', 'Source HORNINA label covering the largest total area. Labels may describe mixed rocks.'),
        'geology_dominant_lithology_en_variants': ('JSON list of original English labels', 'Every original ROCKS label associated with the dominant Czech HORNINA label. Several LEG units can share a Czech label but have different English translations; all variants are retained.'),
        'geology_dominant_lithology_area_share': ('fraction of district area', 'Unambiguous area of map units with dominant HORNINA label / full district area; not the fraction of an individual mineral in mixed units.'),
        'geology_source_status': ('status', 'complete_actual_source means actual downloaded polygons were processed, not that every district has complete source coverage or a historical survey.'),
        'source_objectid': ('identifier', 'Original objectid of the official ArcGIS source feature.'),
        'geology_legend_code': ('identifier', 'Original LEG geological map legend category; LEG_OPRAV agrees in this source download.'),
        'lithology_cz': ('original Czech label', 'Original HORNINA description, only leading/trailing whitespace removed in analytical tables.'),
        'lithology_en': ('original English label', 'Original ROCKS description, only leading/trailing whitespace removed in analytical tables.'),
        'lithology_en_variants': ('JSON list of original English labels', 'All original English descriptions associated with a Czech rock label across source LEG categories.'),
        'geologic_age_cz': ('original Czech label', 'Original STARI description of geological age; not survey year.'),
        'geologic_age_en': ('original English label', 'Original AGE description of geological age; not survey year.'),
        'intersection_area_km2': ('km2', 'Area of geological polygon or map unit actually within a district; EPSG:3035.'),
        'district_area_share': ('fraction of district area', 'Intersection area / complete district area. Shares are not renormalized to available source coverage.'),
        'n_source_polygons': ('count', 'Number of separate source objectid polygons within this district/LEG combination.'),
    }
    dictionary = []
    for table, df in [('gis_geology', summary), ('gis_geology_district_links', links),
                      ('gis_geology_composition', composition), ('gis_geology_legend', legend),
                      ('gis_geology_lithology_labels', label_catalogue)]:
        for col in df:
            unit, definition = defs.get(col, ('original source label', f'Original geological legend field {col}; only outer whitespace normalized.'))
            if table == 'gis_geology_composition' and col in ['intersection_area_km2', 'district_area_share']:
                definition = 'Unambiguous LEG-class area inside the district, after uniting polygons within each LEG and excluding overlaps between different LEG categories. ' + ('Measured in EPSG:3035.' if col == 'intersection_area_km2' else 'Divided by full district area, with uncovered and ambiguous areas retained in the denominator.')
            dictionary.append(dictionary_row(table, col, unit, definition))
    pd.DataFrame(dictionary).to_csv(OUT / 'dictionary.csv', index=False)
    pd.DataFrame(tests).to_csv(AUDIT / 'geology_validation.csv', index=False)
    counts = pd.Series([x['status'] for x in tests]).value_counts().to_dict()
    (AUDIT / 'geology_validation_summary.json').write_text(json.dumps(counts, indent=2), encoding='utf-8')
    manifest = {
        'module': 'geology', 'status': 'complete_actual_source', 'source_id': 'cgs_geological_map_500k_2007',
        'dataset': 'CGS geological map of the Czech Republic 1:500,000 (2007), official vector layer GM500 G JEDNOTKY',
        'built_utc': datetime.now(timezone.utc).isoformat(), 'base_geopackage': str(args.base.resolve()),
        'base_sha256': sha256(args.base), 'source_url': LAYER_URL, 'product_url': PRODUCT_URL,
        'source_original_export': relative(source_path), 'source_sha256': sha256(source_path),
        'source_feature_count': len(raw), 'legend_categories': len(legend), 'lithology_labels': len(label_catalogue),
        'czech_english_lithology_label_pairs': len(lithology_labels),
        'source_metadata': relative(SRC / 'layer_metadata.json'),
        'source_download_manifest': relative(SRC / 'download_manifest.json'),
        'source_crs_export': 'EPSG:4326, transformed by official ArcGIS service from source EPSG:5514',
        'analysis_crs': 'EPSG:3035', 'map_scale_denominator': 500000, 'map_publication_year': 2007,
        'analysis_precision_grid_m': 0.001,
        'analysis_precision_max_feature_area_change_fraction': float((precision_area_delta_m2.abs() / before_precision_area).max()),
        'analysis_precision_max_feature_area_change_m2': float(precision_area_delta_m2.abs().max()),
        'geographies': all_geo_reports,
        'source_geometry_repairs': len(repair_table), 'geometry_repairs_log': relative(AUDIT / 'geology_geometry_repairs.csv'),
        'source_positive_overlap_pairs': len(source_overlap_table),
        'source_different_legend_overlap_pairs': int(different.sum()),
        'source_ambiguous_area_km2': float(ambiguous_geometry.area / 1e6),
        'source_overlay_residual_m2': float(source_overlay_residual_m2),
        'overlap_method': 'Union polygons within each original LEG class. Areas covered by different LEG classes are retained as explicit ambiguous area and excluded from default compositions. Raw feature links retain source overlaps for audit.',
        'licence_url': LICENCE_URL,
        'licence_note': 'Official CGS data; consult archived copyright page and source metadata. Do not substitute the software licence for source-data terms.',
        'temporal_interpretation': 'Modern geological map describing geological units; not measured economic activity, mines active in 1930, or historical soil/land use.',
        'classification': 'Original LEG categories and original HORNINA/ROCKS labels only; no unverified recoding into broad sedimentary/igneous/metamorphic groups.',
        'validation': counts,
        'output_files': [{'path': relative(p), 'bytes': p.stat().st_size, 'sha256': sha256(p)} for p in sorted(OUT.iterdir()) if p.is_file() and p.name != 'manifest.json'],
        'environment': {'python': platform.python_version(), 'geopandas': gpd.__version__, 'shapely': shapely.__version__},
        'limitations': ['Scale is 1:500,000; very small districts and detailed border intersections are sensitive to generalization.',
                       'Original map labels sometimes describe rock mixtures. Their area shares describe map categories, not pure rock or mineral fractions.',
                       'Missing source area is retained in the denominator and reported; no extrapolation or renormalization is used.',
                       'Only geology is added by this module; present-day mineral occurrence lists and historical mine activity are separate datasets.'],
    }
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    (DOCS / 'GEOLOGY_METHODS_CZ.md').write_text('''# Geologické mapové jednotky ČGS — v0.6

## Co je připojeno

Skutečná vektorová data oficiální služby České geologické služby: CGS_Bedrock_Geology, vrstva 2 „GM500 G JEDNOTKY“. Podklad představuje geologickou mapu České republiky 1 : 500 000 z roku 2007. Původní export se všemi atributy je v sources/geology/geology_source.geojson; původní metadata, soupis identifikátorů, adresy všech dotazů a kontrolní součty jsou uložené vedle něj. Byla vyžádána kompletní množina ID a shoda množiny byla ověřena po stažení všech dávek, takže limit serveru 1 000 prvků nezkrátil výsledek.

## Převod na okresy

Plošné průniky se počítají v EPSG:3035. Zachovávají se kódy původní legendy LEG a české/anglické popisy HORNINA a ROCKS. Jsou odstraněny pouze okrajové mezery; není vytvořeno vlastní nedoložené dělení hornin. LEG a opravené kódy LEG_OPRAV se v tomto zdroji shodují.

Okresní podíl je plocha konkrétní mapové jednotky uvnitř okresu dělená celou plochou okresu. Součet ploch se neškáluje na 100 % při neúplném pokrytí. Pokrytí je samostatně vypočteno jako sjednocení všech zdrojových polygonů.

Původní mapa obsahuje drobné překryvy polygonů. Polygony se stejným kódem LEG se nejprve sjednotí. Plocha překryvu mezi různými LEG se označí jako nejednoznačná a není svévolně přiřazena žádné z kategorií. Defaultní kompozice a dominantní horninové podíly používají pouze jednoznačně klasifikovanou plochu. Součet podílů kategorií plus nejednoznačná plocha odpovídá zdrojovému pokrytí v deklarované numerické toleranci. Nejednoznačná ani nepokrytá plocha se neodstraní ze jmenovatele. Samostatná pole geology_ambiguous_fraction a geology_unambiguous_coverage_fraction dovolují přesnost posoudit.

Geometrické operace používají v EPSG:3035 souřadnicovou přesnost 1 mm, aby nevznikaly nestabilní numerické proužky na sdílených hranách. Původní export i opravená zdrojová vrstva bez tohoto zaokrouhlení jsou uchovány. Změna plochy každého prvku musí být menší než 1 m² nebo 0,01 % jeho původní plochy. Úzké původní proužky o několika m² mohou mít relativně větší změnu, ale absolutně pod 1 m². Pole geology_overlay_residual_fraction uvádí numerický rozdíl mezi sjednoceným pokrytím, součtem klasifikovaných ploch a nejednoznačnou plochou. Kontrola připouští nejvýše 0,0001 procentního bodu plochy okresu; zbytek se nepřerozděluje ani neschovává přenormováním.

Tabulka geology_district_links.csv.gz zachovává původní jednotlivé zdrojové průniky včetně překryvů pro audit; její podíly proto mohou v součtu překročit 100 %. geology_district_composition.csv.gz obsahuje výchozí, vzájemně se nepřekrývající kompozice podle původní legendy; geology_legend.csv obsahuje popisy. Drobné překryvy jsou dohledatelné v audit/geology_source_overlaps.csv.gz a vrstvě geology_ambiguous_overlap.

Některé původní geometrie jsou neplatné. Analytická kopie je opravuje funkcí make_valid a zachovává plošné komponenty. Každá oprava včetně změny plochy je v audit/geology_geometry_repairs.csv; původní export zůstává nezměněný. Vrstva geology_500k_source v geology.gpkg je označená příznakem source_geometry_repaired.

## Interpretace

Jde o geologickou charakteristiku území, nikoli o mapu dolů v provozu roku 1930 nebo dobové měření zemědělské půdy. Rok 1921/1930 označuje pouze hranice okresu. Plocha kategorie s popisem směsi hornin není podílem jedné čisté horniny nebo minerálu. Měřítko 1 : 500 000 se přepočtem na malé okresy nezpřesňuje.

## Zdroje

Poskytovatel a mapový produkt: https://cgs.gov.cz/en/maps-and-data/provision-of-data

Vektorová služba: https://mapy.geology.cz/arcgis/rest/services/Projekty/CGS_Bedrock_Geology/MapServer/2

Podmínky poskytovatele: https://cgs.gov.cz/en/copyright

Mapová data mají podmínky svého poskytovatele, které jsou oddělené od licence našeho zpracovatelského kódu. Modul nepřidává dosud neověřenou databázi meziválečných dolů.
''', encoding='utf-8')
    logging.info('Geology completed: %s; %d district rows; %d links; %d composition rows', counts, len(summary), len(links), len(composition))


if __name__ == '__main__':
    main()
