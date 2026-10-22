#!/usr/bin/env python3
"""Validate the real Quarto build before GitHub Pages uploads it."""
from pathlib import Path
from prepare_cv import prepare
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
output = root / 'docs'
if (output / 'search.json').is_file():
    (output / 'search-index.json').unlink(missing_ok=True)
(output / 'assets/img/hero-archive.svg').unlink(missing_ok=True)
prepare(output / 'assets/files/Adam-Dittrich-CV.pdf')
result = subprocess.run([sys.executable, str(root / 'scripts/check_site.py')], cwd=root)
raise SystemExit(result.returncode)
