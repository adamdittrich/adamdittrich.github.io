#!/usr/bin/env python3
"""Verify presentation consistency and preservation of the original research data.

Run from any directory: python code/verify_presentation.py
The original ZIP, when present alongside this release, is checked against its
published SHA256 and used for byte-level data and workbook comparisons.
"""
from pathlib import Path
from io import BytesIO
import base64
import csv
import hashlib
import json
import re
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
STEM = 'Czechoslovak_Commercial_Banking_1919_1937'
ORIGINAL_SHA256 = '60fa210f7118049cb65b33330be3fe8ad51d19f0008003973a7bc2dafffc214d'
PALETTE = json.loads((ROOT/'code/chart_palette.json').read_text())

def payload(text):
    return json.loads(re.search(r'<script id="dataset-payload" type="application/json">(.*?)</script>', text, re.S)[1])

def colors(text):
    definition = re.search(r'const CHART_COLORS=\{(.*?)\};', text)[1]
    return dict(re.findall(r"(\w+):'([^']+)'", definition))

def series(text):
    return [re.search(r'const '+name+r'=\[(.*?)\];', text)[1] for name in ('ANNUAL_SERIES', 'INCOME_SERIES')]

def workbook_cells(content):
    ns={'x':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    result={}
    with zipfile.ZipFile(BytesIO(content)) as z:
        for name in z.namelist():
            if name.startswith('xl/worksheets/sheet') and name.endswith('.xml'):
                result[name]={c.attrib['r']:(c.attrib.get('t'),c.findtext('x:f', namespaces=ns),c.findtext('x:v', namespaces=ns))
                              for c in ET.fromstring(z.read(name)).findall('.//x:c',ns)}
    return result

def main():
    template=(ROOT/'code/preview_template.html').read_text()
    html=(ROOT/'index.html').read_text()
    data=payload(html)
    assert data['version']=='0.1.1' and data['date']=='2026-11-01'
    assert colors(template)==PALETTE==colors(html)
    assert template.replace('/*__EMBEDDED_DATA__*/',re.search(r'<script id="dataset-payload" type="application/json">(.*?)</script>',html,re.S)[1])==html
    for path,text in data['files'].items():
        assert text==(ROOT/path).read_text(encoding='utf-8-sig'),path
    for path,info in data['binaries'].items():
        assert base64.b64decode(info['base64'])==(ROOT/path).read_bytes(),path
    for name in ('annual_aggregate','bank_panel'):
        with (ROOT/'data'/f'{name}.csv').open(encoding='utf-8-sig',newline='') as f:
            assert data['tables'][name]==list(csv.DictReader(f)),name
    # The host repository is optional: an extracted ZIP works independently.
    site=ROOT.parents[3]
    if (site/'assets/js/commercial-banking.js').exists():
        web=(site/'assets/js/commercial-banking.js').read_text()
        assert colors(web)==PALETTE and series(web)==series(template)
        page=payload((site/'czechoslovak-commercial-banking.qmd').read_text())
        assert page['tables']==data['tables'] and page['version']==data['version']
    original=ROOT/(STEM+'_v0.1.0.zip')
    checked=0
    if original.exists():
        assert hashlib.sha256(original.read_bytes()).hexdigest()==ORIGINAL_SHA256
        with zipfile.ZipFile(original) as z:
            prefix='czechoslovak_commercial_banking_0.1.0/'
            for name in z.namelist():
                rel=name.removeprefix(prefix)
                if rel.startswith(('data/','inputs/')) or rel.startswith('metadata/') and rel.endswith('.csv'):
                    assert z.read(name)==(ROOT/rel).read_bytes(),rel
                    checked+=1
            before=workbook_cells(z.read(prefix+STEM+'.xlsx'))
            after=workbook_cells((ROOT/(STEM+'.xlsx')).read_bytes())
            for cells in before.values():
                for address,(kind,formula,value) in cells.items():
                    if kind=='str' and value:
                        cells[address]=(kind,formula,value.replace('0.1.0','0.1.1').replace('29 October 2026','1 November 2026'))
            assert before==after,'Workbook values or formulas changed beyond release labels'
            for name in ('release_counts','validation'):
                old=json.loads(z.read(prefix+'metadata/'+name+'.json'))
                new=json.loads((ROOT/'metadata'/f'{name}.json').read_text())
                for key in ('version','release_date'):
                    old.pop(key);new.pop(key)
                assert old==new,name
    with zipfile.ZipFile(ROOT/(STEM+'.xlsx')) as z:
        ns={'c':'http://schemas.openxmlformats.org/drawingml/2006/chart', 'a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
        charts=[n for n in z.namelist() if '/charts/chart' in n and n.endswith('.xml')]
        assert len(charts)==2
        for name in charts:
            s=ET.fromstring(z.read(name)).findall('.//c:ser',ns)
            assert len(s)==3
            for item,key in zip(s,('blue','orange','green')):
                rgb=item.find('.//a:srgbClr',ns).attrib['val']
                assert rgb.lower()==PALETTE[key][1:]
    for line in (ROOT/'SHA256SUMS.txt').read_text().splitlines():
        expected,name=line.split('  ',1)
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected,name
    archive=ROOT/(STEM+'_v0.1.1.zip')
    if archive.exists():
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
            prefix='czechoslovak_commercial_banking_0.1.1/'
            for name in z.namelist():
                assert z.read(name)==(ROOT/name.removeprefix(prefix)).read_bytes(),name
    print(json.dumps({'status':'pass','unchanged_original_files':checked,'offline_payload_and_downloads':'pass','chart_palette':'pass','workbook_cells_and_formulas':'pass','archive_and_manifest':'pass'}))

if __name__=='__main__':
    main()
