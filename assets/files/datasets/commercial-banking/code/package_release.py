#!/usr/bin/env python3
"""Package the public banking dataset and write its resource inventory.

Run after the data, workbook, guide and standalone-page builders have finished.
Uses only Python's standard library. Does not contact GitHub or publish files.
"""
from pathlib import Path
from io import BytesIO
import csv
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
STEM = 'Czechoslovak_Commercial_Banking_1919_1937'
VERSION = '0.1.0'
DATE = '2026-10-29'
PAGE_URL = 'https://adamdittrich.github.io/czechoslovak-commercial-banking.html'
REPO_URL = 'https://github.com/adamdittrich/adamdittrich.github.io/tree/main/assets/files/datasets/commercial-banking'
ARCHIVE_NAME = STEM + '_v' + VERSION + '.zip'


def main():
    required = [ROOT/'index.html', ROOT/(STEM+'.xlsx'),
                ROOT/'docs/Banking_Dataset_Guide.pdf',
                ROOT/'metadata/validation.json', ROOT/'metadata/release_counts.json']
    missing = [str(p.relative_to(ROOT)) for p in required if not p.is_file()]
    if missing:
        raise SystemExit('Finish the release build before packaging: '+', '.join(missing))
    validation = json.loads((ROOT/'metadata/validation.json').read_text())
    if validation.get('status') != 'pass':
        raise SystemExit('Data validation has not passed.')
    resources=[]
    for folder in ['data','metadata']:
        for path in sorted((ROOT/folder).glob('*.csv')):
            with path.open(encoding='utf-8-sig', newline='') as stream:
                rows=csv.reader(stream)
                columns=next(rows)
                count=sum(1 for _ in rows)
            data=path.read_bytes()
            resources.append({'name':path.stem, 'path':str(path.relative_to(ROOT)),
                              'format':'csv','encoding':'UTF-8','delimiter':',',
                              'rows':count,'columns':columns,'size_bytes':len(data),
                              'sha256':hashlib.sha256(data).hexdigest()})
    dataset={
        'title':'Czechoslovak Commercial Banking, 1919–1937',
        'subtitle':'Joint-stock banks in the Czech lands',
        'version':VERSION,
        'status':'public_release',
        'release_date':DATE,
        'url':PAGE_URL,
        'repository_url':REPO_URL,
        'creator':{'name':'Adam Dittrich','orcid':'https://orcid.org/0000-0002-7803-1339'},
        'primary_period':{'start_year':1919,'end_year':1937},
        'panel_period':{'start_year':1933,'end_year':1937},
        'scope':'Changing annual commercial-bank aggregate in Bohemia, Moravia and Silesia; separate fixed fourteen-bank handbook panel. Additional national roster, central-bank and price context retain distinct populations.',
        'observation_counts':json.loads((ROOT/'metadata/release_counts.json').read_text()),
        'license':None,
        'doi':None,
        'publication_note':'First public release. Cite the version and underlying sources. No additional reuse licence or DOI assigned. See docs/RELEASE_NOTES.txt.',
        'citation_file':'CITATION.cff',
        'guide':'docs/Banking_Dataset_Guide.pdf',
        'variable_dictionary':'metadata/variable_dictionary.csv',
        'resources':resources,
    }
    (ROOT/'dataset.json').write_text(json.dumps(dataset,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    files={}
    for path in sorted(ROOT.rglob('*')):
        if (not path.is_file() or '__pycache__' in path.parts
                or 'qa' in path.relative_to(ROOT).parts or path.name.startswith('.')
                or path.name.endswith('.inspect.ndjson')):
            continue
        if path.name=='SHA256SUMS.txt' or path.suffix in {'.pyc','.log','.zip'}:
            continue
        files[str(path.relative_to(ROOT))]=path.read_bytes()
    manifest=''.join(hashlib.sha256(value).hexdigest()+'  '+name+'\n'
                     for name,value in sorted(files.items()))
    (ROOT/'SHA256SUMS.txt').write_text(manifest,encoding='utf-8')
    files['SHA256SUMS.txt']=manifest.encode('utf-8')
    archive=BytesIO()
    prefix='czechoslovak_commercial_banking_'+VERSION+'/'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,value in sorted(files.items()):
            z.writestr(prefix+name,value)
    destination=ROOT/ARCHIVE_NAME
    content=archive.getvalue();destination.write_bytes(content)
    if destination.read_bytes()!=content:
        raise IOError('Incomplete archive write')
    with zipfile.ZipFile(destination) as z:
        assert z.testzip() is None
        assert not any(name.endswith('.zip') for name in z.namelist()), 'Nested release ZIP'
        for line in z.read(prefix+'SHA256SUMS.txt').decode().splitlines():
            expected,name=line.split('  ',1)
            assert hashlib.sha256(z.read(prefix+name)).hexdigest()==expected,name
    print(json.dumps({'archive':str(destination),'files':len(files),'bytes':len(content),
                      'csv_resources':len(resources),'manifest_verified':True,
                      'sha256':hashlib.sha256(content).hexdigest()},indent=2))


if __name__=='__main__':
    main()
