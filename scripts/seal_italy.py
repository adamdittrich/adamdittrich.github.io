#!/usr/bin/env python3
"""Seal the Italy portal and its research downloads for a static website.

Run locally: python3 scripts/seal_italy.py PRIVATE_DIR DOWNLOAD_DIR SITE_DIR
The password is prompted without echo. Use --password-stdin only with a private
stdin pipe. No password or plaintext dataset is written inside SITE_DIR.
Requires cryptography; this is deliberately not a render hook.
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
import re
import secrets
import shutil
import sys
import tempfile

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


AAD_PREFIX = 'adamdittrich-italy-v1/'
ITERATIONS = 1_000_000
CHUNK_SIZE = 524_288
DOWNLOADS = {
    'workbook': 'Italy_Interwar_1919_1939.xlsx',
    'research': 'Italy_Interwar_Data_v1.zip',
    'guide': 'Italy_Interwar_User_Guide.pdf',
    'figures': 'Italy_Interwar_Figures_v1.zip',
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('private', type=Path)
    parser.add_argument('downloads', type=Path)
    parser.add_argument('site', type=Path)
    parser.add_argument('--password-stdin', action='store_true',
                        help='Read one password line from private standard input.')
    args = parser.parse_args()
    private, downloads, site = (p.resolve() for p in (args.private, args.downloads, args.site))
    if not site.is_dir():
        parser.error('SITE_DIR must be an existing website checkout.')
    if private.is_relative_to(site) or downloads.is_relative_to(site):
        parser.error('Private portal and download inputs must stay outside the website.')
    dest = site / 'assets/files/datasets/italy-protected'
    if dest.exists():
        parser.error('The encrypted output already exists; preserve the existing release.')
    portal = {}
    for key, filename in (('html', 'portal.html'), ('css', 'portal.css'), ('script', 'portal.js')):
        path = private / filename
        if not path.is_file():
            parser.error(f'Missing private portal input: {filename}')
        portal[key] = path.read_text(encoding='utf-8')
        if not portal[key].strip():
            parser.error(f'Empty private portal input: {filename}')
    if not re.search(r'\bid=[\"\']italy-portal[\"\']', portal['html']):
        parser.error('The private portal needs an element with id="italy-portal".')
    for filename in DOWNLOADS.values():
        path = downloads / filename
        if not path.is_file() or not path.stat().st_size:
            parser.error(f'Missing or empty download input: {filename}')

    password = sys.stdin.readline().rstrip('\r\n') if args.password_stdin else getpass.getpass('Dataset password: ')
    if not password:
        parser.error('A nonempty password is required.')
    salt = os.urandom(32)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, ITERATIONS, dklen=32)
    del password
    cipher = AESGCM(key)
    del key

    # Stage outside the public checkout and install only a fully verified release.
    with tempfile.TemporaryDirectory(prefix='italy-sealed-', dir=site.parent) as directory:
        stage = Path(directory)

        def seal(data: bytes, name: str | None = None) -> dict[str, object]:
            name = name or 'p_' + secrets.token_hex(12) + '.bin'
            if (stage / name).exists():
                raise RuntimeError('Unexpected encrypted-resource filename collision.')
            nonce = os.urandom(12)
            aad = (AAD_PREFIX + name).encode('utf-8')
            raw = nonce + cipher.encrypt(nonce, data, aad)
            (stage / name).write_bytes(raw)
            if cipher.decrypt(raw[:12], raw[12:], aad) != data:
                raise RuntimeError('Encrypted resource verification failed.')
            return {'file': name, 'bytes': len(raw)}

        resources = {}
        for asset_id, filename in DOWNLOADS.items():
            source = downloads / filename
            digest = hashlib.sha256()
            parts = []
            size = 0
            with source.open('rb') as stream:
                while block := stream.read(CHUNK_SIZE):
                    digest.update(block)
                    size += len(block)
                    parts.append(seal(block))
            if size != source.stat().st_size:
                raise RuntimeError('A source download changed while being sealed.')
            resources[asset_id] = {
                'filename': filename,
                'size': size,
                'mime': mimetypes.guess_type(filename)[0] or 'application/octet-stream',
                'sha256': digest.hexdigest(),
                'parts': parts,
            }
            print('Sealed', filename, size, 'bytes', flush=True)

        vault = {'version': 1, **portal, 'downloads': resources}
        packed = gzip.compress(json.dumps(vault, ensure_ascii=False, separators=(',', ':')).encode('utf-8'),
                               compresslevel=9, mtime=0)
        seal(packed, 'vault.bin')
        raw = (stage / 'vault.bin').read_bytes()
        try:
            AESGCM(os.urandom(32)).decrypt(raw[:12], raw[12:], (AAD_PREFIX + 'vault.bin').encode())
        except InvalidTag:
            pass
        else:
            raise RuntimeError('Wrong encryption key was accepted.')
        config = {
            'version': 1,
            'kdf': {'name': 'PBKDF2', 'hash': 'SHA-256', 'iterations': ITERATIONS,
                    'salt': base64.b64encode(salt).decode('ascii')},
            'cipher': 'AES-GCM', 'manifest': 'vault.bin', 'compression': 'gzip',
            'aadPrefix': AAD_PREFIX,
        }
        (stage / 'config.json').write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
        checksums = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(stage.glob('*.bin'))}
        (stage / 'checksums.json').write_text(json.dumps(checksums, indent=2) + '\n', encoding='utf-8')
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Do not overwrite any release created concurrently.
        if dest.exists():
            raise RuntimeError('The destination was created during sealing; existing release preserved.')
        shutil.copytree(stage, dest)

    manifest = []
    for path in sorted(dest.iterdir()):
        content = path.read_bytes()
        header = ('blob ' + str(len(content)) + '\0').encode('ascii')
        manifest.append({'path': path.relative_to(site).as_posix(), 'size': len(content),
                         'sha': hashlib.sha1(header + content).hexdigest()})
    (site.parent / 'italy_binary_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'sealed_files': len(manifest), 'bytes': sum(p['size'] for p in manifest),
                      'vault_bytes': len(packed), 'downloads': len(resources),
                      'all_chunks_verified': True}), flush=True)


if __name__ == '__main__':
    main()
