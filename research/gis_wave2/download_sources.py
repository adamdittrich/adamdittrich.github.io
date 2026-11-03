#!/usr/bin/env python3
"""Reproducible regional subsets of CRU-TS 4.10 and HydroRIVERS 1.0.
Raw decoded climate values are cropped, not interpolated. Two processes maximum.
"""
from pathlib import Path
import concurrent.futures as cf
import datetime, gzip, hashlib, json, shutil, zipfile
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import xarray as xr
import geopandas as gpd

OUT=Path('results/wave2_sources'); OUT.mkdir(parents=True,exist_ok=True)
TMP=Path('wave2_cache'); TMP.mkdir(exist_ok=True)
BASE='https://crudata.uea.ac.uk/cru/data/hrg/cru_ts_4.10/cruts.2604091129.v4.10'
VARIABLES=['pre','tmp','tmn','tmx','dtr','wet','frs','pet','vap','cld']
BBOX=(10.0,47.0,21.0,53.0)

def download(url,path):
    session=requests.Session()
    session.mount('https://',HTTPAdapter(max_retries=Retry(total=4,backoff_factor=2,status_forcelist=[429,500,502,503,504])))
    digest=hashlib.sha256(); n=0
    with session.get(url,timeout=(30,240),stream=True) as r:
        r.raise_for_status()
        with path.open('wb') as f:
            for part in r.iter_content(1024*1024):
                if part: f.write(part);digest.update(part);n+=len(part)
    return {'url':url,'file':path.name,'bytes':n,'sha256':digest.hexdigest()}

def climate_part(task):
    var,start=task; end=start+9
    name=f'cru_ts4.10.{start}.{end}.{var}.dat.nc.gz'
    gz=TMP/name; nc=TMP/name[:-3]
    record=download(f'{BASE}/{var}/{name}',gz)
    with gzip.open(gz,'rb') as source, nc.open('wb') as target:
        shutil.copyfileobj(source,target,1024*1024)
    with xr.open_dataset(nc) as src:
        selected=src.sel(lon=slice(BBOX[0],BBOX[2]),lat=slice(BBOX[1],BBOX[3]),time=slice('1901-01-01','1938-12-31')).load()
        record['global_attributes']={k:str(v) for k,v in src.attrs.items()}
        record['variable_attributes']={k:{a:str(b) for a,b in v.attrs.items()} for k,v in src.variables.items()}
        record['source_variables']=list(src.data_vars)
    names={k:f'{var}__{k}' for k in selected.data_vars if k!=var}
    selected=selected.rename(names)
    destination=OUT/f'part_{var}_{start}.nc'
    selected.to_netcdf(destination,engine='scipy',format='NETCDF3_64BIT')
    nc.unlink();gz.unlink()
    print('CRU part',var,start,dict(selected.sizes),list(selected.data_vars),flush=True)
    return record

def hydro():
    archive=TMP/'HydroRIVERS_v10_eu_shp.zip'
    rec=download('https://data.hydrosheds.org/file/HydroRIVERS/HydroRIVERS_v10_eu_shp.zip',archive)
    with zipfile.ZipFile(archive) as z:
        z.extractall(TMP/'hydrorivers')
    shp=next((TMP/'hydrorivers').rglob('*.shp'))
    rivers=gpd.read_file(shp,bbox=BBOX)
    assert len(rivers)>0 and rivers.HYRIV_ID.is_unique
    assert rivers.geometry.is_valid.all()
    rivers.to_file(OUT/'hydrorivers_v10_region_10E21E_47N53N.gpkg',layer='hydrorivers',driver='GPKG')
    for pdf in (TMP/'hydrorivers').rglob('*.pdf'):
        shutil.copy2(pdf,OUT/pdf.name)
    rec.update({'regional_reaches':len(rivers),'regional_bounds':rivers.total_bounds.tolist(),'crs':str(rivers.crs),'columns':list(rivers.columns)})
    print('HYDRO',len(rivers),'regional reaches',flush=True)
    return rec

def main():
    manifest={'downloaded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'bbox_wgs84':BBOX,'period':'1901-01 to 1938-12','cru_version':'4.10','sources':[]}
    manifest['hydrorivers']=hydro()
    tasks=[(v,y) for v in VARIABLES for y in [1901,1911,1921,1931]]
    with cf.ProcessPoolExecutor(max_workers=2) as pool:
        for record in pool.map(climate_part,tasks):
            manifest['sources'].append(record)
            (OUT/'download_manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf8')
    outputs=[]
    for v in VARIABLES:
        parts=[xr.open_dataset(OUT/f'part_{v}_{y}.nc',engine='scipy').load() for y in [1901,1911,1921,1931]]
        joined=xr.concat(parts,dim='time',combine_attrs='drop_conflicts')
        assert joined.sizes['time']==456 and joined.indexes['time'].is_unique
        outputs.append(joined)
    combined=xr.merge(outputs,compat='no_conflicts',combine_attrs='drop_conflicts')
    combined.attrs.update({'title':'Regional unaggregated subset of CRU-TS 4.10, 1901-1938','source':BASE,'spatial_resolution_degrees':0.5,'subset_only':'No resampling, temporal aggregation or district interpolation applied','attribution':'Climatic Research Unit, University of East Anglia; Harris et al. (2020), doi:10.1038/s41597-020-0453-3'})
    combined.to_netcdf(OUT/'cru_ts_4_10_central_europe_1901_1938.nc',engine='scipy',format='NETCDF3_64BIT')
    for p in OUT.glob('part_*.nc'): p.unlink()
    for label,url in [('cru_release_notes.txt','https://crudata.uea.ac.uk/cru/data/hrg/cru_ts_4.10/Release_Notes_CRU_TS_4.10.txt'),('cru_version_source.html','https://crudata.uea.ac.uk/cru/data/hrg/cru_ts_4.10/'),('hydrorivers_source.html','https://www.hydrosheds.org/products/hydrorivers')]:
        try: manifest.setdefault('documentation',[]).append(download(url,OUT/label))
        except Exception as e: manifest.setdefault('documentation_errors',[]).append(str(e))
    manifest['final_dimensions']=dict(combined.sizes)
    manifest['final_variables']=list(combined.data_vars)
    (OUT/'download_manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf8')
    print('COMPLETE',dict(combined.sizes),list(combined.data_vars),flush=True)

if __name__=='__main__': main()
