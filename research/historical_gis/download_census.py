#!/usr/bin/env python3
"""Download all ORIGINAL census attributes for 1921 and 1930 judicial districts.
Uses source ArcGIS FeatureServer directly, preserving raw column names and nulls.
"""
import json, datetime, pathlib, csv, requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT=pathlib.Path("results/census_raw");ROOT.mkdir(parents=True,exist_ok=True)
BASE="https://services1.arcgis.com/LPm07959azIAvFRD/ArcGIS/rest/services/"
S=requests.Session();S.mount("https://", HTTPAdapter(max_retries=Retry(total=5,backoff_factor=.7,status_forcelist=[429,500,502,503,504])))
S.headers["User-Agent"]="Interwar-Czech-census-GIS-research contact via historicalgis.cz"
def fetch(u,**p):
 r=S.get(u,params=p,timeout=(20,120))
 r.raise_for_status()
 obj=r.json()
 if "error" in obj:raise RuntimeError(str(obj["error"]))
 return obj
manifest={"downloaded_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
 "source":"Urbanni a regionalni laborator historical census ArcGIS FeatureServer",
 "scope":"Czech lands ONLY; 1921 and 1930 judicial districts, not all interwar Czechoslovakia",
 "layers":{}}
for year in (1921,1930):
 layer=f"{BASE}Okresy_Ceska_{year}/FeatureServer/0"
 meta=fetch(layer,f="json")
 fields=meta["fields"]
 ids=fetch(layer+"/query",where="1=1",returnIdsOnly="true",f="json")["objectIds"]
 rows=[]
 for k in range(0,len(ids),40):
  ret=fetch(layer+"/query",objectIds=",".join(map(str,ids[k:k+40])),
   outFields="*",returnGeometry="false",f="json")
  rows.extend(f["attributes"] for f in ret["features"])
 cols=[field["name"] for field in fields]
 # Ensure reproducibility, uniqueness, round trip fidelity
 idkey=meta["objectIdField"]
 found=[a[idkey] for a in rows]
 assert len(rows)==len(ids)==len(set(found)),(year,len(rows),len(ids))
 assert set(found)==set(ids)
 assert len(cols)>=75, (year,len(cols))
 assert all(set(a).issubset(set(cols)) for a in rows)
 output=ROOT/f"source_census_judicial_{year}_all_columns.csv"
 with output.open("w",encoding="utf-8-sig",newline="") as fp:
  w=csv.DictWriter(fp,fieldnames=cols,extrasaction="ignore")
  w.writeheader();w.writerows(sorted(rows,key=lambda v:v[idkey]))
 (ROOT/f"source_fields_judicial_{year}.json").write_text(json.dumps(fields,indent=2,ensure_ascii=False),encoding="utf-8")
 manifest["layers"][str(year)]={"url":layer,"n_features":len(rows),"n_fields":len(cols),
  "columns":cols,"source_objectid":idkey,"description":meta.get("description","")[:1100]}
 print(year,len(rows),len(cols),"fields",flush=True)
(ROOT/"source_census_manifest.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding="utf-8")
