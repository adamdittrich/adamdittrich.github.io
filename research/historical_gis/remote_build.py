#!/usr/bin/env python3
"""Real historical district polygons (Czech lands) and Copernicus GLO-90 terrain.
Run from any working directory; all output goes to ./results.
"""
import json, math, time, logging
from pathlib import Path
from datetime import datetime,timezone
import geopandas as gpd
import numpy as np
import pandas as pd
import requests
import rasterio
from rasterio.merge import merge
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject,transform_bounds
from rasterio.features import rasterize
from scipy.ndimage import convolve
from shapely.ops import unary_union
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

OUT=Path("results"); OUT.mkdir(exist_ok=True)
CACHE=Path("download_cache"); CACHE.mkdir(exist_ok=True)
SERVICES={
 "judicial_1921":"Okresy_Ceska_1921",
 "judicial_1930":"Okresy_Ceska_1930",
 "political_1921":"Politicke_okresy_Ceska_1921",
 "political_1930":"Politicke_okresy_Ceska_1930"}
BASE="https://services1.arcgis.com/LPm07959azIAvFRD/ArcGIS/rest/services"
CRS="EPSG:3035"; GRID=200
logging.basicConfig(level="INFO",format="%(asctime)s %(levelname)s %(message)s")

def client():
 s=requests.Session()
 s.mount("https://",HTTPAdapter(max_retries=Retry(total=5,backoff_factor=1,status_forcelist=[429,500,502,503,504])))
 s.headers["User-Agent"]="Historic-economic-GIS-2026 academic-research"
 return s
S=client()
def jget(url,**params):
 r=S.get(url,params=params,timeout=(25,150));r.raise_for_status()
 j=r.json()
 if "error" in j: raise RuntimeError(str(j["error"]))
 return j

def layer(name,service):
 url=f"{BASE}/{service}/FeatureServer/0"
 meta=jget(url,f="json")
 available=[x["name"] for x in meta.get("fields",[])]
 preferred=["OBJECTID_1","OBJECTID","NAZEV","KOD_30","KOD30_NAKI","KOD_21","KOD21_NAKI","KOD21_NA_1","KOD30_NA_1"]
 fields=[c for c in preferred if c in available]
 ids=jget(url+"/query",where="1=1",returnIdsOnly="true",f="json").get("objectIds")
 if not ids: raise RuntimeError(f"No source feature IDs for {name}")
 feats=[]
 for k in range(0,len(ids),15):
  response=jget(url+"/query",objectIds=",".join(str(v) for v in ids[k:k+15]),
    outFields=",".join(fields),outSR="4326",geometryPrecision="6",
    returnGeometry="true",f="geojson")
  if response.get("type")!="FeatureCollection":raise RuntimeError(f"No GeoJSON for {name}")
  feats.extend(response["features"])
 if len(feats)!=len(ids):raise RuntimeError(f"{name}: source {len(ids)} IDs vs {len(feats)} geometries")
 raw={"type":"FeatureCollection","features":feats}
 (OUT/f"source_{name}.geojson").write_text(json.dumps(raw,ensure_ascii=False),encoding="utf8")
 geo=gpd.GeoDataFrame.from_features(feats,crs="EPSG:4326")
 if geo.geometry.isna().any(): raise RuntimeError(f"Null geom in {name}")
 n_bad=int((~geo.is_valid).sum())
 if n_bad:
  geo.geometry=geo.geometry.make_valid()
  geo.geometry=geo.geometry.map(lambda g: unary_union([p for p in g.geoms if p.geom_type in ("Polygon","MultiPolygon")]) if g.geom_type=="GeometryCollection" else g)
 if not geo.geometry.is_valid.all(): raise RuntimeError(f"Invalid geometry after repair {name}")
 year=1921 if "1921" in name else 1930
 typ="J" if name.startswith("judicial") else "P"
 candidates=(["KOD21_NAKI","KOD_21","KOD30_NAKI","KOD_30"] if year==1921
             else ["KOD30_NAKI","KOD_30","KOD21_NAKI","KOD_21"])
 col=next((c for c in candidates if c in geo.columns and geo[c].notna().all() and geo[c].is_unique),None)
 if col is None:
  col=next((c for c in ("OBJECTID_1","OBJECTID") if c in geo.columns and geo[c].notna().all() and geo[c].is_unique),None)
 if col is None: raise RuntimeError(f"No usable unique ID for {name}, fields={list(geo.columns)}")
 geo["district_year_id"]=[f"CZ{year}-{typ}-{int(v):05d}" for v in geo[col]]
 geo["year"]=year;geo["admin_type"]="judicial" if typ=="J" else "political"
 geo["source_key_field"]=col
 geo["area_gis_km2"]=geo.to_crs(CRS).geometry.area.to_numpy()/1e6
 gc=geo.to_crs(CRS).geometry.centroid.to_crs("EPSG:4326")
 geo["centroid_lon"]=gc.x.to_numpy();geo["centroid_lat"]=gc.y.to_numpy()
 logging.info("Downloaded %s: %d features, %d repaired",name,len(geo),n_bad)
 return geo,{"count":len(geo),"repaired":n_bad,"code_field":col,"area_total_km2":round(geo["area_gis_km2"].sum(),1),"source":url}

def tileurl(lat,lon):
 ns=f'{"N" if lat>=0 else "S"}{abs(lat):02d}_00'
 ew=f'{"E" if lon>=0 else "W"}{abs(lon):03d}_00'
 stem=f"Copernicus_DSM_COG_30_{ns}_{ew}_DEM"
 return f"https://copernicus-dem-90m.s3.amazonaws.com/{stem}/{stem}.tif"

def dem(geo):
 a,b,c,d=geo.to_crs(4326).total_bounds
 bbox=(a-.02,b-.02,c+.02,d+.02)
 tilepaths=[]
 for y in range(math.floor(bbox[1]),math.ceil(bbox[3])):
  for x in range(math.floor(bbox[0]),math.ceil(bbox[2])):
   target=CACHE/f"dem_N{y}_E{x}.tif"
   if not target.exists():
    url=tileurl(y,x)
    logging.info("DEM %s",url)
    with S.get(url,timeout=(30,180),stream=True) as r:
     if r.status_code==404:continue
     r.raise_for_status()
     with target.open("wb") as f:
      for buf in r.iter_content(1024*1024):
       if buf:f.write(buf)
   with rasterio.open(target) as ds:
    if ds.count!=1 or ds.crs is None:raise RuntimeError(f"Bad raster {target}")
   tilepaths.append(target)
 if not tilepaths:raise RuntimeError("No DEM tiles")
 logging.info("Downloading DEM complete: %d tiles",len(tilepaths))
 sources=[rasterio.open(p) for p in tilepaths]
 try:
  arr,t=merge(sources,bounds=bbox,res=(0.002,0.002),nodata=np.nan,resampling=Resampling.bilinear)
  src=arr[0].astype("float32")
 finally:
  for s in sources:s.close()
 xmin,ymin,xmax,ymax=transform_bounds("EPSG:4326",CRS,*bbox,densify_pts=25)
 w=math.ceil((xmax-xmin)/GRID);h=math.ceil((ymax-ymin)/GRID)
 tr=from_origin(xmin,ymax,GRID,GRID)
 elev=np.full((h,w),np.nan,dtype="float32")
 reproject(source=src,destination=elev,src_transform=t,src_crs="EPSG:4326",
  src_nodata=np.nan,dst_transform=tr,dst_crs=CRS,dst_nodata=np.nan,
  resampling=Resampling.bilinear,init_dest_nodata=True)
 if np.isfinite(elev).mean()<.15:raise RuntimeError("DEM grid largely empty")
 return elev,tr,len(tilepaths)

def derivatives(e):
 gy,gx=np.gradient(e,GRID)
 slope=np.rad2deg(np.arctan(np.hypot(gx,gy))).astype("float32")
 good=np.isfinite(e)
 val=np.where(good,e,0).astype("float64")
 kernel=np.ones((3,3),dtype="float64");kernel[1,1]=0
 ct=convolve(good.astype("float64"),kernel,mode="constant",cval=0)
 s1=convolve(val,kernel,mode="constant",cval=0)
 s2=convolve(val*val,kernel,mode="constant",cval=0)
 tri=np.sqrt(np.maximum(s2-2*val*s1+val*val*ct,0)/np.maximum(ct,1)).astype("float32")
 tri[(ct<3)|(~good)]=np.nan
 slope[~good]=np.nan
 return slope,tri

def zonal(g,e,slope,tri,tr):
 g=g.to_crs(CRS).reset_index(drop=True)
 z=rasterize(((gm,i+1) for i,gm in enumerate(g.geometry)),
    out_shape=e.shape,transform=tr,fill=0,all_touched=False,dtype="int32")
 records=[]
 for i,row in g.iterrows():
  match=z==i+1
  a=e[match];a=a[np.isfinite(a)]
  b=slope[match];b=b[np.isfinite(b)]
  c=tri[match];c=c[np.isfinite(c)]
  records.append({"district_year_id":row.district_year_id,
    "year":int(row.year),"admin_type":row.admin_type,"name":row.get("NAZEV"),
    "source_kod_30":row.get("KOD_30"),"gis_area_km2":row.area_gis_km2,
    "grid_m":GRID,"n_dem_cells":len(a),
    "mean_elevation_m":float(a.mean()) if len(a) else None,
    "median_elevation_m":float(np.median(a)) if len(a) else None,
    "min_elevation_m":float(a.min()) if len(a) else None,
    "max_elevation_m":float(a.max()) if len(a) else None,
    "p10_elevation_m":float(np.percentile(a,10)) if len(a) else None,
    "p90_elevation_m":float(np.percentile(a,90)) if len(a) else None,
    "elevation_range_m":float(a.max()-a.min()) if len(a) else None,
    "mean_slope_deg":float(b.mean()) if len(b) else None,
    "mean_tri_rms_m":float(c.mean()) if len(c) else None,
    "n_slope_cells":len(b),"n_tri_cells":len(c)})
 return pd.DataFrame(records)

def crosswalk(g1,g2):
 a=g1.to_crs(CRS).reset_index(drop=True)
 b=g2.to_crs(CRS).reset_index(drop=True)
 rows=[]
 for _,r in a.iterrows():
  for k in b.sindex.query(r.geometry,predicate="intersects"):
   s=b.iloc[int(k)]
   km=r.geometry.intersection(s.geometry).area/1e6
   if km<.02:continue
   rows.append({"district_id_1921":r.district_year_id,
      "district_id_1930":s.district_year_id,"area_overlap_km2":km,
      "share_of_area_1921":km/r.area_gis_km2,
      "share_of_area_1930":km/s.area_gis_km2})
 return pd.DataFrame(rows)

def main():
 layers={};audit={}
 for key,svc in SERVICES.items():
  layers[key],audit[key]=layer(key,svc)
 geomfile=OUT/"historical_districts_1921_1930_czech_lands.gpkg"
 if geomfile.exists():geomfile.unlink()
 for key,g in layers.items():g.to_file(geomfile,layer=key,driver="GPKG")
 crosswalk(layers["judicial_1921"],layers["judicial_1930"]).to_csv(
   OUT/"crosswalk_judicial_1921_1930_area.csv",index=False)
 for year in (1921,1930):
  crosswalk(layers[f"judicial_{year}"],layers[f"political_{year}"]).to_csv(
    OUT/f"crosswalk_judicial_political_{year}_area.csv",index=False)
 elev,tr,tiles=dem(layers["judicial_1930"])
 slope,tri=derivatives(elev)
 with rasterio.open(OUT/"terrain_grid_glo90_200m.tif","w",driver="GTiff",
   width=elev.shape[1],height=elev.shape[0],count=3,dtype="float32",
   transform=tr,crs=CRS,nodata=np.nan,compress="deflate",predictor=3,tiled=True) as ds:
  for i,(nm,ar) in enumerate([("elevation_m",elev),("slope_deg",slope),("tri_rms_m",tri)],1):
   ds.write(ar,i);ds.set_band_description(i,nm)
 qa={}
 for key,g in layers.items():
  tab=zonal(g,elev,slope,tri,tr)
  if tab.n_dem_cells.eq(0).any():raise RuntimeError(f"{key}: some districts lack DEM pixels")
  tab.to_csv(OUT/f"terrain_{key}_glo90_200m.csv",index=False)
  enriched=g.merge(tab.drop(columns=["year","admin_type","name","source_kod_30","gis_area_km2"]),
    on="district_year_id",how="left",validate="one_to_one")
  enriched.to_file(OUT/"districts_and_terrain.gpkg",layer=key,driver="GPKG")
  qa[key]={"count":len(tab),"valid_zones":int(tab.n_dem_cells.gt(0).sum()),
    "min_elev_m":round(tab.min_elevation_m.min(),1),"max_elev_m":round(tab.max_elevation_m.max(),1)}
 manifest={"created_utc":datetime.now(timezone.utc).isoformat(),
   "scope":"present-day Czechia (Czech lands), NOT full historical Czechoslovakia",
   "district_source":"UrRlab NAKI 1921 and 1930 ArcGIS FeatureServer",
   "terrain_source":"Copernicus DEM GLO-90, 2021 COG release, modern DSM not historical bare earth",
   "height_datum":"EGM2008","dem_tiles":tiles,"grid_m":GRID,"crs_raster":CRS,
   "zonal_method":"cell-center rasterized polygons; non-area-weighted",
   "ruggedness_method":"RMS elevation difference to 8 neighboring analysis-grid cells",
   "source_layers":audit,"qa":qa}
 (OUT/"build_manifest.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding="utf8")
 logging.info("SUCCESS: %s",json.dumps(qa))

if __name__=="__main__": main()
