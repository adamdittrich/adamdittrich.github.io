#!/usr/bin/env python3
"""Remove the optional degree suffix from the legacy CV's display heading.

Applies only to the exact October 2026 source PDF. Uses an incremental PDF
update, preserving all pages, fonts, links and education records. A later
replacement CV is left untouched. Only the rendered download is edited.
"""
from pathlib import Path
import hashlib
import re
import zlib

SOURCE_SHA256 = 'e425e6302d818a442b4296c6a909788d916cb140828bbe1a5997bd8dd79ad0a1'


def prepare(path: Path) -> None:
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        print('CV: retaining the supplied PDF (legacy title migration not needed).')
        return
    obj = re.search(rb'(?m)^2 0 obj\s*<<(.*?)>>\s*stream\r?\n', data, re.S)
    if not obj:
        raise RuntimeError('Legacy CV content stream was not found.')
    end = data.index(b'\nendstream', obj.end())
    stream = zlib.decompress(data[obj.end():end])
    old = b'-9<0C>-9<05>-8<0D>-10<0B>-7<06>]TJ'
    if stream.count(old) != 1:
        raise RuntimeError('Legacy CV title did not match the expected glyph sequence.')
    revised = zlib.compress(stream.replace(old, b']TJ', 1), 9)
    previous_xref = int(re.findall(rb'startxref\s+(\d+)', data)[-1])
    object_offset = len(data) + 1
    update = b'\n2 0 obj\n<< /Filter /FlateDecode /Length ' + str(len(revised)).encode() + b' >>\nstream\n' + revised + b'\nendstream\nendobj\n'
    xref_offset = len(data) + len(update)
    update += (f'xref\n2 1\n{object_offset:010d} 00000 n \n'
               f'trailer\n<< /Size 147 /Root 145 0 R /Info 146 0 R /Prev {previous_xref} >>\n'
               f'startxref\n{xref_offset}\n%%EOF\n').encode()
    path.write_bytes(data + update)
    print('CV: display heading updated to Adam Dittrich; academic record preserved.')


if __name__ == '__main__':
    prepare(Path(__file__).resolve().parents[1] / 'docs/assets/files/Adam-Dittrich-CV.pdf')
