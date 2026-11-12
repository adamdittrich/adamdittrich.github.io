#!/usr/bin/env python3
"""Validate the encrypted Romania release and prevent plaintext publication."""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'assets/files/datasets/romania-protected'
checksums = json.loads((ROOT / PREFIX / 'checksums.json').read_text())
if 'vault.bin' not in checksums or len(checksums) < 5:
    raise SystemExit('Incomplete encrypted Romania release.')
for base in (ROOT, ROOT / 'docs'):
    sealed = base / PREFIX
    config = json.loads((sealed / 'config.json').read_text())
    assert config['cipher'] == 'AES-GCM' and config['kdf']['iterations'] >= 1_000_000
    assert config['compression'] == 'gzip' and config['manifest'] == 'vault.bin'
    actual = {p.name for p in sealed.glob('*.bin')}
    assert actual == set(checksums), 'Unexpected or missing encrypted resources'
    for name, digest in checksums.items():
        assert re.fullmatch(r'(vault|p_[a-f0-9]{24})\.bin', name)
        raw = (sealed / name).read_bytes()
        assert len(raw) > 28 and hashlib.sha256(raw).hexdigest() == digest, name
    for forbidden in ('assets/files/datasets/romania', 'data_sources/romania', 'romania_private'):
        assert not (base / forbidden).exists(), 'Private source exposed: ' + forbidden
    for path in (base / 'assets/files/datasets').rglob('*'):
        assert not (path.is_file() and path.name.startswith('Romania_Interwar_')), 'Plaintext download exposed'
page = (ROOT / 'docs/romania-interwar.html').read_text()
assert 'noindex, nofollow, noarchive' in page
assert 'romania-access.js' in page and 'romania-access-form' in page
assert 'id="romania-private-root" hidden' in page
print(f'Validated encrypted Romania release: {len(checksums)} protected resources.')
