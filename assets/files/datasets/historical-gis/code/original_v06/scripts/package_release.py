#!/usr/bin/env python3
"""Stage a self-contained research delivery and verify the complete ZIP."""
from pathlib import Path
import argparse, hashlib, json, shutil, zipfile
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT.parent/'deliverables'
STAGE=DEST/'GIS_Czech_Lands_v0_6_stage'
ARCHIVE=DEST/'GIS_Czech_Lands_v0_6.zip'
SOURCE_ARCHIVE=DEST/'GIS_Czech_Lands_v0_6_sources.zip'
SOURCE_FOLDERS={'inputs','modules','sources','history_v05'}

def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as stream:
  while block:=stream.read(2**20):h.update(block)
 return h.hexdigest()

def copy_file(src,dst):
 dst.parent.mkdir(parents=True,exist_ok=True)
 shutil.copy2(src,dst)

def copy_tree(src,dst,exclude=lambda p:False):
 for p in sorted(src.rglob('*')):
  hidden=any(part.startswith('.') and part not in {'.Rbuildignore','.gitignore','.github'} for part in p.relative_to(src).parts)
  if p.is_file() and not hidden and '__pycache__' not in p.parts and not exclude(p):copy_file(p,dst/p.relative_to(src))

def stage():
 DEST.mkdir(exist_ok=True);STAGE.mkdir(exist_ok=True)
 for name in ['inputs','outputs','modules','docs','scripts']:
  copy_tree(ROOT/name,STAGE/name,lambda p:p.name.endswith(('.part','-wal','-shm')) or '.building.' in p.name)
 copy_tree(ROOT/'audit',STAGE/'audit',lambda p:p.stat().st_size==0 or p.name.endswith('.part'))
 for filename in ['README_CZ.md','requirements.txt']:copy_file(ROOT/filename,STAGE/filename)
 # Whole regional original polygons and European topology are in modules/basins.
 # The complete 361 MB Europe archive and its expanded copies are not duplicated.
 for folder in (ROOT/'sources').iterdir():
  if not folder.is_dir():continue
  if folder.name=='basins':
   for p in folder.rglob('*'):
    if p.is_file() and p.suffix.lower() in ['.json','.pdf','.txt','.md']:copy_file(p,STAGE/'sources/basins'/p.relative_to(folder))
  elif folder.name=='soil':
   copy_file(folder/'acquisition_manifest.json',STAGE/'sources/soil/acquisition_manifest.json')
   # Composite 0-30cm rasters are derived from the retained three native
   # depths by build_soil.py; do not duplicate these reproducible outputs.
   copy_tree(folder/'regional',STAGE/'sources/soil/regional',lambda p:'0-30cm_depth_weighted' in p.name)
  else:copy_tree(folder,STAGE/'sources'/folder.name,lambda p:p.name.endswith('.part'))
 legacy=(ROOT/'history_v05' if (ROOT/'history_v05').exists()
         else ROOT.parent/'gis_work/GIS_v04_Preparation')
 for folder in ['inputs','docs','scripts','sources','cache/regional_sources','outputs/registry','outputs/spatial_weights','outputs/audit','outputs/wave2_completed']:
  copy_tree(legacy/folder,STAGE/'history_v05'/folder,
            lambda p:p.name=='historical_gis_czech_lands_v05.gpkg' or p.name.endswith(('.part','-wal','-shm')))
 for name in ['README_CZ.md','requirements.txt']:
  if (legacy/name).exists():copy_file(legacy/name,STAGE/'history_v05'/name)
 (STAGE/'history_v05/ARCHIVE_NOTE_CZ.md').write_text('''# Archiv předchozího vydání 0.5

Původní metodiky, historické vstupy, regionální zdroje, váhy a tabulky jsou zachovány jako podklady historie projektu. Jejich názvy a stavové příznaky odpovídají tehdejším verzím.

Celý nezměněný původní integrovaný GeoPackage je uložen v `../inputs/base_v05_inputs.gpkg`; z této složky se neduplikuje pod starým rozpoznávaným názvem. Aktuální hotový výstup je `../outputs/historical_gis_czech_lands_v06.gpkg`.

Velké globální zkušební stahované soubory nejsou duplikované. Zachované regionální klimatické a hydrologické hodnoty, původní adresy a SHA256 umožňují dohledat použité zdroje. Stejně je v novém modulu HydroBASINS uchován regionální originál a evropská topologie místo celého evropského ZIPu. SoilGrids zachovává přesné regionální pixely a úplný manifest původních dlaždic.
''',encoding='utf-8')
 rsource=ROOT/'r_package/histCzechia'
 copy_tree(rsource,STAGE/'r_package/histCzechia',lambda p:'.git' in p.parts or '.Rcheck' in str(p))
 rtar=ROOT/'r_package/histCzechia_0.2.0.tar.gz'
 if not rtar.exists():raise FileNotFoundError('R release archive is required before packaging: '+str(rtar))
 copy_file(rtar,STAGE/'r_package'/rtar.name)
 if (ROOT/'r_package/r_package_manifest.json').exists():
  copy_file(ROOT/'r_package/r_package_manifest.json',STAGE/'r_package/r_package_manifest.json')
 if (ROOT/'r_package/histCzechia_0_2_0_project.zip').exists():
  copy_file(ROOT/'r_package/histCzechia_0_2_0_project.zip',STAGE/'r_package/histCzechia_0_2_0_project.zip')
 manifest=json.loads((ROOT/'outputs/integrated_v06_manifest.json').read_text())
 assert sha(STAGE/'outputs'/manifest['filename'])==manifest['sha256']
 assert sha(STAGE/'inputs/base_v05_inputs.gpkg')==manifest['base_sha256']
 hashes={'core':[],'sources':[]}
 for p in sorted(STAGE.rglob('*')):
  rel=p.relative_to(STAGE)
  hidden=any(part.startswith('.') and part not in {'.Rbuildignore','.gitignore','.github'} for part in rel.parts)
  if p.is_file() and not hidden and not p.name.startswith('FILE_MANIFEST_'):
   group='sources' if rel.parts[0] in SOURCE_FOLDERS else 'core'
   hashes[group].append({'path':rel.as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
 for group,entries in hashes.items():
  pd.DataFrame(entries).to_csv(STAGE/f'FILE_MANIFEST_{group.upper()}_SHA256.csv',index=False)
 print(json.dumps({'stage':str(STAGE),'files':sum(len(v) for v in hashes.values())+2,
                   'bytes_uncompressed':sum(h['bytes'] for v in hashes.values() for h in v)},ensure_ascii=False),flush=True)

def archive():
 already_compressed={'.gz','.zip','.tif','.tiff','.png','.pdf'}
 reports=[]
 for group,target in [('core',ARCHIVE),('sources',SOURCE_ARCHIVE)]:
  manifest=STAGE/f'FILE_MANIFEST_{group.upper()}_SHA256.csv'
  files=[STAGE/p for p in pd.read_csv(manifest).path]+[manifest]
  tmp=target.with_suffix('.zip.part')
  with zipfile.ZipFile(tmp,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
   for i,p in enumerate(files,1):
    z.write(p,arcname='GIS_Czech_Lands_v0_6/'+p.relative_to(STAGE).as_posix(),
            compress_type=zipfile.ZIP_STORED if p.suffix.lower() in already_compressed else zipfile.ZIP_DEFLATED)
    if i%100==0:print('Archived',group,i,'/',len(files),flush=True)
  with zipfile.ZipFile(tmp) as z:
   assert z.testzip() is None,'CRC error in release archive'
   recognised=[n for n in z.namelist() if Path(n).name in ['historical_gis_czech_lands_v05.gpkg','historical_gis_czech_lands_v06.gpkg']]
   assert (group=='core' and len(recognised)==1 and recognised[0].endswith('_v06.gpkg')) or (group=='sources' and not recognised),recognised
  tmp.replace(target)
  report={'kind':group,'file':str(target),'bytes':target.stat().st_size,'sha256':sha(target),'entries':len(files),'zip_crc':'PASS','recognised_geopackages':len(recognised)}
  reports.append(report);print(json.dumps(report,indent=2),flush=True)
 (DEST/'GIS_v06_delivery_manifest.json').write_text(json.dumps({'archives':reports,'unpack_into_same_directory':True},indent=2))

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--stage-only',action='store_true');parser.add_argument('--zip-only',action='store_true');args=parser.parse_args()
 if not args.zip_only:stage()
 if not args.stage_only:archive()
