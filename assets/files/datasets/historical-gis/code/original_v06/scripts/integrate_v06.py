#!/usr/bin/env python3
"""Combine real-source modules with v0.5 while preserving every original value."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, shutil, sqlite3
import numpy as np
import pandas as pd
import geopandas as gpd
import shapely

ROOT=Path(__file__).resolve().parents[1]
BASE=(ROOT/'inputs/base_v05_inputs.gpkg' if (ROOT/'inputs/base_v05_inputs.gpkg').exists()
      else ROOT.parent/'gis_work/GIS_v04_Preparation/outputs/wave2_completed/historical_gis_czech_lands_v05.gpkg')
OUT=ROOT/'outputs'; TARGET=OUT/'historical_gis_czech_lands_v06.gpkg'
LAYERS=['judicial_1930','judicial_1921','political_1930','political_1921']
BASE_SHA='e12e39b14e421394d5f6f083f454ef28178bec5ad8ec62b6f116408c1d4c8748'
MODULE_GPKGS={'rail':'rail_module.gpkg','basins':'basins.gpkg','borders':'borders.gpkg',
              'geology':'geology.gpkg','settlements':'settlements.gpkg','landuse':'landuse.gpkg'}


def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()


def q(x):return '"'+x.replace('"','""')+'"'


def register_gpkg_geometry_functions(connection):
 # SQLite compiles GeoPackage RTree triggers even when only attributes change.
 # Supply the standard geometry functions without dropping any spatial index.
 def geometry(blob):
  if blob is None:return None
  data=bytes(blob)
  if data[:2]!=b'GP':raise ValueError('Expected a standard GeoPackage geometry')
  envelope=(data[3]>>1)&7
  offset=8+{0:0,1:32,2:48,3:48,4:64}[envelope]
  return shapely.from_wkb(data[offset:])
 connection.create_function('ST_IsEmpty',1,lambda b:1 if b is None else int(geometry(b).is_empty))
 for name,index in [('ST_MinX',0),('ST_MinY',1),('ST_MaxX',2),('ST_MaxY',3)]:
  connection.create_function(name,1,lambda b,i=index:None if b is None else float(geometry(b).bounds[i]))


def registered_tables(path):
 with sqlite3.connect(path) as c:
  return c.execute('SELECT table_name,data_type,description FROM gpkg_contents ORDER BY rowid').fetchall()


def add_table(c,name,df,description='',keys=None):
 if name in {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
  raise ValueError('Refusing table overwrite: '+name)
 df.to_sql(name,c,index=False,if_exists='fail',chunksize=5000)
 c.execute('INSERT INTO gpkg_contents(table_name,data_type,identifier,description,last_change,srs_id) VALUES(?,?,?,?,?,NULL)',
           (name,'attributes',name,description,datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')))
 if keys:
  assert not df.duplicated(keys).any(),(name,keys)
  c.execute('CREATE UNIQUE INDEX '+q('idx_'+name+'_key')+' ON '+q(name)+'('+','.join(map(q,keys))+')')
 c.commit()


def key_fields(table,columns):
 special={
  'gis_rail_annual':['geography','district_year_id','calendar_year'],
  'gis_borders':['geography','district_year_id','snapshot_id'],
  'gis_basins':['geography','district_year_id','hybas_level'],
  'gis_basin_district_links':['geography','district_year_id','hybas_level','HYBAS_ID'],
  'gis_soil_by_depth':['geography','district_year_id','property','depth_top_cm','depth_bottom_cm'],
  'gis_neighbors':['geography','district_year_id','neighbor_district_year_id'],
  'gis_district_distances':['geography','district_year_id','neighbor_district_year_id'],
  'gis_geology_composition':['geography','district_year_id','geology_legend_code'],
  'gis_geology_district_links':['geography','district_year_id','source_objectid'],
  'gis_landuse':['geography','district_year_id','calendar_year'],
  'gis_landuse_static':['geography','district_year_id'],
  'landuse_district_unit_links':['geography','district_year_id','landuse_unit_id'],
  'gis_gazetteer_reference':['geography','district_year_id'],
  'gis_geology':['geography','district_year_id'],
  'gis_basins_static':['geography','district_year_id'],
  'gis_minerals':['geography','district_year_id'],
  'gis_minerals_district_links':['geography','district_year_id','deposit_id'],
  'gis_minerals_categories':['geography','district_year_id','category_dimension','category_label'],
  'border_snapshots':['snapshot_id'],
 }
 ks=special.get(table)
 return ks if ks and set(ks)<=set(columns) else None


def static_sources(layer):
 files=[('rail',ROOT/f'modules/rail/gis_rail_static_{layer}.csv'),
        ('basins',ROOT/'modules/basins/gis_basins_static.csv'),
        ('borders',ROOT/'modules/borders/gis_borders_static.csv'),
        ('geology',ROOT/'modules/geology/gis_geology.csv'),
        ('settlements',ROOT/'modules/settlements/gis_gazetteer_reference.csv'),
        ('soil',ROOT/'modules/soil/gis_soil.csv'),
        ('spatial',ROOT/'modules/spatial/gis_spatial_summary.csv')]
 # Land use and optional minerals have explicit static export filenames.
 for mod in ['landuse','minerals']:
  directory=ROOT/'modules'/mod
  candidates=[directory/f'gis_{mod}_static.csv',directory/f'gis_{mod}.csv']
  for p in candidates:
   if p.exists():
    df=pd.read_csv(p,nrows=3)
    if 'calendar_year' not in df and 'observation_year' not in df:
     files.append((mod,p));break
 for mod,p in files:
  if not p.exists():raise FileNotFoundError(p)
  d=pd.read_csv(p,float_precision='round_trip')
  if 'geography' in d:d=d[d.geography==layer].copy()
  yield mod,p,d


def add_static_columns(target):
 counts=[];field_origin={}
 with sqlite3.connect(target) as c:
  register_gpkg_geometry_functions(c)
  for layer in LAYERS:
   old=pd.read_sql_query('SELECT * FROM '+q(layer),c)
   ids=old.district_year_id.tolist();extra=pd.DataFrame({'district_year_id':ids})
   for module,p,d in static_sources(layer):
    assert d.district_year_id.is_unique and set(d.district_year_id)==set(ids),(layer,p)
    if 'boundary_year' in d:assert d.boundary_year.eq(int(layer[-4:])).all()
    d=d.drop(columns=[z for z in ['geography','boundary_year'] if z in d])
    overlap=(set(d)-{'district_year_id'})&(set(old)|set(extra))
    if overlap:raise ValueError(f'Column collision {layer} {module}: {overlap}')
    for col in d.columns:
     if col!='district_year_id':field_origin[(layer,col)]=module
    extra=extra.merge(d,on='district_year_id',validate='one_to_one',how='left',sort=False)
   newcols=[z for z in extra if z!='district_year_id']
   for col in newcols:
    s=extra[col]
    typ='INTEGER' if pd.api.types.is_integer_dtype(s) or pd.api.types.is_bool_dtype(s) else 'REAL' if pd.api.types.is_numeric_dtype(s) else 'TEXT'
    c.execute('ALTER TABLE '+q(layer)+' ADD COLUMN '+q(col)+' '+typ)
   def native(v):
    if pd.isna(v):return None
    if isinstance(v,np.generic):return v.item()
    return v
   values=[tuple(native(v) for v in row) for row in extra[newcols+['district_year_id']].itertuples(index=False,name=None)]
   c.executemany('UPDATE '+q(layer)+' SET '+','.join(q(z)+'=?' for z in newcols)+' WHERE district_year_id=?',values)
   c.commit()
   master=pd.read_sql_query('SELECT '+','.join(q(z) for z in old.columns if z not in ['fid','geom'])+','+','.join(map(q,newcols))+' FROM '+q(layer),c)
   master.to_csv(OUT/f'gis_master_{layer}_v06.csv',index=False,encoding='utf-8-sig')
   counts.append({'geography':layer,'districts':len(master),'static_columns':len(master.columns),'new_columns':len(newcols)})
   print('master',layer,master.shape,flush=True)
 return counts,field_origin


def all_dictionaries():
 frames=[]
 oldpath=ROOT/'inputs/v05_variable_dictionary.csv'
 if not oldpath.exists():oldpath=ROOT.parent/'r_package_work/histCzechia/inst/extdata/dictionary.csv'
 old=pd.read_csv(oldpath).fillna('');old['module']='v05';frames.append(old)
 for p in sorted((ROOT/'modules').rglob('*dictionary.csv')):
  d=pd.read_csv(p).fillna('')
  if not {'table','variable'}<=set(d):continue
  if 'description' not in d:d['description']=d.get('definition','')
  if 'period' not in d:d['period']=d.get('observation_period','')
  if 'source' not in d:d['source']=d.get('source_id',p.parent.name)
  if 'notes' not in d:d['notes']=d.get('method','')
  if 'license' in d:d['notes']=d.notes+' Licence: '+d.license
  d['module']=p.parent.name;frames.append(d)
 return pd.concat(frames,ignore_index=True).fillna('')


def build_dictionary(c,origins):
 definitions=all_dictionaries();rows=[];generic=[]
 tables=c.execute('SELECT table_name,data_type FROM gpkg_contents').fetchall()
 defaults={'rail':('reconstructed annual states 1901–1938','UPOL ZelezniceCR, Bedrunka2023'),
           'basins':('modern topographic catchment model','HydroBASINS v1c'),
           'geology':('modern geological mapping; source 1:500000','Czech Geological Survey'),
           'borders':('specified reference_date / source validity interval','CShapes2.0'),
           'settlements':('reference gazetteer; existence in1930 not asserted','CZ_RETRO, SOVAMM/NPÚ'),
           'soil':('modern model; no historical observation year','ISRIC SoilGrids2.0'),
           'spatial':('fixed1921/1930 district geometries','v0.5 unchanged boundaries'),
           'landuse':('1845,1948,1990,2000 explicitly distinguished','LUCC Czechia'),
           'population':('census years1869–2011; municipal geography2015','ČSÚ170240-17'),
           'minerals':('modern inventory; historical mine operation unknown','Czech Geological Survey')}
 for table,kind in tables:
  for info in c.execute('PRAGMA table_info('+q(table)+')').fetchall():
   _,col,typ,*_=info
   if col in ['fid','geom']:continue
   hit=definitions[(definitions.table==table)&(definitions.variable==col)]
   module=origins.get((table,col),'')
   if hit.empty and module:hit=definitions[(definitions.module==module)&(definitions.variable==col)]
   if hit.empty:hit=definitions[definitions.variable==col]
   if not hit.empty:
    h=hit.iloc[0];desc=str(h.description);unit=str(h.get('unit',''));period=str(h.get('period',''));source=str(h.get('source',''));notes=str(h.get('notes',''));group=str(h.get('group','')) or str(h.get('module',''))
   else:
    module=module or next((m for m in defaults if m in table),'source')
    period,source=defaults.get(module,('source-specific','See source metadata retained in package'))
    desc=f'Original or technical field {col} in {table}; consult the retained source schema.'
    unit='source field';notes='Source field preserved without inference of historical meaning.';group=module
    generic.append({'table':table,'variable':col})
   if not period:period=defaults.get(module,('source-specific',''))[0]
   rows.append(dict(table=table,variable=col,type=typ,group=group,description=desc,unit=unit,period=period,source=source,notes=notes))
 d=pd.DataFrame(rows)
 assert not d.duplicated(['table','variable']).any()
 d.to_csv(OUT/'GIS_V06_DATA_DICTIONARY.csv',index=False)
 pd.DataFrame(generic).to_csv(ROOT/'audit/dictionary_original_fields.csv',index=False)
 add_table(c,'gis_variable_dictionary',d,'Field definitions; explicit source periods and interpretation limitations.',['table','variable'])
 return len(d),generic


def collect_sources(c):
 components=[];files=[]
 for m in ['rail','soil','basins','geology','borders','settlements','population','landuse','minerals','spatial']:
  p=ROOT/'modules'/m/('rail_manifest.json' if m=='rail' else 'manifest.json')
  if not p.exists():continue
  obj=json.loads(p.read_text());components.append({'component':m,'status':obj.get('status','documented'),'manifest_path':str(p.relative_to(ROOT)),'metadata_json':json.dumps(obj,ensure_ascii=False)})
  def walk(o):
   if isinstance(o,dict):
    source_url=o.get('url',o.get('source_url'))
    if isinstance(source_url,str) and o.get('sha256'):
     files.append({'component':m,'url':source_url,'path':o.get('path',o.get('file','')),'bytes':o.get('bytes'),'sha256':o['sha256']})
    if o.get('archive_sha256'):
     name=o.get('archive_filename','')
     path=ROOT/'sources'/m/name
     files.append({'component':m,'url':o.get('url',''),'path':str(path.relative_to(ROOT)) if path.exists() else name,'bytes':o.get('archive_bytes'),'sha256':o['archive_sha256']})
    if o.get('source_archive_sha256'):
     files.append({'component':m,'url':o.get('source_url',''),'path':'original external archive','bytes':o.get('source_archive_bytes'),'sha256':o['source_archive_sha256']})
    if o.get('source_sha256') and o.get('source_original_export'):
     fp=ROOT/o['source_original_export']
     files.append({'component':m,'url':o.get('source_url',''),'path':o['source_original_export'],'bytes':fp.stat().st_size if fp.exists() else None,'sha256':o['source_sha256']})
    for val in o.values():walk(val)
   elif isinstance(o,list):
    for val in o:walk(val)
  walk(obj)
  if m=='soil':walk(json.loads((ROOT/'sources/soil/acquisition_manifest.json').read_text()))
  for field in ['source_download_manifest','acquisition_manifest']:
   if obj.get(field) and (ROOT/obj[field]).is_file():
    walk(json.loads((ROOT/obj[field]).read_text()))
 d=pd.DataFrame(components);f=pd.DataFrame(files).drop_duplicates()
 add_table(c,'gis_source_catalog_v06',d,'Actual acquired modules, full provenance and explicit completion status.',['component'])
 add_table(c,'gis_source_files_v06',f,'Actual additional source files and SHA256; original v0.5 sources remain in gis_source_catalog.')
 d.to_csv(OUT/'GIS_V06_SOURCE_CATALOG.csv',index=False);f.to_csv(OUT/'GIS_V06_SOURCE_FILES.csv',index=False)


def preserve_original_check(target):
 results=[]
 with sqlite3.connect(BASE) as old,sqlite3.connect(target) as new:
  for table,_,_ in registered_tables(BASE):
   cols=[r[1] for r in old.execute('PRAGMA table_info('+q(table)+')')]
   sql='SELECT '+','.join(map(q,cols))+' FROM '+q(table)+' ORDER BY rowid'
   a=old.execute(sql);b=new.execute(sql);n=0;ok=True
   while True:
    x=a.fetchmany(5000);y=b.fetchmany(5000)
    if x!=y:ok=False;break
    n+=len(x)
    if not x:break
   results.append({'check':'all_original_values_and_geometry_unchanged','table':table,'rows_compared':n,'passed':ok})
  for (table,) in old.execute("SELECT name FROM sqlite_master WHERE type='table' AND sql LIKE 'CREATE VIRTUAL TABLE%USING rtree%'").fetchall():
   sql='SELECT * FROM '+q(table)+' ORDER BY id'
   x=old.execute(sql).fetchall();y=new.execute(sql).fetchall()
   results.append({'check':'original_spatial_index_unchanged','table':table,'rows_compared':len(x),'passed':x==y})
  results.append({'check':'original_file_sha256_unchanged','table':'base_file','rows_compared':0,'passed':sha(BASE)==BASE_SHA})
 out=pd.DataFrame(results);out.to_csv(ROOT/'audit/v06_original_preservation.csv',index=False)
 assert out.passed.all(),out[~out.passed].to_string()
 return results


def main():
 OUT.mkdir(exist_ok=True)
 assert sha(BASE)==BASE_SHA,'Unexpected v0.5 input'
 for m,n in MODULE_GPKGS.items():
  if not (ROOT/'modules'/m/n).exists():raise FileNotFoundError(ROOT/'modules'/m/n)
 for p in ['soil/gis_soil.csv','soil/gis_soil_by_depth.csv.gz','spatial/gis_neighbors.csv.gz']:
  if not (ROOT/'modules'/p).exists():raise FileNotFoundError(p)
 temp=OUT/'historical_gis_czech_lands_v06.building.gpkg'
 if temp.exists():temp.unlink()
 shutil.copy2(BASE,temp)
 sources=dict(MODULE_GPKGS)
 if (ROOT/'modules/minerals/minerals.gpkg').exists():sources['minerals']='minerals.gpkg'
 for module,filename in sources.items():
  path=ROOT/'modules'/module/filename
  for table,kind,description in registered_tables(path):
   if kind=='features':
    with sqlite3.connect(temp) as check_connection:
     assert check_connection.execute('SELECT COUNT(*) FROM sqlite_master WHERE type=? AND name=?',('table',table)).fetchone()[0]==0,('Refusing feature-layer overwrite',table)
    g=gpd.read_file(path,layer=table)
    g.to_file(temp,layer=table,driver='GPKG')
   elif kind=='attributes':
    with sqlite3.connect(path) as src,sqlite3.connect(temp) as dest:
     d=pd.read_sql_query('SELECT * FROM '+q(table),src)
     add_table(dest,table,d,description or 'See module documentation.',key_fields(table,d.columns))
   print('import',module,table,flush=True)
 with sqlite3.connect(temp) as c:
  for module,table,filename in [('soil','gis_soil','gis_soil.csv'),('soil','gis_soil_by_depth','gis_soil_by_depth.csv.gz'),
             ('spatial','gis_neighbors','gis_neighbors.csv.gz'),('spatial','gis_district_distances','gis_district_distances.csv.gz'),
             ('spatial','gis_spatial_summary','gis_spatial_summary.csv')]:
   d=pd.read_csv(ROOT/'modules'/module/filename,float_precision='round_trip')
   keys=key_fields(table,d.columns) or ['geography','district_year_id']
   add_table(c,table,d,'See '+module+' module documentation.',keys)
  p=ROOT/'modules/population/csu_population_houses_1869_2011_municipalities2015.csv.gz'
  if p.exists():
   d=pd.read_csv(p,dtype={'vuzemi_kod':str},low_memory=False)
   add_table(c,'csu_population_houses_reference',d,'Reference only: census data harmonized to municipal boundaries2015. NOT joined to historical districts.')
 layercounts,origins=add_static_columns(temp)
 with sqlite3.connect(temp) as c:
  collect_sources(c)
  ndict,generic=build_dictionary(c,origins)
  counts={t:c.execute('SELECT COUNT(*) FROM '+q(t)).fetchone()[0] for t,_,_ in registered_tables(temp)}
  metadata={'release':'0.6','schema_version':'0.6','built_utc':datetime.now(timezone.utc).isoformat(),
            'base_release':'0.5','base_sha256':BASE_SHA,'table_counts':counts,'geographies':LAYERS,
            'status':'actual_source_data_integrated_with_documented_source_limitations',
            'historical_warning':'Observation years differ from boundary years; modern proxies and historical estimates are explicitly labelled.',
            'publication_status':'Private research delivery. Public redistribution of UPOL rail data and conflicting CZ_RETRO licence statements requires clarification.'}
  meta=pd.DataFrame([{'key':k,'value':json.dumps(v,ensure_ascii=False) if not isinstance(v,str) else v} for k,v in metadata.items()])
  add_table(c,'gis_release_metadata',meta,'Version metadata and actual table counts.',['key'])
  assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
  for layer in LAYERS:
   static=pd.read_sql_query('SELECT '+','.join(q(r[1]) for r in c.execute('PRAGMA table_info('+q(layer)+')').fetchall() if r[1] not in ['fid','geom'])+' FROM '+q(layer),c)
   climate=pd.read_sql_query('SELECT * FROM gis_climate_annual WHERE geography=?',c,params=(layer,)).drop(columns=['geography'])
   shared=[z for z in climate if z in static and z!='district_year_id']
   merged=climate.merge(static.drop(columns=shared),on='district_year_id',validate='many_to_one')
   rail=pd.read_sql_query('SELECT * FROM gis_rail_annual WHERE geography=?',c,params=(layer,))
   fields=['district_year_id','calendar_year']+[z for z in rail if z not in merged and z not in ['geography','boundary_year']]
   merged=merged.merge(rail[fields],on=['district_year_id','calendar_year'],validate='one_to_one')
   assert len(merged)==len(static)*38
   merged.to_csv(OUT/f'gis_annual_{layer}_1901_1938_v06.csv.gz',index=False,compression='gzip')
 preservation=preserve_original_check(temp)
 if TARGET.exists():TARGET.unlink()
 temp.replace(TARGET)
 metadata.update({'filename':TARGET.name,'bytes':TARGET.stat().st_size,'sha256':sha(TARGET),'layers':layercounts,
                  'dictionary_rows':ndict,'generic_source_field_definitions':len(generic),'original_preservation_checks':len(preservation)})
 (OUT/'integrated_v06_manifest.json').write_text(json.dumps(metadata,indent=2,ensure_ascii=False))
 print(json.dumps(metadata,indent=2,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
