#!/usr/bin/env python3
"""Seal the Romania portal and its downloads for a static website.

Run locally: python3 scripts/seal_romania.py PRIVATE_DIR DOWNLOAD_DIR SITE_DIR
The password is prompted without echo. Only ciphertext belongs in the website.
Requires cryptography; not a render hook. Private source stays outside SITE_DIR.
"""
from pathlib import Path
import base64
import getpass
import gzip
import hashlib
import json
import mimetypes
import os
import secrets
import sys
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

AAD_PREFIX = 'adamdittrich-romania-v1/'
ITERATIONS = 1_000_000
CHUNK_SIZE = 524_288
DOWNLOADS = {
    'workbook': 'Romania_Interwar_Database_v0_1_0.xlsx',
    'research': 'Romania_Interwar_Research_Package_v0_1_0.zip',
    'figures': 'Romania_Interwar_Figures_v0_1_0.zip',
    'figurebook': 'Romania_Interwar_Figure_Book.pdf',
}


def main():
    private, downloads, site = [Path(p).resolve() for p in sys.argv[1:4]]
    if private.is_relative_to(site) or downloads.is_relative_to(site):
        raise SystemExit('Private inputs must remain outside the published site.')
    dest = site / 'assets/files/datasets/romania-protected'
    if dest.exists():
        raise SystemExit('Choose a fresh output directory; preserve the existing release.')
    password = getpass.getpass('Dataset password: ')
    if not password:
        raise SystemExit('A nonempty password is required.')
    salt = os.urandom(32)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                    iterations=ITERATIONS).derive(password.encode('utf-8'))
    del password
    cipher = AESGCM(key)
    dest.mkdir(parents=True)

    def seal(data, name=None):
        name = name or 'p_' + secrets.token_hex(12) + '.bin'
        nonce = os.urandom(12)
        aad = (AAD_PREFIX + name).encode()
        blob = nonce + cipher.encrypt(nonce, data, aad)
        (dest / name).write_bytes(blob)
        assert cipher.decrypt(blob[:12], blob[12:], aad) == data
        return {'file': name, 'bytes': len(blob)}

    resources = {}
    for asset_id, filename in DOWNLOADS.items():
        source = downloads / filename
        digest = hashlib.sha256()
        parts = []
        with source.open('rb') as stream:
            while block := stream.read(CHUNK_SIZE):
                digest.update(block)
                parts.append(seal(block))
        resources[asset_id] = {'filename': filename, 'size': source.stat().st_size,
                              'mime': mimetypes.guess_type(filename)[0] or 'application/octet-stream',
                              'sha256': digest.hexdigest(), 'parts': parts}
        print('Sealed', filename, source.stat().st_size, flush=True)

    vault = {'version': 1, 'html': (private / 'portal.html').read_text(),
             'css': (private / 'portal.css').read_text(),
             'script': (private / 'portal.js').read_text(), 'downloads': resources}
    payload = gzip.compress(json.dumps(vault, ensure_ascii=False, separators=(',', ':')).encode(),
                            compresslevel=9, mtime=0)
    seal(payload, 'vault.bin')
    stored = (dest / 'vault.bin').read_bytes()
    try:
        AESGCM(os.urandom(32)).decrypt(stored[:12], stored[12:], (AAD_PREFIX + 'vault.bin').encode())
    except Exception:
        pass
    else:
        raise AssertionError('Wrong key was accepted')
    config = {'version': 1, 'kdf': {'name': 'PBKDF2', 'hash': 'SHA-256',
              'iterations': ITERATIONS, 'salt': base64.b64encode(salt).decode()},
              'cipher': 'AES-GCM', 'manifest': 'vault.bin', 'compression': 'gzip', 'aadPrefix': AAD_PREFIX}
    (dest / 'config.json').write_text(json.dumps(config, indent=2) + '\n')
    checksums = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in sorted(dest.glob('*.bin'))}
    (dest / 'checksums.json').write_text(json.dumps(checksums, indent=2) + '\n')
    manifest = []
    for path in sorted(dest.iterdir()):
        content = path.read_bytes()
        manifest.append({'path': path.relative_to(site).as_posix(), 'size': len(content),
                         'sha': hashlib.sha1(('blob ' + str(len(content)) + '\0').encode() + content).hexdigest()})
    (site.parent / 'romania_binary_manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps({'sealed_files': len(manifest), 'bytes': sum(x['size'] for x in manifest),
                      'vault_bytes': len(payload), 'downloads': len(resources), 'all_chunks_verified': True}), flush=True)


if __name__ == '__main__':
    main()
