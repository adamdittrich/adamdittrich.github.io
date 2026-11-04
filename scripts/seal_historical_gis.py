#!/usr/bin/env python3
"""Prepare an encrypted GIS portal from an existing, validated website edition.

Run locally: python3 scripts/seal_historical_gis.py SOURCE_SITE OUTPUT_SITE
The password is read without echo; neither it nor the key is written to disk.
Only ciphertext and public cryptographic parameters belong in the website.
Requires the cryptography package. This is deliberately not a build hook.
"""
from pathlib import Path
import base64
import getpass
import gzip
import hashlib
import json
import mimetypes
import os
import re
import secrets
import sys
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

SOURCE = Path(sys.argv[1]).resolve()
OUTPUT = Path(sys.argv[2]).resolve()
SOURCE_ASSETS = SOURCE / 'assets/files/datasets/historical-gis'
DEST = OUTPUT / 'assets/files/datasets/historical-gis-protected'
PREFIX = 'assets/files/datasets/historical-gis/'
AAD_PREFIX = 'adamdittrich-gis-v1/'
CHUNK_SIZE = 8_000_000
ITERATIONS = 1_000_000


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    if (DEST / 'config.json').exists():
        raise SystemExit('Output already sealed; choose a fresh output directory.')
    password = getpass.getpass('Dataset password: ')
    if not password:
        raise SystemExit('A nonempty password is required.')
    salt = os.urandom(32)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                    iterations=ITERATIONS).derive(password.encode('utf-8'))
    del password
    cipher = AESGCM(key)

    def seal_piece(data, name=None):
        name = name or 'p_' + secrets.token_hex(12) + '.bin'
        nonce = os.urandom(12)
        encrypted = nonce + cipher.encrypt(nonce, data, (AAD_PREFIX + name).encode())
        path = DEST / name
        path.write_bytes(encrypted)
        return {'file': name, 'bytes': len(encrypted)}

    def seal_stream(stream, size):
        parts = []
        while True:
            block = stream.read(CHUNK_SIZE)
            if not block:
                break
            parts.append(seal_piece(block))
        return {'size': size, 'parts': parts}

    json_names = ['explorer.json', 'climate_explorer.json', 'dictionary.json',
                  'gallery.json', 'downloads.json', 'module_inventory.json', 'sources.json']
    ui_paths = [SOURCE_ASSETS / n for n in json_names]
    ui_paths.extend(sorted(p for p in (SOURCE_ASSETS / 'maps').iterdir()
                           if p.is_file() and p.suffix in {'.png', '.webp', '.svg'}))
    ui_entries = []
    for path in ui_paths:
        data = path.read_bytes()
        ui_entries.append({'path': PREFIX + path.relative_to(SOURCE_ASSETS).as_posix(),
                           'mime': mimetypes.guess_type(path.name)[0] or 'application/octet-stream',
                           'base64': base64.b64encode(data).decode('ascii')})
    packed = gzip.compress(json.dumps(ui_entries, separators=(',', ':')).encode(),
                           compresslevel=6, mtime=0)
    import io
    ui = seal_stream(io.BytesIO(packed), len(packed))
    ui['compression'] = 'gzip'
    del packed, ui_entries

    download_names = {d['url'] for d in json.loads((SOURCE_ASSETS / 'downloads.json').read_text())['items']}
    download_names.update({'data/gis_master_judicial_1930_public_v061.csv',
                           'data/climate_normals_judicial_1930.csv',
                           'CITATION.cff', 'citation.bib'})
    download_names.update('docs/' + p.name for p in (SOURCE_ASSETS / 'docs').iterdir() if p.is_file())
    downloads = {}
    for name in sorted(download_names):
        path = (SOURCE_ASSETS / name).resolve()
        if not path.is_relative_to(SOURCE_ASSETS) or not path.is_file():
            raise ValueError('Unknown download: ' + name)
        with path.open('rb') as stream:
            resource = seal_stream(stream, path.stat().st_size)
        resource.update({'filename': path.name,
                         'mime': mimetypes.guess_type(path.name)[0] or 'application/octet-stream'})
        downloads[PREFIX + name] = resource
        print('Sealed', name, path.stat().st_size, flush=True)

    source_qmd = (SOURCE / 'czech-lands-historical-gis.qmd').read_text()
    html = source_qmd.split('```{=html}', 1)[1].rsplit('```', 1)[0].strip()
    html = html.replace('Public edition 0.6.1', 'Edition 0.6.1 · Password access')
    # Prevent any plaintext request before the loader substitutes decrypted URLs.
    html = re.sub(r'(<img\b[^>]*?)\bsrc=', r'\1data-private-src=', html)
    script = (SOURCE / 'assets/js/historical-gis.js').read_text()
    start = script.index('  const assetURL = (path) => {')
    end = script.index('  const items = ', start)
    script = script[:start] + '  const assetURL = (path) => window.GISPrivate.assetURL(path);\n' + script[end:]
    vault = {'version': 1, 'html': html,
             'css': (SOURCE / 'assets/css/historical-gis.css').read_text(),
             'script': script, 'ui': ui, 'downloads': downloads}
    vault_bytes = json.dumps(vault, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    seal_piece(vault_bytes, 'vault.bin')
    config = {'version': 1, 'kdf': {'name': 'PBKDF2', 'hash': 'SHA-256',
              'iterations': ITERATIONS, 'salt': base64.b64encode(salt).decode('ascii')},
              'cipher': 'AES-GCM', 'manifest': 'vault.bin', 'aadPrefix': AAD_PREFIX}
    (DEST / 'config.json').write_text(json.dumps(config, indent=2) + '\n')

    # Verify the password envelope, wrong-key rejection, and transferred bytes.
    stored = (DEST / 'vault.bin').read_bytes()
    assert cipher.decrypt(stored[:12], stored[12:], (AAD_PREFIX + 'vault.bin').encode()) == vault_bytes
    try:
        AESGCM(os.urandom(32)).decrypt(stored[:12], stored[12:], (AAD_PREFIX + 'vault.bin').encode())
    except Exception:
        pass
    else:
        raise AssertionError('Wrong key unexpectedly succeeded')
    checks = []
    for path in sorted(DEST.glob('*.bin')):
        checks.append({'path': path.relative_to(OUTPUT).as_posix(), 'size': path.stat().st_size,
                       'sha': hashlib.sha1(('blob ' + str(path.stat().st_size) + '\0').encode() + path.read_bytes()).hexdigest()})
    (OUTPUT.parent / 'protection_binary_manifest.json').write_text(json.dumps(checks, indent=2))
    print(json.dumps({'encrypted_files': len(checks), 'encrypted_bytes': sum(x['size'] for x in checks),
                      'ui_bytes': ui['size'], 'downloads': len(downloads), 'envelope_verified': True}), flush=True)


if __name__ == '__main__':
    main()
