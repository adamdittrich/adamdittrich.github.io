#!/usr/bin/env python3
"""Validate the encrypted Italy release and prevent plaintext publication.

Use --source-only before rendering to check the public source checkout. The
default checks both source and rendered output; no password is needed in CI.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'assets/files/datasets/italy-protected'


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-only', action='store_true')
    args = parser.parse_args()
    checksums = json.loads((ROOT / PREFIX / 'checksums.json').read_text(encoding='utf-8'))
    require(isinstance(checksums, dict) and 'vault.bin' in checksums and len(checksums) >= 5,
            'Incomplete encrypted Italy release.')
    source_config = json.loads((ROOT / PREFIX / 'config.json').read_text(encoding='utf-8'))
    bases = (ROOT,) if args.source_only else (ROOT, ROOT / 'docs')
    for base in bases:
        sealed = base / PREFIX
        config = json.loads((sealed / 'config.json').read_text(encoding='utf-8'))
        require(config == source_config, 'The rendered Italy access configuration differs from source.')
        require(config.get('version') == 1 and config.get('cipher') == 'AES-GCM',
                'Unsupported Italy encryption configuration.')
        require(config.get('compression') == 'gzip' and config.get('manifest') == 'vault.bin',
                'Incorrect Italy vault configuration.')
        require(config.get('aadPrefix') == 'adamdittrich-italy-v1/', 'Incorrect Italy authentication prefix.')
        kdf = config.get('kdf', {})
        require(kdf.get('name') == 'PBKDF2' and kdf.get('hash') == 'SHA-256' and
                isinstance(kdf.get('iterations'), int) and 1_000_000 <= kdf['iterations'] <= 2_000_000,
                'Incorrect Italy password-derivation configuration.')
        require(len(base64.b64decode(kdf.get('salt', ''), validate=True)) == 32, 'Incorrect Italy salt.')
        require({p.name for p in sealed.iterdir()} == set(checksums) | {'config.json', 'checksums.json'},
                'Unexpected or missing encrypted Italy resources.')
        require(json.loads((sealed / 'checksums.json').read_text(encoding='utf-8')) == checksums,
                'The rendered Italy checksum list differs from source.')
        for name, digest in checksums.items():
            require(bool(re.fullmatch(r'(vault|p_[a-f0-9]{24})\.bin', name)),
                    'Invalid encrypted Italy resource name.')
            require(isinstance(digest, str) and bool(re.fullmatch(r'[a-f0-9]{64}', digest)),
                    'Invalid Italy SHA-256 digest.')
            raw = (sealed / name).read_bytes()
            require(len(raw) > 28 and hashlib.sha256(raw).hexdigest() == digest,
                    'Encrypted Italy resource is corrupt: ' + name)
        for forbidden in ('assets/files/datasets/italy', 'data_sources/italy', 'italy_private', 'italy-private'):
            require(not (base / forbidden).exists(), 'Private Italy source exposed: ' + forbidden)
        for folder in (base / 'assets', base / 'data_sources'):
            if folder.exists():
                for path in folder.rglob('*'):
                    require(not (path.is_file() and path.name.startswith('Italy_Interwar_')),
                            'Plaintext Italy download exposed: ' + path.name)
        controller = base / 'assets/js/italy-access.js'
        require(controller.is_file(), 'Italy access controller is missing.')

    page = (ROOT / ('italy-interwar.qmd' if args.source_only else 'docs/italy-interwar.html')).read_text(encoding='utf-8')
    require('noindex, nofollow, noarchive' in page, 'Italy page lacks its indexing exclusion.')
    require('italy-access.js' in page and 'italy-access-form' in page, 'Italy password form is missing.')
    require('id="italy-private-root" hidden' in page, 'Italy content root is not initially hidden.')
    require('data-asset=' not in page and 'window.ITALY_DATA' not in page,
            'Private Italy content appears in the public password page.')
    print(f'Validated encrypted Italy release: {len(checksums)} protected resources'
          + (' (source only).' if args.source_only else ' (source and rendered output).'))


if __name__ == '__main__':
    main()
