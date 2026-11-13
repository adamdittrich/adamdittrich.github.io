#!/usr/bin/env python3
"""Reconstruct released EER indices from the versioned bilateral inputs."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'assets/files/datasets'

if __name__ == '__main__':
    subprocess.run(
        [sys.executable,
         str(DATA / 'eer-documentation/reproduce_indices.py'),
         '--check-reader', str(DATA / 'eer-all-series.csv')],
        cwd=ROOT,
        check=True,
    )
