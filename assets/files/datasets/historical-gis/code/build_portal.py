"""Build the public historical-GIS web explorer from documented release inputs.

No source measurements are invented. Browser metrics retain source periods,
denominators and conservative display masks. Use --help for input locations.
"""
from pathlib import Path
import argparse, json, shutil, sqlite3
import numpy as np
import pandas as pd
import geopandas as gpd
from PIL import Image

def jswrite(path,obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,allow_nan=False,separators=(',',':')),encoding='utf-8')

def clean(x):
    if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [clean(v) for v in x]
    if isinstance(x,(np.integer,)):return int(x)
    if isinstance(x,(np.bool_,)):return bool(x)
    if isinstance(x,(float,np.floating)):return None if not np.isfinite(x) else round(float(x),6)
    if pd.isna(x):return None
    return x

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--atlas-one',type=Path,required=True)
    p.add_argument('--atlas-two',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--rail-annual',type=Path)
    args=p.parse_args(); out=args.output;out.mkdir(parents=True,exist_ok=True)
    (out/'maps').mkdir(exist_ok=True);(out/'data').mkdir(exist_ok=True)
    master=pd.read_csv(args.source/'outputs/gis_master_judicial_1930_v06.csv').set_index('district_year_id')
    d=master.copy()
    for ap,fn in [(args.atlas_one,'atlas_values.csv'),(args.atlas_two,'atlas2_values.csv')]:
        a=pd.read_csv(ap/fn).set_index('district_year_id')
        d=pd.concat([d,a[[col for col in a if col not in d]]],axis=1)
    assert len(d)==330 and d.index.is_unique
    brno=d.index.isin(['CZ1930-J-30247','CZ1930-J-30245'])
    for col in ['sdp_1935_pct','ksc_1935_pct','ksc_change_1929_1935_pp_conservative','ksc_1929_pct_conservative']:
        d.loc[brno,col]=np.nan
    if args.rail_annual and args.rail_annual.exists():
        rail=pd.read_csv(args.rail_annual)
        for year in [1921,1930,1938]:
            r=rail[rail.geography.eq('judicial_1930') & rail.calendar_year.eq(year)].set_index('district_year_id')
            for col in r:
                if col+'_'+str(year) in d:
                    d[col+'_'+str(year)]=r[col]
        print('Browser rail metrics use corrected public chronology.')
    dic=pd.read_csv(args.source/'outputs/GIS_V06_DICTIONARY_judicial_1930.csv').fillna('')
    source_census='Historický GIS, Charles University · census 1930'
    source_climate='CRU-TS v4.10, Climatic Research Unit, University of East Anglia'
    source_rail='Ondřej Bedrunka, Palacký University (2023) · derived district statistics'
    metrics=[]
    def metric(key,label,unit,period,group,description,source,quality='',palette='teal',mult=1):
        assert key in d,key
        if mult!=1:d[key]=d[key]*mult
        values=pd.to_numeric(d[key],errors='raise')
        metrics.append(dict(key=key,label=label,unit=unit,period=period,group=group,
            description=description,source=source,quality_note=quality,palette=palette,
            min=float(values.min()),max=float(values.max()),coverage=int(values.notna().sum())))
    area='Historical census areas and GIS areas differ materially for Žacléř, Napajedla and Zlín; see district quality notes.'
    econ='Denominator: economically active population with a known sector. Vsetín and Vejprty withheld pending source verification.'
    climate='Area-weighted 0.5° grid: 60 cells underlie 330 districts; 82 districts occupy a single cell. These are not 330 independent station records.'
    metric('density_reported_1930','Population density','people / km²','1930','Population','Census population divided by the historical reported district area.',source_census,area)
    metric('population','Population','people','1930','Population','Total present population at the 1930 census.',source_census,area)
    metric('born_in_municipality_pct','Born in the local municipality','%','1930','Population','Share born in the municipality where enumerated, not merely somewhere in the district.',source_census)
    metric('children_0_14_pct','Children aged 0–14','%','1930','Population','Children aged 0–14 as a share of total population.',source_census)
    metric('elderly_65_plus_pct','People aged 65 and over','%','1930','Population','People aged 65+ as a share of total population.',source_census)
    metric('age_0_14_plus_65_per_100_age15_64_1930','Children and older people per 100 aged 15–64','people per 100','1930','Population','100 × (ages 0–14 plus ages 65+) / ages 15–64. Unknown age excluded.',source_census,'An age ratio, not dependants per employed worker.')
    metric('women_per_100_men_1930','Women per 100 men','women per 100 men','1930','Population','Present population of all ages.',source_census,'The ratio alone does not identify war losses or migration.')
    metric('widows_pct_all_women_1930','Widows among all women','%','1930','Population','Widowed women divided by all women, including children.',source_census,'A stock at the census, not annual widowhood risk or war-widow prevalence.')
    metric('widowers_pct_all_men_1930','Widowers among all men','%','1930','Population','Widowed men divided by all men, including children.',source_census)
    for key,label in [('german_nationality_pct','German nationality'),('polish_nationality_pct','Polish nationality'),('jewish_nationality_pct','Jewish nationality')]:
        metric(key,label,'%','1930','Nationality and religion','Share recorded in the corresponding census nationality category.',source_census,'Historical census nationality is distinct from religion and citizenship.')
    for key,label in [('roman_catholic_pct','Roman Catholic religion'),('evangelical_pct','Evangelical religions'),('czechoslovak_church_pct','Czechoslovak Church'),('no_religion_pct','No religious affiliation'),('jewish_religion_pct','Jewish religion')]:
        metric(key,label,'%','1930','Nationality and religion','Share of total population in the named census religious category.',source_census)
    metric('religion10_effective_categories_1930','Religious composition: effective categories','effective categories','1930','Nationality and religion','Inverse sum of squared shares across ten named census categories, including no religion; other/unknown excluded.',source_census,'Two equally large categories give 2. This is not an actual count of churches or a measure of tolerance.')
    for key,label in [('agriculture_pct_active_atlas','Agriculture'),('industry_pct_active_atlas','Industry and manufacturing crafts'),('tertiary_pct_active_atlas','Tertiary sector'),('transport_pct_active_atlas','Transport'),('forestry_pct_active_atlas','Forestry, hunting and fishing')]:
        metric(key,label,'% of known-sector active','1930','Employment','Employment share among economically active people with a known sector.',source_census,econ,palette='ochre')
    metric('econ_effective_branches8_1930','Employment diversity: effective branches','effective branches','1930','Employment','Inverse sum of squared employment shares across eight broad census branches.',source_census,econ+' Industry is one broad category; this is not within-industry diversity.',palette='ochre')
    for key,label in [('sdp_1935_pct','SdP vote share'),('ksc_1935_pct','KSČ vote share')]:
        metric(key,label,'% of valid votes','1935','Elections','Party votes divided by valid votes in the Chamber of Deputies election.', 'Czech Statistical Office · inherited district election panel','326 displayed: Praha-sever and Zlín missing; both Brno districts withheld pending territorial reconciliation.',palette='purple')
    metric('ksc_change_1929_1935_pp_conservative','Change in KSČ vote share','percentage points','1929–1935','Elections','1935 share minus 1929 share among conservatively matched districts.','Czech Statistical Office · audited election crosswalk','Unavailable or uncertain matches, including Brno, withheld. Aggregate change does not trace individual voters.',palette='diverging')
    metric('clim_normal_1901_1928_temp_mean_c','Mean annual temperature','°C','1901–1928 mean','Climate','Annual mean temperature averaged over 28 years.',source_climate,climate,palette='ochre')
    metric('clim_normal_1901_1928_precip_mm_year','Mean annual precipitation','mm / year','1901–1928 mean','Climate','Annual precipitation total averaged over 28 years.',source_climate,climate,palette='blue')
    metric('april_september_precip_1935_anomaly_pct','Growing-season rainfall anomaly, 1935','%','April–September 1935','Climate','100 × (seasonal precipitation / local 1901–1928 mean for the same months − 1).',source_climate,climate+' A precipitation deficit is not a measured crop loss.',palette='diverging')
    metric('july_minus_january_temperature_1901_1928_c','July–January temperature difference','°C','1901–1928 mean','Climate','Difference of long-run monthly mean temperatures; not daily extremes.',source_climate,climate,palette='ochre')
    metric('june_august_share_annual_precip_1901_1928_pct','Summer share of annual precipitation','%','1901–1928 mean','Climate','June–August mean precipitation sum divided by the annual mean sum.',source_climate,climate,palette='blue')
    metric('april_may_ground_frost_days_mean_1901_1928','Spring ground-frost days','days in April–May','1901–1928 mean','Climate','Mean sum of CRU FRS for April and May.',source_climate,'Empirically derived ground-frost frequency, not direct local event counts or the date of the last frost. '+climate,palette='blue')
    metric('mean_elevation_m','Mean terrain elevation','m above sea level','Modern terrain model','Terrain and water','Area average of the district terrain, not the altitude of its administrative town.','Copernicus DEM GLO-90','Geographic context; not an observation made in 1930.',palette='ochre')
    metric('river_density_km_per_100km2','Mapped river density','km / 100 km²','Modern HydroRIVERS network','Terrain and water','Total clipped river reach length divided by GIS district area.','HydroRIVERS / HydroSHEDS','Threshold-defined network excludes many small streams; not historical navigation or flow.',palette='blue')
    metric('mean_nearest_river_distance_km_1kmgrid','Mean distance to a mapped river','km','Modern HydroRIVERS network','Terrain and water','Average nearest-river distance from regular 1 km sample points within each district.','HydroRIVERS / HydroSHEDS','Area-sampled accessibility, not population-weighted distance or transport access.',palette='blue')
    metric('basin_l08_n_intersecting_basins','Intersecting level-8 drainage basins','basins','Modern HydroBASINS v1c','Terrain and water','Count of level-8 basin polygons intersecting the historical district.','HydroBASINS / HydroSHEDS','A topographic subdivision count, not rainfall or an interwar discharge observation.',palette='blue')
    metric('rail_operating_density_km_per_100km2_1930','Operating railway density','km / 100 km²','1930','Transport and borders','Length of the spatial union of operating tracks inside the district divided by GIS area.',source_rail,'Corrected Horní Lideč–Púchov opening: 1937. Poříčany–Nymburk lacks source geometry; source coverage is present-day Czechia.',palette='ochre')
    metric('rail_distance_interior_to_track_km_1930','Distance to operating railway','km','1930','Transport and borders','Straight-line distance from a district interior point to the nearest operating track.',source_rail,'Distance to track, not a railway station or population-weighted access. Cross-border source truncation may matter.',palette='ochre')
    metric('border_dist_interior_km_1930','Distance to the Czechoslovak state border','km','1 January 1930','Transport and borders','Distance from a district interior point to the external Czechoslovak border.','CShapes 2.0 / ETH Zürich','Generalised historical boundaries; interior point is not the district town.',palette='purple')
    metric('landuse_forest_1845_area_allocated_share','Forest share, 1845','%','1845 source slice','Land and soils','Forest area allocated from harmonised LUCC units by polygon overlap, divided by allocated total area.','LUCC Czechia, Ivan Bičík and colleagues, Charles University','Areal estimate; 1845 represents a cadastral source slice, approximately surveys of 1826–1843.',mult=100)
    metric('landuse_forest_1948_area_allocated_share','Forest share, 1948','%','1948 source slice','Land and soils','Area-allocated forest share on fixed district boundaries.','LUCC Czechia, Charles University','Postwar reference slice. Not an observation of land use in 1930.',mult=100)
    metric('forest_change_1845_1948_pp','Change in forest share, 1845–1948','percentage points','1845–1948','Land and soils','1948 forest share minus 1845 forest share on fixed 1930 boundaries.','LUCC Czechia, Charles University','Long-run context including years before and after the republic; cannot isolate the interwar change.',palette='diverging')
    metric('soil_clay_0_30cm_pct_atlas','Clay content, 0–30 cm','mass % of fine earth','Modern SoilGrids 2.0','Land and soils','Depth-thickness and area-weighted clay fraction in valid soil cells.','ISRIC SoilGrids 2.0','37 districts below 90% texture coverage withheld. Modern model, not 1930 fertility or yield.',palette='ochre')
    d['soil_ph_water_display']=d.soil_ph_water_0_30cm.mask(d.soil_phh2o_0_30cm_coverage_fraction.lt(.9))
    metric('soil_ph_water_display','Soil pH in water, 0–30 cm','pH','Modern SoilGrids 2.0','Land and soils','Depth-thickness and area-weighted descriptive mean pH in valid soil cells.','ISRIC SoilGrids 2.0','Coverage below 90% withheld. A modern descriptive arithmetic average, not a historical soil measurement.',palette='ochre')
    metric('geology_dominant_legend_area_share','Share of the dominant geological map unit','%','Geological map, 2007','Geology and minerals','District share assigned to its largest source legend category.','Czech Geological Survey, map 1:500,000','Category composition and mixed lithology descriptions remain in the downloadable tables; scale is not parcel precision.',mult=100)
    metric('minerals_current_n_deposits','Registered mineral deposits and resources','records','Registry snapshot: 3 November 2026','Geology and minerals','Distinct current register records intersecting the historical district.','Czech Geological Survey, B/D/P/R inventories','Modern register. Does not identify active interwar mines, output or historical employment.',palette='ochre')
    metric('gazetteer_reference_locality_code_count','Historical gazetteer locality codes','distinct codes','Mixed-period CZ_RETRO','Settlements and spatial links','Distinct referenced locality codes assigned to each district polygon.','Karel Kuča / SOVAMM, CZ_RETRO via NPÚ','Mixed historical and current references; not the number of active municipalities in 1930.')
    metric('spatial_rook_neighbors_n','Neighbours sharing a boundary segment','districts','Fixed 1930 geography','Settlements and spatial links','Rook neighbours: districts sharing a line, excluding point-only contact.','Own calculation from Historický GIS district geometries','Use supplied weights and distance tables for spatial analyses, with boundary-quality flags.')
    core_keys=[m['key'] for m in metrics if m['group']!='Climate']
    climate_keys=[m['key'] for m in metrics if m['group']=='Climate']
    d[core_keys].reset_index().to_csv(out/'data/explorer_values.csv',index=False)
    d[climate_keys].reset_index().to_csv(out/'data/climate_explorer_values.csv',index=False)
    geo=gpd.read_file(args.atlas_two/'inputs/district_boundaries_display_1930.geojson').to_crs(3035).set_index('district_year_id')
    minx,miny,maxx,maxy=geo.total_bounds
    width=1200;pad=22;scale=(width-2*pad)/(maxx-minx);height=(maxy-miny)*scale+2*pad
    def ring_path(ring):
        pts=[((x-minx)*scale+pad,(maxy-y)*scale+pad) for x,y,*_ in ring.coords]
        return 'M'+'L'.join(f'{x:.2f},{y:.2f}' for x,y in pts)+'Z'
    def svg_path(shape):
        polys=[shape] if shape.geom_type=='Polygon' else list(shape.geoms)
        return ''.join(ring_path(p.exterior)+''.join(ring_path(r) for r in p.interiors) for p in polys)
    districts=[]
    for id,row in d.iterrows():
        shape=geo.loc[id].geometry
        pt=shape.representative_point()
        flags=[]
        if bool(row.get('area_mismatch_gt10pct_and_gt5km2',False)):flags.append(area)
        if bool(row.get('economic_record_awaits_source_verification',False)):flags.append('Economic source counts await verification; derived employment previews withheld.')
        if id in ['CZ1930-J-30247','CZ1930-J-30245']:flags.append('Election territory does not yet reconcile with the judicial district; vote previews withheld.')
        districts.append(dict(id=id,name=row.NAZEV,path=svg_path(shape),x=round((pt.x-minx)*scale+pad,2),y=round((maxy-pt.y)*scale+pad,2),flags=flags,values=clean({m['key']:row[m['key']] for m in metrics})))
    con=sqlite3.connect('file:'+str(args.source/'outputs/historical_gis_czech_lands_v06.gpkg')+'?mode=ro',uri=True)
    annual=pd.read_sql_query("SELECT * FROM gis_climate_annual WHERE geography='judicial_1930' ORDER BY district_year_id,calendar_year",con)
    con.close()
    ametrics=[dict(key='precip_mm',label='Annual precipitation',unit='mm / year',description='Annual sum of monthly precipitation.'),dict(key='temp_mean_c',label='Annual mean temperature',unit='°C',description='Annual aggregate of monthly mean temperatures.'),dict(key='growing_season_precip_mm',label='April–September precipitation',unit='mm',description='Sum of six growing-season monthly totals.'),dict(key='growing_season_temp_mean_c',label='April–September temperature',unit='°C',description='Growing-season aggregate of monthly mean temperatures.'),dict(key='frost_days',label='Modelled ground-frost frequency',unit='days / year',description='CRU empirical ground-frost frequency; not directly observed local events.')]
    series={id:clean({m['key']:g[m['key']].tolist() for m in ametrics}) for id,g in annual.groupby('district_year_id',sort=False)}
    for id,vals in series.items():assert all(len(v)==38 for v in vals.values()),id
    climate_values={x['id']:{k:x['values'].pop(k) for k in climate_keys} for x in districts}
    climate_obj=dict(version='0.6.1',values=climate_values,annual=dict(years=list(range(1901,1939)),metrics=ametrics,districts=series,source=source_climate,quality_note=climate),source=source_climate,license='ODbL 1.0; Database Contents License for database contents',license_url='https://opendatacommons.org/licenses/odbl/1-0/',terms_url='https://crudata.uea.ac.uk/cru/data/hrg/')
    jswrite(out/'climate_explorer.json',clean(climate_obj))
    obj=dict(version='0.6.1',date='2026-11-04',sourceMasterFields=462,defaultMetric='density_reported_1930',defaultDistrict='CZ1930-J-30102',viewBox=[0,0,width,round(height,2)],metrics=metrics,districts=districts)
    jswrite(out/'explorer.json',clean(obj))
    dictionary=[]
    for row in dic.to_dict('records'):
        key=row['variable'];valid=330 if key=='district_year_id' else master[key].notna().sum()
        destination='climate_normals_judicial_1930.csv' if row['group']=='climate' else 'gis_master_judicial_1930_public_v061.csv'
        dictionary.append(dict(name=key,label=row['description'],group=row['group'],unit=row['unit'],period=row['period'],source=row['source'],description=row['description'],coverage=f'{valid}/330 non-missing source records',quality_note=row['notes'],public_file=destination))
    jswrite(out/'dictionary.json',dictionary)
    annual.to_csv(out/'data/climate_annual_judicial_1930.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    pd.DataFrame([{k:v for k,v in x.items() if k not in ['path','values','flags']} for x in districts]).to_csv(out/'data/district_index.csv',index=False)
    print(json.dumps({'districts':len(districts),'metrics':len(metrics),'annual_rows':len(annual),'dictionary_fields':len(dictionary),'browser_bytes':(out/'explorer.json').stat().st_size}))

if __name__=='__main__':main()
