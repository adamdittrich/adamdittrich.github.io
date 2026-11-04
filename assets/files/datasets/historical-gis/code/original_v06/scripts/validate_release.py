#!/usr/bin/env python3
"""Checks relationships across completed modules and writes a release inventory."""
from pathlib import Path
import hashlib, json, sqlite3, gzip
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/'outputs/historical_gis_czech_lands_v06.gpkg'
GEOS={'judicial_1930':330,'judicial_1921':328,'political_1930':151,'political_1921':151}

def quoted(s):return '"'+s.replace('"','""')+'"'

def main():
 checks=[];inventory=[];details={}
 compressed=[]
 for folder in ['modules','outputs']:
  for path in sorted((ROOT/folder).rglob('*.gz')):
   size=0;error=''
   try:
    with gzip.open(path,'rb') as stream:
     while block:=stream.read(2**20):size+=len(block)
   except Exception as exc:error=repr(exc)
   compressed.append({'test':'complete_gzip_export','path':str(path.relative_to(ROOT)),
                      'status':'FAIL' if error else 'PASS','bytes_uncompressed':size,'detail':error})
 pd.DataFrame(compressed).to_csv(ROOT/'audit/gzip_exports_validation.csv',index=False)
 def check(name,ok,detail=''):
  checks.append({'test':name,'status':'PASS' if ok else 'FAIL','detail':str(detail)})
 with sqlite3.connect('file:'+str(DB)+'?mode=ro',uri=True) as c:
  check('sqlite_integrity',c.execute('PRAGMA integrity_check').fetchone()[0]=='ok')
  tables=c.execute('SELECT table_name,data_type FROM gpkg_contents').fetchall()
  ids={g:set(pd.read_sql_query('SELECT district_year_id FROM '+quoted(g),c).district_year_id) for g in GEOS}
  for g,n in GEOS.items():check('district_count_'+g,len(ids[g])==n,len(ids[g]))
  for table,kind in tables:
   columns=[r[1] for r in c.execute('PRAGMA table_info('+quoted(table)+')')]
   n=c.execute('SELECT COUNT(*) FROM '+quoted(table)).fetchone()[0]
   inventory.append({'table':table,'kind':kind,'rows':n,'columns':len(columns)})
   if 'district_year_id' in columns and 'geography' in columns:
    df=pd.read_sql_query('SELECT DISTINCT geography,district_year_id FROM '+quoted(table),c)
    unknown=[(r.geography,r.district_year_id) for r in df.itertuples() if r.geography not in ids or r.district_year_id not in ids[r.geography]]
    check('district_foreign_keys_'+table,not unknown,unknown[:5])
   if 'neighbor_district_year_id' in columns:
    df=pd.read_sql_query('SELECT DISTINCT geography,neighbor_district_year_id FROM '+quoted(table),c)
    check('neighbor_foreign_keys_'+table,all(r.neighbor_district_year_id in ids[r.geography] for r in df.itertuples()))
  dictionaries=pd.read_sql_query('SELECT * FROM gis_variable_dictionary',c)
  generic=pd.read_csv(ROOT/'audit/dictionary_original_fields.csv')
  new_generic=generic[generic.table.isin(GEOS)] if len(generic) else generic
  check('all_master_fields_have_specific_definitions',len(new_generic)==0,new_generic.to_dict('records'))
  for g in GEOS:
   cols={r[1] for r in c.execute('PRAGMA table_info('+quoted(g)+')')}-{'fid','geom'}
   check('complete_dictionary_'+g,set(dictionaries[dictionaries.table==g].variable)==cols)
  soil=pd.read_sql_query('SELECT * FROM gis_soil',c)
  for col,lo,hi in [('soil_clay_pct_0_30cm',0,100),('soil_sand_pct_0_30cm',0,100),('soil_silt_pct_0_30cm',0,100),('soil_coarse_fragments_vol_pct_0_30cm',0,100),('soil_ph_water_0_30cm',0,14),('soil_organic_carbon_g_kg_0_30cm',0,1000)]:
   check('physical_unit_range_'+col,soil[col].dropna().between(lo,hi).all())
  texture=soil[['soil_clay_pct_0_30cm','soil_sand_pct_0_30cm','soil_silt_pct_0_30cm']].sum(axis=1,min_count=3)
  check('soil_texture_components_total_with_rounding',texture.dropna().between(99.95,100.05).all(),[texture.min(),texture.max()])
  rail=pd.read_sql_query('SELECT geography,calendar_year,COUNT(*) n FROM gis_rail_annual GROUP BY geography,calendar_year',c)
  check('rail_balanced_all_years_geographies',len(rail)==4*38 and all(r.n==GEOS[r.geography] for r in rail.itertuples()) and set(rail.calendar_year)==set(range(1901,1939)))
  lu=pd.read_sql_query('SELECT geography,calendar_year,COUNT(*) n FROM gis_landuse GROUP BY geography,calendar_year',c)
  check('landuse_four_actual_source_years',len(lu)==16 and set(lu.calendar_year)=={1845,1948,1990,2000} and all(r.n==GEOS[r.geography] for r in lu.itertuples()))
  borders=pd.read_sql_query('SELECT snapshot_id,COUNT(*) n FROM gis_borders GROUP BY snapshot_id',c)
  check('borders_keep_distinct_1938_snapshots',len(borders)==5 and (borders.n==960).all())
  ref=pd.read_sql_query('SELECT * FROM csu_population_houses_reference LIMIT 1',c)
  check('municipal_2015_population_not_misjoined', 'district_year_id' not in ref.columns)
  unknown_years=c.execute('SELECT COUNT(*) FROM cz_retro_localities_reference WHERE historical_activity_year IS NOT NULL').fetchone()[0]
  check('gazetteer_unknown_activity_year_is_sql_null',unknown_years==0,unknown_years)
  semily=pd.read_sql_query("SELECT * FROM judicial_1930 WHERE NAZEV='Semily'",c).drop(columns=['geom','fid'],errors='ignore')
  check('semily_unique',len(semily)==1)
  semily.to_csv(ROOT/'outputs/Semily_1930_profile_v06.csv',index=False,encoding='utf-8-sig')
  details['semily']=json.loads(semily.to_json(orient='records'))[0]
  details['soil_main_districts_low_coverage']=int(soil.loc[soil.geography=='judicial_1930','soil_low_coverage_flag'].sum())
  details['main_columns']=len(semily.columns)
  details['source_components']=pd.read_sql_query('SELECT component,status FROM gis_source_catalog_v06',c).to_dict('records')
 for g,n in GEOS.items():
  path=ROOT/'outputs'/f'gis_annual_{g}_1901_1938_v06.csv.gz'
  df=pd.read_csv(path,usecols=['district_year_id','calendar_year'])
  check('combined_annual_unique_'+g,len(df)==n*38 and not df.duplicated().any())
 validation=pd.DataFrame(checks);validation.to_csv(ROOT/'audit/v06_integration_validation.csv',index=False)
 pd.DataFrame(inventory).to_csv(ROOT/'outputs/GIS_V06_TABLE_INVENTORY.csv',index=False)
 summary=[]
 for p in sorted((ROOT/'audit').glob('*validation.csv')):
  d=pd.read_csv(p)
  if 'status' in d:
   vc=d.status.str.upper().value_counts().to_dict()
  elif 'passed' in d:
   b=d.passed.astype(str).str.lower().isin(['true','1']);vc={'PASS':int(b.sum()),'FAIL':int((~b).sum())}
  else:continue
  summary.append({'file':p.name,**{k:int(vc.get(k,0)) for k in ['PASS','WARN','FAIL']}})
 for filename in ['v06_original_preservation.csv','soil_crs_equivalence.csv']:
  d=pd.read_csv(ROOT/'audit'/filename);b=d.passed.astype(str).str.lower().isin(['true','1'])
  summary.append({'file':filename,'PASS':int(b.sum()),'WARN':0,'FAIL':int((~b).sum())})
 audits=pd.DataFrame(summary);audits.to_csv(ROOT/'audit/V06_AUDIT_SUMMARY.csv',index=False)
 details['audit_by_file']=audits.to_dict('records')
 details['audit_totals']={k:int(audits[k].sum()) for k in ['PASS','WARN','FAIL']}
 (ROOT/'audit/v06_key_findings.json').write_text(json.dumps(details,ensure_ascii=False,indent=2))
 print(json.dumps({'audit_totals':details['audit_totals'],'main_columns':details['main_columns'],'soil_main_low_coverage':details['soil_main_districts_low_coverage']},ensure_ascii=False,indent=2),flush=True)
 assert validation.status.eq('PASS').all(),validation[validation.status!='PASS'].to_string()
 assert details['audit_totals']['FAIL']==0,audits.to_string()

if __name__=='__main__':main()
