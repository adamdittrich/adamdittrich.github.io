"""Create a public collection of district results from the original GIS v0.6.

Provider source geometries are omitted. CRU columns are kept in their independent
climate tables, rather than blended into the wide contextual district tables.
The original input is never changed. Rail corrections are supplied explicitly.
"""
from pathlib import Path
import argparse,csv,gzip,hashlib,json,os,shutil,sqlite3,tempfile
import pandas as pd

GEOS=['judicial_1930','judicial_1921','political_1930','political_1921']

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()

def verified_copy(source,destination):
    """Publish only closed, complete bytes, even on a mounted destination."""
    source,destination=Path(source),Path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    staging=destination.with_name(destination.name+'.complete')
    with source.open('rb') as reader,staging.open('wb') as writer:
        shutil.copyfileobj(reader,writer,8*1024*1024)
        writer.flush();os.fsync(writer.fileno())
    if source.stat().st_size!=staging.stat().st_size or sha256(source)!=sha256(staging):
        raise IOError('Incomplete artifact transfer: '+str(destination))
    os.replace(staging,destination)

def verify_gzip(path):
    with gzip.open(path,'rb') as stream:
        while stream.read(8*1024*1024):pass

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--rail-correction',type=Path,required=True)
    p.add_argument('--atlas-two',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--database-output',type=Path,required=True)
    a=p.parse_args();destination=a.output
    # Assemble every streamed export on local storage before publishing it.
    workdir=Path(tempfile.mkdtemp(prefix='gis_public_sqlite_'))
    out=workdir/'assets';data=out/'data';docs=out/'docs';audit=out/'audit'
    for folder in [data,docs,audit,a.database_output.parent]:folder.mkdir(parents=True,exist_ok=True)
    original=a.source/'outputs/historical_gis_czech_lands_v06.gpkg'
    original_sha=sha256(original)
    assert original.resolve()!=a.database_output.resolve()
    # Keep random-access SQLite transactions on a local temporary filesystem;
    # copy the closed, validated database to the deliverable destination once.
    working_db=workdir/a.database_output.name
    verified_copy(original,working_db)
    con=sqlite3.connect(working_db)
    con.execute('PRAGMA foreign_keys=OFF')
    rows=con.execute('SELECT table_name,data_type FROM gpkg_contents').fetchall()
    keep_features=set(GEOS+['cru_grid_cells'])
    removed=[t for t,k in rows if k=='features' and t not in keep_features]
    for t in removed:
        cols=[r[1] for r in con.execute('PRAGMA table_info("'+t+'")')]
        gc=con.execute('SELECT column_name FROM gpkg_geometry_columns WHERE table_name=?',(t,)).fetchone()
        if gc:
            rtree='rtree_'+t+'_'+gc[0]
            con.execute('DROP TABLE IF EXISTS "'+rtree+'"')
        con.execute('DROP TABLE "'+t+'"')
        for meta in ['gpkg_geometry_columns','gpkg_extensions','gpkg_contents']:
            if con.execute("SELECT 1 FROM sqlite_master WHERE name=?",(meta,)).fetchone():
                con.execute('DELETE FROM "'+meta+'" WHERE table_name=?',(t,))
    # Preserve spatial-index triggers verbatim while updating non-geometric attributes.
    triggers=[]
    for g in GEOS:
        for name,sql in con.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name=?",(g,)).fetchall():
            triggers.append((name,sql));con.execute('DROP TRIGGER "'+name+'"')
    rail=pd.read_csv(a.rail_correction/'gis_rail_annual_v061.csv.gz')
    old_rail=pd.read_sql_query('SELECT * FROM gis_rail_annual',con)
    assert len(rail)==len(old_rail)==36480
    cols=list(old_rail.columns)
    assert set(cols)==set(rail.columns)
    con.execute('DELETE FROM gis_rail_annual')
    rail[cols].to_sql('gis_rail_annual',con,if_exists='append',index=False)
    links=pd.read_csv(a.rail_correction/'rail_district_source_links_v061.csv.gz')
    oldcols=[r[1] for r in con.execute('PRAGMA table_info(rail_district_source_links)')]
    con.execute('DELETE FROM rail_district_source_links')
    links[oldcols].to_sql('rail_district_source_links',con,if_exists='append',index=False)
    masters={};normal_parts=[];verification=[]
    for g in GEOS:
        original_master=pd.read_csv(a.source/f'outputs/gis_master_{g}_v06.csv')
        m=original_master.set_index('district_year_id').copy()
        r=pd.read_csv(a.rail_correction/f'gis_rail_static_{g}_v061.csv').set_index('district_year_id')
        for col in r:
            if col in m and col.startswith('rail_'):m[col]=r[col]
        climate_cols=[c for c in m if c.startswith('clim_normal_')]
        assert len(climate_cols)==18
        source_normals=pd.read_sql_query('SELECT * FROM gis_climate_normals WHERE geography=?',con,params=[g]).set_index('district_year_id')
        for col in climate_cols:
            pd.testing.assert_series_equal(m[col].sort_index(),source_normals[col].sort_index(),check_names=False,check_dtype=False)
        # Split the published CSVs by independent source component.
        normals=m[climate_cols].reset_index();normals.insert(0,'geography',g)
        normals.to_csv(data/f'climate_normals_{g}.csv',index=False)
        normal_parts.append(normals)
        core=m.drop(columns=climate_cols)
        core.reset_index().to_csv(data/f'gis_master_{g}_public_v061.csv',index=False)
        masters[g]=m
        for col in climate_cols:con.execute('ALTER TABLE "'+g+'" DROP COLUMN "'+col+'"')
        rail_cols=[c for c in r if c in core and c.startswith('rail_')]
        sql='UPDATE "'+g+'" SET '+','.join('"'+c+'"=?' for c in rail_cols)+' WHERE district_year_id=?'
        payload=[]
        for id,row in r.iterrows():
            payload.append(tuple(None if pd.isna(row[c]) else row[c].item() if hasattr(row[c],'item') else row[c] for c in rail_cols)+(id,))
        con.executemany(sql,payload)
        # Re-export annual contextual data without repeated CRU normal columns.
        annual=pd.read_csv(a.source/f'outputs/gis_annual_{g}_1901_1938_v06.csv.gz')
        rr=rail[rail.geography.eq(g)].set_index(['district_year_id','calendar_year'])
        annual=annual.set_index(['district_year_id','calendar_year'])
        for col in rr:
            if col in annual and col.startswith('rail_'):annual[col]=rr[col]
        for col in rail_cols:
            if col in annual:annual[col]=annual.index.get_level_values('district_year_id').map(r[col])
        # Separate annual CRU variables from repeated contextual fields as well.
        ca=pd.read_sql_query('SELECT * FROM gis_climate_annual WHERE geography=?',con,params=[g])
        climate_annual_cols=[c for c in ca if c not in ['geography','district_year_id','boundary_year','calendar_year']]
        contextual=annual.drop(columns=[c for c in climate_cols+climate_annual_cols if c in annual]).reset_index()
        contextual.to_csv(data/f'gis_annual_context_{g}_1901_1938_v061.csv.gz',index=False,compression={'method':'gzip','mtime':0})
        verification.append({'geography':g,'rows':len(core),'source_fields':len(original_master.columns),'core_fields':len(core.columns)+1,'separate_climate_fields':18,'annual_rows':len(contextual)})
    for name,sql in triggers:con.execute(sql)
    # New flags preserve source values while making the newer audit findings queryable.
    flags=[]
    def flag(g,id,module,code,severity,start,end,note,url=''):
        flags.append(dict(geography=g,district_year_id=id,module=module,flag_code=code,severity=severity,year_start=start,year_end=end,note=note,source_url=url))
    main=masters['judicial_1930']
    for id in ['CZ1930-J-30077','CZ1930-J-30300','CZ1930-J-30298']:
        flag('judicial_1930',id,'census','area_disagreement','warning',1930,1930,'Historical reported area and GIS polygon area differ by over 10% and 5 km²; territorial equivalence needs checking.')
    for id in ['CZ1930-J-30162','CZ1930-J-30331']:
        flag('judicial_1930',id,'employment','economic_counts_unverified','hold',1930,1930,'Trade/finance source counts await independent archival verification. Original values retained; employment previews withheld.')
    for id in ['CZ1930-J-30247','CZ1930-J-30245']:
        flag('judicial_1930',id,'elections','brno_election_territory_unresolved','hold',1929,1935,'Judicial census territory differs from the apparent electoral city/rural grouping. Original counts retained; vote previews withheld. Census population is confirmed by the1935lexicon.','https://librinostri.catholica.cz/download/StatLexZemMorSlez1935-r0.pdf')
    for g,m in masters.items():
        low=m[[c for c in ['soil_clay_0_30cm_coverage_fraction','soil_sand_0_30cm_coverage_fraction','soil_silt_0_30cm_coverage_fraction'] if c in m]].min(axis=1).lt(.9)
        for id in m.index[low]:flag(g,id,'soil','texture_coverage_below_90pct','warning',None,None,'Less than90% valid area for one or more soil textures. Raw model aggregates retained; conservative texture preview withheld.')
        if 'age_1921_remapped_by_sex_population' in m:
            for id in m.index[m.age_1921_remapped_by_sex_population.eq(1)]:
                flag(g,id,'census_age','age_1921_remapped','warning',1921,1921,'Age categories were assigned using the documented sex/population crosswalk; this is not a new archival validation.')
    for g,id in [('judicial_1930','CZ1930-J-30294'),('judicial_1921','CZ1921-J-21294'),('political_1930','CZ1930-P-302923'),('political_1921','CZ1921-P-212923')]:
        flag(g,id,'rail','opening_1937_corrected','corrected',1928,1937,'Horní Lideč–Púchov opening corrected from1928 to1937. All district distances and unions recomputed; source chronologies preserved in provenance.')
    f=pd.DataFrame(flags);f.to_sql('publication_quality_flags',con,if_exists='replace',index=False)
    f.to_csv(data/'publication_quality_flags.csv',index=False)
    def register(t):
        con.execute("INSERT OR REPLACE INTO gpkg_contents(table_name,data_type,identifier,description,last_change) VALUES(?,'attributes',?,?,?)",(t,t,'Public edition0.6.1 metadata','2026-11-04T00:00:00.000Z'))
    register('publication_quality_flags')
    components=[]
    for t,k in con.execute('SELECT table_name,data_type FROM gpkg_contents').fetchall():
        group='climate' if t.startswith(('gis_climate','gis_cru','cru_grid')) else 'contextual_collection'
        terms='ODbL1.0 and DatabaseContentsLicense; CRU/UEA attribution' if group=='climate' else 'Source-specific terms; see docs/SOURCES_AND_REUSE.md. No blanket data licence.'
        components.append(dict(table_name=t,component=group,terms=terms,raw_provider_geometries_redistributed=0))
    pd.DataFrame(components).to_sql('gis_publication_components',con,if_exists='replace',index=False);register('gis_publication_components')
    con.execute("UPDATE gis_release_metadata SET value='0.6.1' WHERE key='release'")
    for k,v in {'publication_date':'2026-11-04','edition':'public collection of independent source components','source_v06_sha256':original_sha,'core_1930_fields':'444','separate_cru_normals_fields':'18','rail_chronology_patch':'UPOL2023-58:1937; all1928–1937 districts recomputed','provider_source_geometry_layers_omitted':json.dumps(removed)}.items():
        con.execute('DELETE FROM gis_release_metadata WHERE key=?',(k,));con.execute('INSERT INTO gis_release_metadata(key,value) VALUES(?,?)',(k,v))
    # Public dictionary describes only present tables/fields; original source dictionary remains separately downloadable.
    dd=pd.read_sql_query('SELECT * FROM gis_variable_dictionary',con)
    table_col='table' if 'table' in dd else 'table_name'
    variable_col='variable' if 'variable' in dd else 'column_name'
    available={t:{r[1] for r in con.execute('PRAGMA table_info("'+t+'")')} for t, in con.execute('SELECT table_name FROM gpkg_contents').fetchall()}
    dd=dd[[str(row[table_col]) in available and str(row[variable_col]) in available[str(row[table_col])] for _,row in dd.iterrows()]]
    con.execute('DELETE FROM gis_variable_dictionary');dd.to_sql('gis_variable_dictionary',con,if_exists='append',index=False)
    dd.to_csv(data/'GIS_PUBLIC_DATA_DICTIONARY.csv',index=False)
    con.commit();con.execute('VACUUM');con.commit()
    assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    inventory=[]
    for t,k in con.execute('SELECT table_name,data_type FROM gpkg_contents').fetchall():
        count=con.execute('SELECT count(*) FROM "'+t+'"').fetchone()[0]
        ncols=len(con.execute('PRAGMA table_info("'+t+'")').fetchall())
        inventory.append(dict(table=t,kind=k,rows=count,columns=ncols))
        if k=='attributes' and not t.startswith('gis_source_'):
            # Every analysis table is also accessible without GIS software.
            dest=data/(t+'.csv.gz')
            first=True
            with gzip.GzipFile(dest,'wb',mtime=0) as gz:
                for chunk in pd.read_sql_query('SELECT * FROM "'+t+'"',con,chunksize=30000):
                    gz.write(chunk.to_csv(index=False,header=first).encode('utf-8'));first=False
    # Dedicated primary-geography climate files for convenient direct reuse.
    for g in GEOS:
        for kind in ['monthly','annual']:
            t='gis_climate_'+kind
            x=pd.read_sql_query('SELECT * FROM '+t+' WHERE geography=?',con,params=[g])
            x.to_csv(data/f'climate_{kind}_{g}.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    con.close()
    for suffix in ['-journal','-wal','-shm']:
        a.database_output.with_name(a.database_output.name+suffix).unlink(missing_ok=True)
    verified_copy(working_db,a.database_output)
    # Reopen the delivered bytes independently; an assembly-connection check
    # alone cannot detect a truncated final transfer.
    with sqlite3.connect('file:'+str(a.database_output.resolve())+'?mode=ro',uri=True) as check:
        assert check.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not check.execute('PRAGMA foreign_key_check').fetchall()
    assert sha256(original)==original_sha
    pd.DataFrame(inventory).to_csv(data/'GIS_PUBLIC_TABLE_INVENTORY.csv',index=False)
    shutil.copy2(a.source/'outputs/GIS_V06_DICTIONARY_judicial_1930.csv',data/'GIS_SOURCE_DICTIONARY_judicial_1930.csv')
    for name in ['RAIL_CORRECTION_V061.json','rail_recomputation_validation.csv','rail_changed_cells_v061.csv']:
        shutil.copy2(a.rail_correction/name,audit/name)
    for name in ['BRNO_TERRITORIAL_COMPARABILITY_EVIDENCE.json']:
        shutil.copy2(a.atlas_two/'provenance'/name,audit/name)
    result=dict(version='0.6.1',date='2026-11-04',source_sha256=original_sha,public_gpkg_name=a.database_output.name,
        public_gpkg_sha256=sha256(a.database_output),public_gpkg_bytes=a.database_output.stat().st_size,
        geographies=verification,table_count=len(inventory),removed_provider_geometry_layers=removed,
        public_quality_flag_rows=len(f),integrity_check='ok',foreign_key_check='ok',closed_copy_verified=True,original_unchanged=True)
    (out/'release_manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    for source in sorted(out.rglob('*')):
        if source.is_file():
            if source.suffix=='.gz':verify_gzip(source)
            target=destination/source.relative_to(out)
            verified_copy(source,target)
            if target.suffix=='.gz':verify_gzip(target)
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
