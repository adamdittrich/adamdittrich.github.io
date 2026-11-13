#!/usr/bin/env python3
"""Update an existing encrypted Romania portal without republishing unchanged files.

Usage: python scripts/update_romania.py PRIVATE_DIR SITE_DIR \
    --download figures=/outside/site/figures.zip --download research=/outside/site/research.zip

PRIVATE_DIR contains portal.html, portal.css, and portal.js. The existing password
is prompted without echo and authenticated against the current vault before any
write. Download arguments replace named resources; others are retained. All
inputs must live outside the public site. Only ciphertext is written to the site.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import gzip
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import secrets
import shutil
import tempfile

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

CHUNK_SIZE = 524_288


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('private', type=Path)
    parser.add_argument('site', type=Path)
    parser.add_argument('--download', action='append', default=[], metavar='ID=PATH')
    args = parser.parse_args()
    private, site = args.private.resolve(), args.site.resolve()
    if private.is_relative_to(site):
        parser.error('Private portal inputs must be outside the public site.')
    replacements = {}
    for spec in args.download:
        asset_id, sep, filename = spec.partition('=')
        if not sep or asset_id not in {'workbook', 'research', 'figures', 'figurebook'}:
            parser.error('Download must use workbook, research, figures, or figurebook as ID.')
        path = Path(filename).resolve()
        if path.is_relative_to(site) or not path.is_file():
            parser.error('Download input must be an existing file outside the public site.')
        replacements[asset_id] = path

    dest = site / 'assets/files/datasets/romania-protected'
    config = json.loads((dest / 'config.json').read_text())
    assert config['cipher'] == 'AES-GCM' and config['compression'] == 'gzip'
    assert config['kdf']['name'] == 'PBKDF2' and config['kdf']['hash'] == 'SHA-256'
    password = getpass.getpass('Existing dataset password: ')
    key = hashlib.pbkdf2_hmac('sha256', password.encode(),
                            base64.b64decode(config['kdf']['salt']),
                            config['kdf']['iterations'], dklen=32)
    del password
    cipher = AESGCM(key)
    del key

    def decrypt(name):
        raw = (dest / name).read_bytes()
        return cipher.decrypt(raw[:12], raw[12:], (config['aadPrefix'] + name).encode())

    # Authentication happens before staging or modifying anything.
    current = json.loads(gzip.decompress(decrypt(config['manifest'])))
    resources = current['downloads']
    with tempfile.TemporaryDirectory(prefix='romania-sealed-', dir=site.parent) as temp:
        stage = Path(temp)

        def seal(content, name=None):
            name = name or 'p_' + secrets.token_hex(12) + '.bin'
            nonce = os.urandom(12)
            aad = (config['aadPrefix'] + name).encode()
            raw = nonce + cipher.encrypt(nonce, content, aad)
            assert cipher.decrypt(raw[:12], raw[12:], aad) == content
            (stage / name).write_bytes(raw)
            return {'file': name, 'bytes': len(raw)}

        for asset_id, source in replacements.items():
            content_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            if resources.get(asset_id, {}).get('sha256') == content_hash:
                print('Retained unchanged download:', asset_id)
                continue
            parts = []
            with source.open('rb') as stream:
                while block := stream.read(CHUNK_SIZE):
                    parts.append(seal(block))
            resources[asset_id] = {
                'filename': source.name,
                'size': source.stat().st_size,
                'mime': mimetypes.guess_type(source.name)[0] or 'application/octet-stream',
                'sha256': content_hash,
                'parts': parts,
            }
            print('Sealed download:', asset_id, source.stat().st_size, 'bytes')

        referenced = {p['file'] for item in resources.values() for p in item['parts']}
        for name in referenced:
            if not (stage / name).exists():
                decrypt(name)  # Authenticate every retained chunk.
                shutil.copyfile(dest / name, stage / name)
        vault = {
            'version': 1,
            'html': (private / 'portal.html').read_text(),
            'css': (private / 'portal.css').read_text(),
            'script': (private / 'portal.js').read_text(),
            'downloads': resources,
        }
        packed = gzip.compress(json.dumps(vault, ensure_ascii=False,
                                         separators=(',', ':')).encode(), mtime=0)
        seal(packed, config['manifest'])
        checksums = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in sorted(stage.glob('*.bin'))}
        (stage / 'checksums.json').write_text(json.dumps(checksums, indent=2) + '\n')
        # Git publishes the complete commit atomically; retain the KDF config and
        # install all new ciphertext before removing obsolete encrypted chunks.
        for path in stage.iterdir():
            shutil.copyfile(path, dest / path.name)
        for obsolete in dest.glob('*.bin'):
            if obsolete.name not in checksums:
                obsolete.unlink()
        print(json.dumps({'encrypted_resources': len(checksums),
                          'vault_bytes': len(packed), 'downloads': len(resources)}))


if __name__ == '__main__':
    main()
