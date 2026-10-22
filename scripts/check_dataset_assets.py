#!/usr/bin/env python3
"""Reject modified downloads, broken Excel archives or malformed dataset SVGs."""
from pathlib import Path
import hashlib
import json
import zipfile
import xml.etree.ElementTree as ET
ROOT = Path(__file__).resolve().parents[1]
for base in (ROOT / 'assets/files/datasets', ROOT / 'docs/assets/files/datasets'):
    manifest = json.loads((base / 'checksums.json').read_text(encoding='utf-8'))
    for name, expected in manifest.items():
        data = (base / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise SystemExit(f'Dataset checksum mismatch: {base / name}')
        if name.endswith(('.xlsx','.zip')):
            with zipfile.ZipFile(base / name) as z:
                bad = z.testzip()
                if bad:
                    raise SystemExit(f'Corrupt archive member: {name}: {bad}')
        if name.endswith('.svg'):
            root = ET.fromstring(data)
            if not root.tag.endswith('svg'):
                raise SystemExit(f'Invalid SVG: {name}')
    print(f'Validated {len(manifest)} dataset assets in {base}')
