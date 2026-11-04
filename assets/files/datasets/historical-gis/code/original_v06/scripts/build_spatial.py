#!/usr/bin/env python3
"""Derive reproducible adjacency and point distances from the unchanged v0.5 boundaries."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import argparse
import sqlite3
import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
from scipy.spatial.distance import cdist

ROOT = Path(__file__).resolve().parents[1]
BASE = (ROOT / 'inputs/base_v05_inputs.gpkg' if (ROOT / 'inputs/base_v05_inputs.gpkg').exists()
        else ROOT.parent / 'gis_work/GIS_v04_Preparation/outputs/wave2_completed/historical_gis_czech_lands_v05.gpkg')
LAYERS = ['judicial_1930', 'judicial_1921', 'political_1930', 'political_1921']
OUT = ROOT / 'modules/spatial'


def atomic_csv(frame, path, compression=None):
    """Only promote a fully closed and readable export."""
    tmp = path.with_name(path.name + '.part')
    frame.to_csv(tmp, index=False, compression=compression)
    restored = pd.read_csv(tmp, compression=compression)
    assert len(restored) == len(frame) and list(restored) == list(frame)
    tmp.replace(path)


def export_distances_only():
    frames, checks = [], []
    with sqlite3.connect(BASE) as connection:
        for layer in LAYERS:
            g = pd.read_sql_query('SELECT district_year_id,centroid_lon,centroid_lat,interior_point_lon,interior_point_lat FROM "'+layer+'" ORDER BY district_year_id', connection)
            ids = g.district_year_id.to_numpy()
            points = gpd.GeoSeries(gpd.points_from_xy(g.centroid_lon,g.centroid_lat),crs=4326).to_crs(3035)
            inner = gpd.GeoSeries(gpd.points_from_xy(g.interior_point_lon,g.interior_point_lat),crs=4326).to_crs(3035)
            cd = cdist(np.c_[points.x,points.y],np.c_[points.x,points.y])/1000
            ip = cdist(np.c_[inner.x,inner.y],np.c_[inner.x,inner.y])/1000
            a,b = np.where(~np.eye(len(g),dtype=bool))
            d = pd.DataFrame(dict(geography=layer,district_year_id=ids[a],neighbor_district_year_id=ids[b],centroid_distance_km=cd[a,b],interior_point_distance_km=ip[a,b]))
            frames.append(d)
            checks.append(dict(geography=layer,check='all_nonself_ordered_pairs_exported',passed=len(d)==len(g)*(len(g)-1) and not d.duplicated(['district_year_id','neighbor_district_year_id']).any()))
            checks.append(dict(geography=layer,check='distances_positive_symmetric',passed=bool(np.all(cd[a,b]>0) and np.allclose(cd,cd.T) and np.allclose(ip,ip.T))))
    all_distances = pd.concat(frames,ignore_index=True)
    path = OUT/'gis_district_distances.csv.gz'
    atomic_csv(all_distances,path,compression='gzip')
    result = pd.DataFrame(checks)
    result.to_csv(ROOT/'audit/spatial_distance_export_validation.csv',index=False)
    assert result.passed.all()
    manifest = json.loads((OUT/'manifest.json').read_text())
    manifest['distance_rows_exported'] = len(all_distances)
    manifest['distance_export_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest['distance_export_verified_utc'] = datetime.now(timezone.utc).isoformat()
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    print(json.dumps({'distance_rows':len(all_distances),'validation_passed':len(checks),'gzip_complete':True}),flush=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    edges, distances, summaries, checks = [], [], [], []
    for layer in LAYERS:
        g = gpd.read_file(BASE, layer=layer).to_crs(3035).sort_values('district_year_id').reset_index(drop=True)
        ids = g.district_year_id.to_numpy()
        geom = g.geometry.to_numpy()
        bounds = shapely.boundary(geom)
        tree = shapely.STRtree(geom)
        pairs = tree.query(geom, predicate='intersects')
        records = []
        for i, j in zip(*pairs):
            if i >= j:
                continue
            common = bounds[i].intersection(bounds[j])
            shared = common.length
            overlap = geom[i].intersection(geom[j]).area
            queen = not common.is_empty
            rook = shared > 1.0
            if not queen and overlap <= 1e-6:
                continue
            records.append(dict(geography=layer, district_year_id=ids[i], neighbor_district_year_id=ids[j],
                                shared_boundary_km=shared / 1000, queen_contact=int(queen),
                                rook_contact=int(rook), overlap_area_m2=overlap,
                                topology_overlap_flag=int(overlap > 1.0)))
            records.append(dict(geography=layer, district_year_id=ids[j], neighbor_district_year_id=ids[i],
                                shared_boundary_km=shared / 1000, queen_contact=int(queen),
                                rook_contact=int(rook), overlap_area_m2=overlap,
                                topology_overlap_flag=int(overlap > 1.0)))
        e = pd.DataFrame(records)
        degree = e.groupby('district_year_id').rook_contact.sum().reindex(ids, fill_value=0)
        e['rook_row_standardized_weight'] = [1.0 / degree.loc[k] if r else 0.0
                                            for k, r in zip(e.district_year_id, e.rook_contact)]
        e = e.sort_values(['district_year_id', 'neighbor_district_year_id']).reset_index(drop=True)
        edges.append(e)
        centroid = gpd.GeoSeries(gpd.points_from_xy(g.centroid_lon, g.centroid_lat), crs=4326).to_crs(3035)
        interior = gpd.GeoSeries(gpd.points_from_xy(g.interior_point_lon, g.interior_point_lat), crs=4326).to_crs(3035)
        cd = cdist(np.c_[centroid.x, centroid.y], np.c_[centroid.x, centroid.y]) / 1000
        ip = cdist(np.c_[interior.x, interior.y], np.c_[interior.x, interior.y]) / 1000
        a, b = np.where(~np.eye(len(g), dtype=bool))
        distances.append(pd.DataFrame(dict(geography=layer, district_year_id=ids[a],
            neighbor_district_year_id=ids[b], centroid_distance_km=cd[a, b], interior_point_distance_km=ip[a, b])))
        s = g[['district_year_id']].copy()
        s.insert(0, 'geography', layer)
        s['spatial_rook_neighbors_n'] = s.district_year_id.map(degree).astype(int)
        q = e.groupby('district_year_id').queen_contact.sum()
        s['spatial_queen_neighbors_n'] = s.district_year_id.map(q).fillna(0).astype(int)
        o = e.groupby('district_year_id').topology_overlap_flag.sum()
        s['spatial_overlap_neighbors_n'] = s.district_year_id.map(o).fillna(0).astype(int)
        summaries.append(s)
        rev = e.rename(columns={'district_year_id': 'neighbor_district_year_id', 'neighbor_district_year_id': 'district_year_id'})
        rev = rev.sort_values(['district_year_id', 'neighbor_district_year_id']).reset_index(drop=True)
        w = e.groupby('district_year_id').rook_row_standardized_weight.sum()
        checks.extend([
            dict(geography=layer, check='symmetric_edges', passed=e[['district_year_id','neighbor_district_year_id','rook_contact','shared_boundary_km']].equals(rev[['district_year_id','neighbor_district_year_id','rook_contact','shared_boundary_km']])),
            dict(geography=layer, check='rook_weights_sum_to_one', passed=bool(np.allclose(w.reindex(degree[degree>0].index), 1))),
            dict(geography=layer, check='no_self_edges', passed=bool((e.district_year_id != e.neighbor_district_year_id).all())),
            dict(geography=layer, check='distances_positive_symmetric', passed=bool(np.all(cd[a,b]>0) and np.allclose(cd,cd.T) and np.allclose(ip,ip.T))),
            dict(geography=layer, check='all_districts_retained', passed=len(s)==len(g) and s.district_year_id.is_unique),
        ])
    atomic_csv(pd.concat(edges, ignore_index=True), OUT/'gis_neighbors.csv.gz', compression='gzip')
    atomic_csv(pd.concat(distances, ignore_index=True), OUT/'gis_district_distances.csv.gz', compression='gzip')
    atomic_csv(pd.concat(summaries, ignore_index=True), OUT/'gis_spatial_summary.csv')
    check = pd.DataFrame(checks)
    check.to_csv(ROOT/'audit/spatial_validation.csv', index=False)
    assert check.passed.all(), check[~check.passed].to_string()
    definitions = {
        'shared_boundary_km': ('km', 'Length of exactly shared polygon boundary in EPSG:3035; no snapping or gap bridging.'),
        'queen_contact': ('0/1', 'Boundaries have a nonempty intersection, including single-point contacts. Overlaps are separately flagged.'),
        'rook_contact': ('0/1', 'Exactly shared boundary length exceeds 1 metre; no adjacency inferred across gaps.'),
        'overlap_area_m2': ('m2', 'Area of intersection of original district polygons, EPSG:3035.'),
        'topology_overlap_flag': ('0/1', 'Original polygons overlap by more than 1 square metre; inspect before spatial modelling.'),
        'rook_row_standardized_weight': ('fraction', '1 / number of rook neighbours for a rook edge, otherwise 0; rows of non-isolates sum to 1.'),
        'centroid_distance_km': ('km', 'Straight-line projected EPSG:3035 distance between archived geometric centroids. Not travel time.'),
        'interior_point_distance_km': ('km', 'Straight-line projected EPSG:3035 distance between archived representative points. Not district seats.'),
        'spatial_rook_neighbors_n': ('count', 'Number of districts sharing more than 1 metre of exact boundary.'),
        'spatial_queen_neighbors_n': ('count', 'Number of districts whose boundaries intersect the district boundary.'),
        'spatial_overlap_neighbors_n': ('count', 'Number of districts with an original polygon overlap exceeding 1 square metre.'),
        'geography': ('identifier', 'Fixed historical boundary system.'),
        'district_year_id': ('identifier', 'Stable district identifier, including year of boundaries.'),
        'neighbor_district_year_id': ('identifier', 'Stable identifier of the other district in the same boundary system.'),
    }
    rows=[]
    for table,frame in [('gis_neighbors',pd.concat(edges)),('gis_district_distances',pd.concat(distances)),('gis_spatial_summary',pd.concat(summaries))]:
        for v in frame.columns:
            unit,definition=definitions[v]
            rows.append(dict(table=table,variable=v,unit=unit,definition=definition,period='fixed 1921 or 1930 boundaries',source='v0.5 original district geometry',notes='Alternative geography layers are not independent observations.'))
    pd.DataFrame(rows).to_csv(OUT/'dictionary.csv', index=False)
    meta = dict(module='spatial',status='complete',built_utc=datetime.now(timezone.utc).isoformat(),
                source='unchanged v0.5 historical district geometry',method_crs='EPSG:3035',
                definitions='Exact contiguity; rook threshold 1m; overlaps>1m2 flagged. Archived centroid/interior points, not district seats.',
                tables=[{'name':'gis_neighbors','file':'gis_neighbors.csv.gz','keys':['geography','district_year_id','neighbor_district_year_id']},
                        {'name':'gis_district_distances','file':'gis_district_distances.csv.gz','keys':['geography','district_year_id','neighbor_district_year_id']},
                        {'name':'gis_spatial_summary','file':'gis_spatial_summary.csv','keys':['geography','district_year_id']}],
                validation_passed=int(check.passed.sum()),validation_failed=int((~check.passed).sum()),
                topology_overlap_directed_edges=sum(int(e.topology_overlap_flag.sum()) for e in edges),
                rook_isolates=[s.loc[s.spatial_rook_neighbors_n==0,'district_year_id'].tolist() for s in summaries])
    (OUT/'manifest.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
    (ROOT/'docs/SPATIAL_METHODS_CZ.md').write_text('''# Sousednost a vzdálenosti okresů\n\nVstupem jsou nezměněné geometrie a referenční body v0.5. Výpočty probíhají v EPSG:3035. `rook_contact` vyžaduje přesně společnou hranici delší než jeden metr; `queen_contact` připouští bodový dotyk hranic. Hranice se neposouvají a malé mezery se automaticky nezacelují. Překryvy původních polygonů větší než 1 m² jsou samostatně označeny. Matice vah standardizuje každý řádek s alespoň jedním sousedem na součet jedna. Izolované okresy zůstávají ve shrnutí s nulovým počtem sousedů.\n\nTabulka vzdáleností obsahuje všechny uspořádané dvojice různých okresů v téže geografii. Jde o přímou vzdálenost mezi archivovanými geometrickými centroidy nebo vnitřními referenčními body. Tyto body nepředstavují okresní města ani těžiště obyvatelstva; vzdálenosti nejsou dopravními časy.\n\nNeúplná politická geometrie 1921 zůstává neúplná; její sousednost má stejné omezení jako vstup. Čtyři správní řezy se nesmějí sloučit jako nezávislá pozorování.\n''',encoding='utf-8')
    print(json.dumps(meta,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--distances-only',action='store_true')
    args=parser.parse_args()
    if args.distances_only:export_distances_only()
    else:main()
