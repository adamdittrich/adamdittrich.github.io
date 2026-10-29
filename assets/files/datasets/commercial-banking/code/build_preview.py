#!/usr/bin/env python3
"""Build a self-contained, offline research-data page from this release's CSVs.

Run: python code/build_preview.py
No network access, repository changes or publication is performed.
The page embeds CSV observations and downloads; missing files are not advertised.
"""
from __future__ import annotations
import argparse
import base64
import csv
import hashlib
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RELEASE = ROOT if (ROOT / 'data' / 'annual_aggregate.csv').exists() else ROOT / 'release'

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--release', type=Path, default=DEFAULT_RELEASE)
    p.add_argument('--qa-dir', help='Optional directory for build diagnostics outside the release')
    args = p.parse_args()
    release = args.release.resolve()
    files, tables, audit = {}, {}, {}
    for folder in ('data', 'metadata'):
        for path in sorted((release / folder).glob('*.csv')):
            text = path.read_text(encoding='utf-8-sig')
            rel = path.relative_to(release).as_posix()
            rows = list(csv.DictReader(io.StringIO(text)))
            files[rel] = text
            tables[path.stem] = rows
            audit[rel] = {'rows': len(rows), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    for name, count in (('annual_aggregate', 19), ('bank_panel', 70)):
        if name not in tables:
            raise SystemExit(f'Missing release/data/{name}.csv. Build the data release first.')
        if len(tables[name]) != count:
            raise SystemExit(f'{name}: expected {count} rows, found {len(tables[name])}')
    supplements = {p.relative_to(release).as_posix(): p.read_text(encoding='utf-8')
                   for p in sorted((release / 'metadata').glob('*.json'))}
    binaries = {}
    for path in sorted(release.glob('*.xlsx')):
        binaries[path.name] = {'mime': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'base64': base64.b64encode(path.read_bytes()).decode('ascii')}
    for path in sorted(release.rglob('*.pdf')):
        if 'codebook' in path.name.lower() or path.name == 'Banking_Dataset_Guide.pdf':
            binaries[path.relative_to(release).as_posix()] = {'mime': 'application/pdf', 'base64': base64.b64encode(path.read_bytes()).decode('ascii')}
    # Only the two visualized cores need parsed JSON. All other original CSVs
    # remain downloadable without duplicating their contents as JSON objects.
    payload = {'tables': {k: tables[k] for k in ('annual_aggregate', 'bank_panel')},
               'counts': {k: len(v) for k, v in tables.items()},
               'files': files, 'supplements': supplements, 'binaries': binaries,
               'version': '0.1.0', 'date': '2026-10-29'}
    json_text = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    template = (Path(__file__).parent / 'preview_template.html').read_text(encoding='utf-8')
    if template.count('/*__EMBEDDED_DATA__*/') != 1:
        raise SystemExit('Expected exactly one data placeholder in template.')
    html = template.replace('/*__EMBEDDED_DATA__*/', json_text)
    (release / 'index.html').write_text(html, encoding='utf-8')
    qa_path = Path(args.qa_dir).resolve() if args.qa_dir else release.parent / 'banking-build-qa'
    qa_path.mkdir(parents=True, exist_ok=True)
    (qa_path / 'preview_build.json').write_text(json.dumps({'embedded_csvs': audit, 'embedded_binary_names': list(binaries), 'html_bytes': len(html.encode('utf-8')), 'no_external_runtime_dependencies': True}, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(release / 'index.html'), 'bytes': len(html.encode('utf-8')), 'tables': len(tables), 'embedded_binaries': list(binaries)}, indent=2))

if __name__ == '__main__':
    main()
