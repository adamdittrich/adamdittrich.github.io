#!/usr/bin/env python3
"""Check the six verified healthcare figures before publishing.

Expected Git blob hashes describe visually checked, decodable assets.
Refresh the relevant hash when deliberately replacing a figure.
"""
from pathlib import Path
import hashlib
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
FIGURES = {
    'physician-density.webp': '18775c3f912c0a07e6ea3e9eba6056a022a0ba51',
    'hospital-beds.webp': 'c3b00ccafebd2f06cc355a542d0af17b522c893c',
    'provision-infant-gap.webp': '38aae819729ef851a56879af4346fd9ae7022d3a',
    'infant-gap-composition-v2.svg': '8cfacc826fba4082380c00057ae308fd678f10f1',
    'male-mortality-v2.svg': '699e23334ab7d94db91f32b1c925922bf7c08435',
    'ardl-capacity-mortality.webp': '4ff8fec1ef848752b07a631254e3cc5222dd5ec9',
}


def check():
    page = (ROOT / 'docs/healthcare-capacity.html').read_text(encoding='utf-8')
    for name, expected in FIGURES.items():
        relative = 'assets/img/healthcare/' + name
        if relative not in page:
            raise ValueError('Healthcare page is missing figure: ' + name)
        for base in (ROOT, ROOT / 'docs'):
            data = (base / relative).read_bytes()
            actual = hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()
            if actual != expected:
                raise ValueError('Figure integrity mismatch: ' + str(base / relative))
            if name.endswith('.svg'):
                element = ET.fromstring(data)
                if element.tag != '{http://www.w3.org/2000/svg}svg':
                    raise ValueError('Not an SVG figure: ' + name)
    for old in ('infant-gap-composition.webp', 'male-mortality.webp'):
        if 'assets/img/healthcare/' + old in page:
            raise ValueError('Page still references corrupted legacy figure: ' + old)
    print('All 6 healthcare figures passed source and deployment integrity checks.')


if __name__ == '__main__':
    check()
