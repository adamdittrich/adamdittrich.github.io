#!/usr/bin/env python3
"""Validate the Quarto build, including dataset downloads, before publication."""
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
for checker in ('check_healthcare_figures.py', 'check_dataset_assets.py', 'check_site.py'):
    result = subprocess.run([sys.executable, str(root / 'scripts' / checker)], cwd=root)
    if result.returncode:
        raise SystemExit(result.returncode)
raise SystemExit(0)
