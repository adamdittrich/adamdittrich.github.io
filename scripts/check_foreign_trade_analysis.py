#!/usr/bin/env python3
"""Check monthly trade identities, filter alignment and packaged provenance.

Uses only Python's standard library so it can run in the website publishing
workflow without installing the numerical/plotting build dependencies.
"""
from __future__ import annotations

import csv
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "assets/files/datasets/foreign-trade-analysis"
SOURCE = BASE.parent / "foreign-trade-monthly.csv"
METHODS = ("raw", "trailing3", "trailing6", "trailing12", "centered12", "hp129600")
NUMBERS = ("exports_million_kc", "imports_million_kc", "trade_balance_million_kc",
           "total_trade_million_kc", "export_import_ratio_pct", "normalized_balance_pct")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def equal(actual, expected, label, tolerance=2e-8):
    if actual is None or expected is None:
        require(actual is expected, f"Missing-value mismatch: {label}: {actual} vs {expected}")
    else:
        require(math.isfinite(actual) and math.isclose(actual, expected, rel_tol=1e-11, abs_tol=tolerance),
                f"Value mismatch: {label}: {actual} vs {expected}")


def source_calendar():
    original = list(csv.DictReader(SOURCE.open(encoding="utf-8-sig")))
    observed, previous = {}, None
    for row in original:
        stamp = date.fromisoformat(row["date"])
        key = stamp.year * 12 + stamp.month - 1
        require(stamp.day == 1 and stamp.isoformat() == row["date"], "Invalid monthly source date")
        require(previous is None or key > previous, "Duplicate or unsorted source month")
        previous = key
        values = [float(row[field]) if row[field] else None for field in NUMBERS[:2]]
        require(all(value is None or math.isfinite(value) and value >= 0 for value in values), "Invalid source flow")
        observed[key] = values
    stamps, flows = [], []
    for key in range(min(observed), max(observed) + 1):
        year, month = divmod(key, 12)
        stamps.append(date(year, month + 1, 1).isoformat())
        flows.append(observed.get(key, [None, None]))
    return original, stamps, flows


def check():
    original, stamps, flows = source_calendar()
    n = len(stamps)
    source_sha = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    payload = json.loads((BASE / "monthly-analysis.json").read_text(encoding="utf-8"))
    meta = json.loads((BASE / "metadata.json").read_text(encoding="utf-8"))
    require(payload["schema_version"] == meta["schema_version"] == 1, "Unexpected schema version")
    require(payload["source"] == meta["source"], "JSON/metadata source descriptions differ")
    require(meta["source"]["sha256"] == source_sha, "Source checksum mismatch")
    require(meta["source"]["observations"] == len(original), "Source observation count mismatch")
    require(meta["source"]["calendar_months"] == n, "Source calendar count mismatch")
    require(meta["source"]["start"] == stamps[0] and meta["source"]["end"] == stamps[-1], "Source coverage mismatch")
    require(tuple(method["id"] for method in payload["methods"]) == METHODS, "Unexpected smoothing methods")
    require(payload["methods"] == meta["methods"], "Method metadata mismatch")
    require(payload["default_method"] == meta["default_method"] == "trailing12", "Unexpected default method")
    rows = payload["rows"]
    require(len(rows) == n * len(METHODS), "Unexpected derived observation count")
    grouped = {}
    for method in METHODS:
        grouped[method] = [row for row in rows if row["method"] == method]
        require([row["date"] for row in grouped[method]] == stamps, f"Bad date coverage for {method}")
    csv_rows = list(csv.DictReader((BASE / "monthly-analysis.csv").open(encoding="utf-8")))
    require(len(csv_rows) == len(rows), "CSV/JSON row count mismatch")
    for item, row in zip(csv_rows, rows):
        require(item["date"] == row["date"] and item["method"] == row["method"], "CSV/JSON row order mismatch")
        for field in NUMBERS:
            number = float(item[field]) if item[field] else None
            equal(number, row[field], f"CSV/JSON {row['date']} {row['method']} {field}", tolerance=1e-12)

    for row in rows:
        x, m = (row[field] for field in NUMBERS[:2])
        paired = x is not None and m is not None
        b, t = (x - m, x + m) if paired else (None, None)
        label = f"{row['date']} {row['method']}"
        equal(row["trade_balance_million_kc"], b, label + " balance")
        equal(row["total_trade_million_kc"], t, label + " turnover")
        equal(row["export_import_ratio_pct"], 100 * x / m if paired and m > 0 else None, label + " ratio")
        equal(row["normalized_balance_pct"], 100 * b / t if paired and t > 0 else None, label + " normalized balance")
    for i, pair in enumerate(flows):
        for j, field in enumerate(NUMBERS[:2]):
            equal(grouped["raw"][i][field], pair[j], f"Original flow {stamps[i]} {field}")

    # Independently calculate complete trailing windows with math.fsum.
    for window in (3, 6, 12):
        for i in range(n):
            part = flows[max(0, i - window + 1):i + 1]
            available = len(part) == window and all(all(v is not None for v in pair) for pair in part)
            for j, field in enumerate(NUMBERS[:2]):
                expected = math.fsum(pair[j] for pair in part) / window if available else None
                equal(grouped[f"trailing{window}"][i][field], expected, f"{window}-month mean {stamps[i]} {field}")
    # Center independently as the mean of two overlapping 12-month averages.
    for i in range(n):
        available = i >= 6 and i + 6 < n and all(all(v is not None for v in pair) for pair in flows[i - 6:i + 7])
        for j, field in enumerate(NUMBERS[:2]):
            expected = ((math.fsum(pair[j] for pair in flows[i - 6:i + 6]) / 12 +
                         math.fsum(pair[j] for pair in flows[i - 5:i + 7]) / 12) / 2) if available else None
            equal(grouped["centered12"][i][field], expected, f"Centered 2×12 {stamps[i]} {field}")

    # Verify HP first-order conditions, including the four boundary conditions,
    # directly by applying the second-difference penalty in scalar arithmetic.
    valid = [all(v is not None for v in pair) for pair in flows]
    runs, start = [], None
    for i, available in enumerate(valid + [False]):
        if available and start is None:
            start = i
        elif not available and start is not None:
            runs.append((start, i))
            start = None
    covered = set()
    hp_residual = 0.0
    for start, stop in runs:
        if stop - start < 24:
            continue
        covered.update(range(start, stop))
        for field, original_values in (
            ("exports_million_kc", [pair[0] for pair in flows[start:stop]]),
            ("imports_million_kc", [pair[1] for pair in flows[start:stop]]),
            ("trade_balance_million_kc", [pair[0] - pair[1] for pair in flows[start:stop]]),
        ):
            trend = [row[field] for row in grouped["hp129600"][start:stop]]
            require(all(v is not None for v in trend), f"Missing HP estimate inside a complete run: {field}")
            penalty = [0.0] * len(trend)
            for i in range(len(trend) - 2):
                curvature = trend[i] - 2 * trend[i + 1] + trend[i + 2]
                penalty[i] += curvature
                penalty[i + 1] -= 2 * curvature
                penalty[i + 2] += curvature
            residual = max(abs(t - y + 129600 * p) for t, y, p in zip(trend, original_values, penalty))
            hp_residual = max(hp_residual, residual)
            require(residual < 1e-5, f"HP optimality/linearity residual too large: {field} {residual}")
    for i in set(range(n)) - covered:
        require(all(grouped["hp129600"][i][field] is None for field in NUMBERS), f"HP bridged a missing or too-short segment: {stamps[i]}")

    svgs = sorted(BASE.glob("*.svg"))
    require(len(svgs) == 6, "Expected six research SVGs")
    for svg in svgs:
        require(ET.fromstring(svg.read_bytes()).tag.endswith("svg"), f"Invalid SVG {svg.name}")
    with zipfile.ZipFile(BASE / "monthly-analysis.zip") as archive:
        require(archive.testzip() is None, "Damaged analysis ZIP")
        require(archive.read("source-monthly.csv") == SOURCE.read_bytes(), "ZIP source does not match original CSV")
        for path in BASE.iterdir():
            if path.is_file() and path.suffix in {".py", ".txt", ".csv", ".json", ".svg"}:
                require(archive.read(path.name) == path.read_bytes(), f"Stale ZIP member: {path.name}")
    public = ROOT / "docs/assets/files/datasets/foreign-trade-analysis"
    if public.exists():
        for path in BASE.iterdir():
            if path.is_file():
                require((public / path.name).read_bytes() == path.read_bytes(), f"Source/rendered analysis mismatch: {path.name}")
    print(f"Validated {n} monthly observations × six methods ({len(rows)} rows), identities, complete windows, centered alignment, six SVGs and ZIP provenance.")
    print(f"Maximum HP optimality/linearity residual: {hp_residual:.3g}; source SHA-256: {source_sha}")


if __name__ == "__main__":
    try:
        check()
    except (ValueError, KeyError, OSError, zipfile.BadZipFile) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
