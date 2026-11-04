#!/usr/bin/env python3
"""Real SoilGrids v2 regional mosaics and exact pixel/district area aggregation.

Native source GeoTIFF tiles retain nodata. Do not use the WCS response tested
during acquisition: that service did not retain its nodata metadata.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
import argparse, hashlib, json, time, xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.merge import merge
import requests
import pyproj
from exactextract import exact_extract

ROOT=Path(__file__).resolve().parents[1]
BASE=(ROOT/'inputs/base_v05_inputs.gpkg' if (ROOT/'inputs/base_v05_inputs.gpkg').exists()
      else ROOT.parent/'gis_work/GIS_v04_Preparation/outputs/wave2_completed/historical_gis_czech_lands_v05.gpkg')
SRC=ROOT/'sources/soil'; OUT=ROOT/'modules/soil'
LAYERS=['judicial_1930','judicial_1921','political_1930','political_1921']
DEPTHS=[('0-5cm',0,5),('5-15cm',5,15),('15-30cm',15,30)]
PROPS={
 'clay':('clay_pct',10,'percent','Clay concentration in fine earth'),
 'sand':('sand_pct',10,'percent','Sand concentration in fine earth'),
 'silt':('silt_pct',10,'percent','Silt concentration in fine earth'),
 'cfvo':('coarse_fragments_vol_pct',10,'percent by volume','Coarse fragments'),
 'phh2o':('ph_water',10,'pH','pH in water; arithmetic descriptive mean, not the pH of mixed soil'),
 'soc':('organic_carbon_g_kg',10,'g/kg','Soil organic carbon concentration'),
 'bdod':('bulk_density_kg_dm3',100,'kg/dm3','Bulk density'),
 'cec':('cec_cmolc_kg',10,'cmol(c)/kg','Cation exchange capacity buffered at pH7'),
 'nitrogen':('nitrogen_g_kg',100,'g/kg','Total nitrogen concentration'),
}
URL='https://files.isric.org/soilgrids/latest/data/'


def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()


def fetch(url,path):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 if not path.exists():
  for attempt in range(3):
   try:
    r=requests.get(url,timeout=(20,90));r.raise_for_status()
    if len(r.content)<100:raise ValueError('Unexpected small source')
    tmp=path.with_suffix(path.suffix+'.part');tmp.write_bytes(r.content);tmp.replace(path);break
   except Exception:
    if attempt==2:raise
 return {'url':url,'path':str(path.relative_to(ROOT)),'bytes':path.stat().st_size,'sha256':sha(path)}


def prepare_maps(properties):
 SRC.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
 jobs=[(p,d) for p in properties for d,_,_ in DEPTHS]
 cached={(p,d):SRC/'regional'/f'{p}_{d}_mean_region.tif' for p,d in jobs}
 if (SRC/'acquisition_manifest.json').exists() and all(p.exists() for p in cached.values()):
  manifest=json.loads((SRC/'acquisition_manifest.json').read_text())
  expected={r['path']:r['sha256'] for r in manifest['regional_files']}
  for p in cached.values():
   assert sha(p)==expected[str(p.relative_to(ROOT))],f'Cached regional input changed: {p}'
  print('Using verified archived regional SoilGrids pixels; no source download needed',flush=True)
  return cached,manifest['crs_wkt']
 vrts={}; source_records=[]
 def vrtjob(item):
  p,d=item;name=f'{p}_{d}_mean.vrt';u=f'{URL}{p}/{name}';dest=SRC/'vrt'/name
  meta=fetch(u,dest);return p,d,dest,meta
 with ThreadPoolExecutor(max_workers=4) as ex:
  for fut in as_completed([ex.submit(vrtjob,j) for j in jobs]):
   p,d,dest,meta=fut.result();vrts[(p,d)]=dest;source_records.append(meta);print('VRT',p,d,flush=True)
 ref=ET.parse(vrts[jobs[0]]).getroot();crs=ref.findtext('SRS');gt=list(map(float,ref.findtext('GeoTransform').split(',')))
 gs=gpd.read_file(BASE,layer='judicial_1930').to_crs(crs)
 b=gs.total_bounds.copy()
 b[0]=np.floor((b[0]-gt[0])/250)*250+gt[0]-250;b[2]=np.ceil((b[2]-gt[0])/250)*250+gt[0]+250
 b[1]=np.floor((b[1]-gt[3])/250)*250+gt[3]-250;b[3]=np.ceil((b[3]-gt[3])/250)*250+gt[3]+250
 tile_jobs=[];tile_lookup={}
 for (p,d),path in vrts.items():
  v=ET.parse(path).getroot();band=v.find('VRTRasterBand');assert band.findtext('NoDataValue')=='-32768'
  gt2=list(map(float,v.findtext('GeoTransform').split(',')))
  # The SOC global VRT omits three western columns. Its grid phase agrees.
  assert gt2[1:3]==gt[1:3] and gt2[4:]==gt[4:]
  assert np.isclose((gt2[0]-gt[0])/250,round((gt2[0]-gt[0])/250))
  assert np.isclose((gt2[3]-gt[3])/250,round((gt2[3]-gt[3])/250))
  choices=[]
  for s in band.findall('ComplexSource')+band.findall('SimpleSource'):
   r=s.find('DstRect');x,y,w,h=[float(r.get(k)) for k in ['xOff','yOff','xSize','ySize']]
   xmin=gt2[0]+250*x;ymax=gt2[3]-250*y
   if xmin<b[2] and xmin+250*w>b[0] and ymax>b[1] and ymax-250*h<b[3]:
    rel=s.findtext('SourceFilename');url=urljoin(f'{URL}{p}/',rel)
    local=SRC/'tiles'/p/rel.removeprefix('./')
    choices.append(local);tile_jobs.append((url,local))
  assert choices,(p,d)
  tile_lookup[(p,d)]=choices
 print('native regional tiles',len(tile_jobs),'bounds',b.tolist(),flush=True)
 unique_jobs=list(dict.fromkeys(tile_jobs))
 with ThreadPoolExecutor(max_workers=6) as ex:
  futures={ex.submit(fetch,u,p):(u,p) for u,p in unique_jobs}
  for n,fut in enumerate(as_completed(futures),1):
   source_records.append(fut.result())
   if n%30==0 or n==len(futures):print('tiles',n,'/',len(futures),flush=True)
 paths={}
 for (p,d),files in tile_lookup.items():
  dest=SRC/'regional'/f'{p}_{d}_mean_region.tif';dest.parent.mkdir(exist_ok=True)
  if not dest.exists():
   readers=[rasterio.open(f) for f in files]
   try:
    for rr in readers:assert rr.nodata==-32768 and np.allclose(rr.res,(250,250))
    array,trans=merge(readers,bounds=tuple(b),res=250,nodata=-32768,method='first')
    profile=readers[0].profile.copy();profile.update(driver='GTiff',height=array.shape[1],width=array.shape[2],transform=trans,count=1,nodata=-32768,compress='deflate',tiled=True,blockxsize=256,blockysize=256,crs=rasterio.crs.CRS.from_wkt(crs))
    with rasterio.open(dest,'w',**profile) as dst:
     dst.write(array);dst.update_tags(source='SoilGrids 2.0 native GeoTIFF tile mosaic',source_property=p,depth_interval=d,prediction='mean',historical_observation='false')
   finally:
    for rr in readers:rr.close()
  paths[(p,d)]=dest
  with rasterio.open(dest,'r+') as ds:
   # VRT says datum=WGS84, native TIFF says ellps=WGS84. Verify the
   # regional transformation numerically before standardizing this alias.
   a=pyproj.Transformer.from_crs(4326,ds.crs,always_xy=True)
   bcheck=pyproj.Transformer.from_crs(4326,crs,always_xy=True)
   testpoints=([12,15,19],[49,50,51])
   assert np.allclose(a.transform(*testpoints),bcheck.transform(*testpoints),rtol=0,atol=1e-6)
   ds.crs=rasterio.crs.CRS.from_wkt(crs)
   assert ds.nodata==-32768
  print('mosaic',dest.name,flush=True)
 acquisition={'provider':'ISRIC World Soil Information','product':'SoilGrids 2.0 rolling release; mean predictions',
              'accessed_utc':datetime.now(timezone.utc).isoformat(),'license':'CC BY 4.0',
              'method':'Unchanged integer pixels from official native GeoTIFF tiles; no resampling. Region mosaicked on native 250m Interrupted Goode Homolosine grid.',
              'bounds_native':b.tolist(),'crs_wkt':crs,'sources':sorted(source_records,key=lambda z:z['url']),
              'regional_files':[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in paths.values()]}
 (SRC/'acquisition_manifest.json').write_text(json.dumps(acquisition,indent=2,ensure_ascii=False))
 return paths,crs


def aggregate(paths,crs,properties):
 # Rasterio serializes this custom CRS using an equivalent ellipsoid/datum
 # alias. Use its actual WKT also for the vector transform, so exactextract
 # does not emit a false mismatch warning. The projection was verified in
 # prepare_maps; neither this normalization nor the mosaic resamples pixels.
 with rasterio.open(next(iter(paths.values()))) as reference:
  crs=reference.crs.to_wkt()
 geometries={l:gpd.read_file(BASE,layer=l)[['district_year_id','geometry']].to_crs(crs) for l in LAYERS}
 allrows=[];checks=[];composite_paths={}
 for prop in properties:
  dest=SRC/'regional'/f'{prop}_0-30cm_depth_weighted_mean_region.tif'
  inputs=[rasterio.open(paths[(prop,d)]) for d,_,_ in DEPTHS]
  try:
   assert all(ds.transform==inputs[0].transform and ds.shape==inputs[0].shape for ds in inputs)
   arrays=[ds.read(1,masked=True).astype(float) for ds in inputs]
   valid=np.logical_and.reduce([~np.ma.getmaskarray(a) for a in arrays])
   data=sum(a.data*(hi-lo) for a,(_,lo,hi) in zip(arrays,DEPTHS))/30
   data[~valid]=-32768
   profile=inputs[0].profile.copy();profile.update(dtype='float32',nodata=-32768)
   with rasterio.open(dest,'w',**profile) as dst:
    dst.write(data.astype('float32'),1);dst.update_tags(depth='0-30cm',definition='Thickness-weighted mean of predicted concentrations; all three source depths must be valid; not a soil-mass-weighted mixture.')
  finally:
   for ds in inputs:ds.close()
  composite_paths[prop]=dest
  for depth,lo,hi in DEPTHS+[('0-30cm',0,30)]:
   p=dest if depth=='0-30cm' else paths[(prop,depth)]
   name,divisor,unit,desc=PROPS[prop]
   for layer,g in geometries.items():
    z=exact_extract(str(p),g,['mean','stdev','min','max','count'],include_cols=['district_year_id'],output='pandas')
    z['geography']=layer;z['property']=prop;z['depth_top_cm']=lo;z['depth_bottom_cm']=hi
    z['unit']=unit
    for col in ['mean','stdev','min','max']:z[col]=z[col]/divisor
    z=z.rename(columns={'mean':'area_weighted_mean','stdev':'spatial_stdev','min':'spatial_min','max':'spatial_max','count':'valid_cell_equivalents'})
    areas=g.set_index('district_year_id').geometry.area
    z['coverage_fraction']=z.valid_cell_equivalents*62500/z.district_year_id.map(areas)
    z['mapped_area_km2']=z.valid_cell_equivalents*62500/1e6
    z['source_resolution_m']=250;z['soil_is_historical_observation']=0
    allrows.append(z)
    checks.append({'geography':layer,'property':prop,'depth':depth,'check':'coverage_in_0_1','passed':bool(z.coverage_fraction.between(-1e-8,1+1e-8).all())})
    checks.append({'geography':layer,'property':prop,'depth':depth,'check':'means_within_pixel_range','passed':bool(((z.area_weighted_mean>=z.spatial_min-1e-8)&(z.area_weighted_mean<=z.spatial_max+1e-8)|z.area_weighted_mean.isna()).all())})
   print('aggregated',prop,depth,flush=True)
 long=pd.concat(allrows,ignore_index=True)
 assert not long.duplicated(['geography','district_year_id','property','depth_top_cm','depth_bottom_cm']).any()
 top=long[(long.depth_top_cm==0)&(long.depth_bottom_cm==30)].copy()
 rows=[]
 for layer,g in geometries.items():
  frame=g[['district_year_id']].copy();frame.insert(0,'geography',layer)
  for prop in properties:
   name,_,unit,_=PROPS[prop];s=top[(top.geography==layer)&(top.property==prop)].set_index('district_year_id')
   frame[f'soil_{name}_0_30cm']=frame.district_year_id.map(s.area_weighted_mean)
   frame[f'soil_{prop}_0_30cm_coverage_fraction']=frame.district_year_id.map(s.coverage_fraction)
   frame[f'soil_{name}_0_30cm_spatial_sd']=frame.district_year_id.map(s.spatial_stdev)
  coverage=[c for c in frame if c.endswith('_coverage_fraction')]
  frame['soil_min_coverage_fraction']=frame[coverage].min(axis=1)
  frame['soil_low_coverage_flag']=(frame.soil_min_coverage_fraction<.9).astype(int)
  frame['soil_source_resolution_m']=250;frame['soil_is_historical_observation']=0
  rows.append(frame)
 static=pd.concat(rows,ignore_index=True)
 long.to_csv(OUT/'gis_soil_by_depth.csv.gz',index=False,compression='gzip')
 static.to_csv(OUT/'gis_soil.csv',index=False)
 # A meaningful independent validation of exact extraction: recompute a small
 # district mean by explicit Shapely pixel intersections, without exactextract.
 from shapely.geometry import box
 import shapely
 g=geometries['judicial_1930']
 usable=static.loc[(static.geography=='judicial_1930')&static.soil_clay_pct_0_30cm.notna()&(static.soil_clay_0_30cm_coverage_fraction>.05),'district_year_id']
 candidates=g[g.district_year_id.isin(usable)]
 test=candidates.loc[candidates.geometry.area.idxmin()]
 with rasterio.open(composite_paths['clay']) as ds:
  win=rasterio.windows.from_bounds(*test.geometry.bounds,transform=ds.transform).round_offsets().round_lengths()
  win=rasterio.windows.Window(max(0,win.col_off-1),max(0,win.row_off-1),win.width+3,win.height+3)
  a=ds.read(1,window=win,masked=True);t=ds.window_transform(win)
  rr,cc=np.indices(a.shape);xs=t.c+cc.ravel()*t.a;ys=t.f+rr.ravel()*t.e
  pix=shapely.box(xs,ys+t.e,xs+t.a,ys)
  weights=shapely.area(shapely.intersection(pix,test.geometry));good=(weights>0)&~np.ma.getmaskarray(a).ravel()
  mean=np.average(a.data.ravel()[good],weights=weights[good])/10 if good.any() else np.nan
  expected=static.loc[static.district_year_id==test.district_year_id,'soil_clay_pct_0_30cm'].iloc[0]
  checks.append({'geography':'judicial_1930','property':'clay','depth':'0-30cm','check':'independent_pixel_intersections_smallest_district','passed':bool(np.isclose(mean,expected,rtol=1e-6,atol=1e-7,equal_nan=True))})
 c=pd.DataFrame(checks);c.to_csv(ROOT/'audit/soil_validation.csv',index=False);assert c.passed.all(),c[~c.passed].to_string()
 dictrows=[]
 ident={'geography':'Historical boundary system','district_year_id':'Stable identifier of historical district','property':'SoilGrids source property code','depth_top_cm':'Top of depth interval','depth_bottom_cm':'Bottom of depth interval','unit':'Conventional unit after official scaling conversion','source_resolution_m':'Native source pixel size in metres','soil_source_resolution_m':'Native source pixel size in metres','soil_is_historical_observation':'Always 0: modern model, not an observation for 1921 or 1930','coverage_fraction':'Mapped valid soil area divided by whole district area; no-data areas excluded from mean','valid_cell_equivalents':'Sum of fractions of valid pixels intersected by district','mapped_area_km2':'Area of valid pixels inside district','area_weighted_mean':'Exact-pixel-area weighted mean of mean predictions; excludes nodata','spatial_stdev':'Area-weighted spatial standard deviation; NOT prediction uncertainty','spatial_min':'Minimum predicted pixel value among intersected pixels','spatial_max':'Maximum predicted pixel value among intersected pixels','soil_min_coverage_fraction':'Lowest of the property-specific 0-30cm coverage fractions','soil_low_coverage_flag':'1 if minimum coverage is below 90 percent'}
 for table,frame in [('gis_soil',static),('gis_soil_by_depth',long)]:
  for col in frame:
   definition=ident.get(col);unit='see property/unit'
   for p in properties:
    nm,div,un,de=PROPS[p]
    if col==f'soil_{nm}_0_30cm':definition=f'{de}: area mean of 0-30cm depth-thickness weighted prediction';unit=un
    if col==f'soil_{nm}_0_30cm_spatial_sd':definition=f'{de}: spatial standard deviation of 0-30cm composite; NOT model uncertainty';unit=un
    if col==f'soil_{p}_0_30cm_coverage_fraction':definition=f'Fraction of entire district with valid {p} values at all three depths 0-5, 5-15 and 15-30cm';unit='fraction'
   dictrows.append(dict(table=table,variable=col,unit=unit,definition=definition or col,period='modern SoilGrids 2.0 predictions; no unique historical observation year',source='ISRIC SoilGrids 2.0',notes='All soil properties are averaged over mapped soil area, not the full district including missing urban/water cells.'))
 pd.DataFrame(dictrows).to_csv(OUT/'dictionary.csv',index=False)
 meta=dict(module='soil',status='complete',built_utc=datetime.now(timezone.utc).isoformat(),properties=properties,
           depth_intervals_cm=[[0,5],[5,15],[15,30],[0,30]],source_resolution_m=250,
           rows_long=len(long),rows_static=len(static),validation_passed=int(c.passed.sum()),validation_failed=int((~c.passed).sum()),
           low_coverage_districts=static.loc[static.soil_low_coverage_flag==1,['geography','district_year_id','soil_min_coverage_fraction']].to_dict('records'),
           acquisition_manifest='sources/soil/acquisition_manifest.json',
           tables=[{'name':'gis_soil','file':'gis_soil.csv','keys':['geography','district_year_id']},
                   {'name':'gis_soil_by_depth','file':'gis_soil_by_depth.csv.gz','keys':['geography','district_year_id','property','depth_top_cm','depth_bottom_cm']}])
 (OUT/'manifest.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False))
 (ROOT/'docs/SOIL_METHODS_CZ.md').write_text('''# Půda: SoilGrids 2.0\n\nSkutečné celočíselné pixely byly staženy přímo z oficiálních GeoTIFF dlaždic ISRIC. Dlaždice byly spojeny a oříznuty na původní 250m mřížce v rovnoplochém Interrupted Goode Homolosine zobrazení, bez převzorkování. Původní chybějící hodnota -32768 je zachována. Zkušební WCS odpověď ztratila značku chybějící hodnoty; proto nebyla použita v produkčních statistikách. SHA256 souborů a původní adresy obsahuje manifest.\n\nPro každou proměnnou jsou uchovány hloubky 0–5, 5–15 a 15–30 cm. Souhrn 0–30 cm je vážen tloušťkou těchto vrstev (5/30, 10/30, 15/30) a vyžaduje platný pixel ve všech třech vrstvách. Jde o průměr predikovaných koncentrací podle tloušťky, nikoli podle hmotnosti půdy. pH je popisný aritmetický průměr pH, nikoli kyselost fyzicky smíchaných vzorků. Jednotky se převádějí přesně podle tabulky ISRIC.\n\nOkresní průměry a prostorová směrodatná odchylka používají skutečnou plochu překryvu pixelu s polygonem (exactextract). Jmenovatelem průměru je pokrytá půdní plocha. Podíl pokrytí je zvlášť vypočten proti celé ploše okresu. Vody, zastavěné plochy a další chybějící místa se nedoplňují nulou. Pod 90 % pokrytí je připojen diagnostický příznak. Prostorová směrodatná odchylka není intervalem spolehlivosti ani nejistotou modelu; kvantilové predikční vrstvy nejsou v tomto modulu agregované.\n\nSoilGrids je moderní model využívající půdní profily a environmentální prediktory. Údaje nejsou měřením roku 1930 ani 1921. Zvláště organický uhlík, pH a další chemické vlastnosti mohou být ovlivněny pozdějším hospodařením. Základní půdní maska používá moderní pokryv území. Modelová fyzická charakteristika proto vyžaduje historickou interpretaci.\n\nZdroj: ISRIC World Soil Information, SoilGrids 2.0, https://docs.isric.org/globaldata/soilgrids/ ; jednotky: https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_01.html . Licence CC BY 4.0.\n''',encoding='utf-8')
 print(json.dumps({'rows':len(static),'long_rows':len(long),'checks':len(c),'low_coverage':int(static.soil_low_coverage_flag.sum())},indent=2),flush=True)


if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--properties',nargs='+',default=['clay','sand','silt','cfvo','phh2o','soc'],choices=list(PROPS));args=p.parse_args()
 paths,crs=prepare_maps(args.properties);aggregate(paths,crs,args.properties)
