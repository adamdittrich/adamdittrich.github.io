#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check the annual EER supplement against the released EER reader source files.

Uses only the Python standard library. Also runs from an extracted analysis ZIP.
"""
from __future__ import annotations
import argparse
import csv
from decimal import Decimal, localcontext
import hashlib
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import zipfile

SOURCE_HASHES = {
    "eer-all-series.csv": "31eaa9335710d5e2b0da01fb6cc4fb6849f0adb525caebf14a42d7e949536c54",
    "eer-annual.csv": "3bc81a18d34894f63c0ec03b938e5ed99bd1aecc0963fa76a0ec5002669a1e8c",
    "eer-partner-weights.csv": "36a7e36ca822dfd964403ec309662ce12a349b52bd54d437843fbd82063b36f1",
    "eer-basket-coverage.csv": "270b9be7bd6ea0a4d1dedebea7920ca2a0d0e68f891d4bf350618ff51df84c66",
}


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def near(actual, expected, message, rel=2e-12, abs_tol=1e-10):
    check(actual is not None and math.isfinite(float(actual)), message + ": unavailable/nonfinite")
    check(math.isclose(float(actual), float(expected), rel_tol=rel, abs_tol=abs_tol),
          f"{message}: {actual!r} != {expected!r}")


def validate(analysis_dir: Path, data_dir: Path):
    for name, expected in SOURCE_HASHES.items():
        found = hashlib.sha256((data_dir / name).read_bytes()).hexdigest()
        check(found == expected, f"Released EER source changed: {name}")
    payload = json.loads((analysis_dir / "annual-analysis.json").read_text(),
                         parse_constant=lambda s: (_ for _ in ()).throw(ValueError(f"Invalid JSON constant {s}")))
    metadata = json.loads((analysis_dir / "metadata.json").read_text())
    rows = payload["series"]
    check(len(rows) == 247, "Expected 247 annual specification rows")
    keys = [(r["year"], r["basis"], r["method"]) for r in rows]
    check(len(set(keys)) == len(keys), "Duplicate analytical keys")
    by_key = dict(zip(keys, rows))
    source_rows = read_csv(data_dir / "eer-all-series.csv")
    source = {(int(r["year"]), r["trade_basis"], r["method"]): r for r in source_rows}
    check(set(source) == set(by_key), "Source/analysis key mismatch")
    check(sum(r[x] is not None for r in rows for x in ["neer", "reer"]) == 455,
          "Expected 455 observed nominal and real values")
    check(payload["years"] == list(range(1920, 1939)), "Calendar range changed")
    check(metadata["available_index_observations"] == 455, "Metadata observation count")
    check(metadata["row_count"] == 247 and metadata["index_series_count"] == 26, "Metadata row/series count")
    for file in payload["source"]["files"]:
        check(file["sha256"] == SOURCE_HASHES[file["name"]], "Payload source-hash mismatch")
    for key, raw in source.items():
        r = by_key[key]
        check(r["sample"] == raw["sample"], f"Source sample changed: {key}")
        if r["method"] == "direct_current":
            check(r["basis"] == "TWEER", "Direct-current method has unsupported trade basis")
        for metric in ["neer", "reer"]:
            value = raw[metric.upper()]
            if value == "":
                check(r[metric] is None, f"Missing source value filled: {key}/{metric}")
            else:
                check(r[metric] == float(value), f"Original stored value changed: {key}/{metric}")
                check(r[metric] > 0, f"Nonpositive index: {key}/{metric}")
            if key[0] == 1929:
                check(r[metric] == 100, f"Base year not 100: {key}/{metric}")
            if metric == "reer":
                check((r[metric] is None) == (key[0] <= 1922), f"REER missingness changed: {key}")
            previous = source.get((key[0] - 1, key[1], key[2]), {}).get(metric.upper(), "")
            if value == "" or previous == "":
                check(r[metric+"_yoy_pct"] is None and r[metric+"_log_change"] is None,
                      f"Change crossed an unavailable observation: {key}/{metric}")
            else:
                with localcontext() as ctx:
                    ctx.prec = 55
                    ratio = Decimal(value) / Decimal(previous)
                    percent = (ratio - 1) * 100
                    log = ratio.ln() * 100
                near(r[metric+"_yoy_pct"], percent, f"Annual percentage change: {key}/{metric}")
                near(r[metric+"_log_change"], log, f"Annual log change: {key}/{metric}")
            window = [source.get((key[0]+delta, key[1], key[2])) for delta in [-1, 0, 1]]
            complete = all(v is not None and v["sample"] == raw["sample"] and v[metric.upper()] != "" for v in window)
            if complete:
                exact_average = sum(Decimal(v[metric.upper()]) for v in window) / 3
                near(r[metric+"_ma3"], exact_average, f"Centered average: {key}/{metric}")
            else:
                check(r[metric+"_ma3"] is None, f"Smoother crossed sample/calendar boundary: {key}/{metric}")
        if r["reer"] is None:
            check(r["relative_price_index"] is None and r["relative_price_log_change"] is None,
                  f"Relative-price data filled without REER: {key}")
        else:
            with localcontext() as ctx:
                ctx.prec = 55
                ratio = Decimal(raw["REER"]) / Decimal(raw["NEER"]) * 100
            near(r["relative_price_index"], ratio, f"Relative-price index: {key}")
            if r["reer_log_change"] is not None:
                near(r["relative_price_log_change"], r["reer_log_change"]-r["neer_log_change"],
                     f"Exact log decomposition: {key}", abs_tol=2e-10)
            else:
                check(r["relative_price_log_change"] is None, f"Relative-price change without previous REER: {key}")
    # Independently published paired series supply a second source for preferred levels.
    annual = read_csv(data_dir / "eer-annual.csv")
    for r in annual:
        for basis, suffix in [("TWEER", "total"), ("XEER", "exports"), ("MEER", "imports")]:
            got = by_key[(int(r["year"]), basis, "paasche")]
            for metric in ["neer", "reer"]:
                value = r[metric.upper()+"_"+suffix]
                check(got[metric] == (float(value) if value else None), "Preferred annual source mismatch")
    # The Törnqvist levels are a geometric mean of the adjacent-weight chains.
    for y in range(1920, 1939):
        for basis in ["TWEER", "XEER", "MEER"]:
            for metric in ["neer", "reer"]:
                p = by_key[(y, basis, "paasche")][metric]
                l = by_key[(y, basis, "laspeyres")][metric]
                t = by_key[(y, basis, "tornqvist")][metric]
                if p is not None:
                    near(t, math.sqrt(p*l), "Törnqvist geometric relationship")
    # Reference values and sample endpoints catch accidental interpretation changes.
    r35 = by_key[(1935, "TWEER", "paasche")]
    near(r35["relative_price_index"], 87.09938190486375, "1935 relative-price reference")
    near(r35["neer_log_change"], 1.3827342844793349, "1935 nominal log change")
    near(r35["relative_price_log_change"], -4.015572862925151, "1935 price log change")
    for year in [1920, 1924, 1925, 1938]:
        check(all(r["neer_ma3"] is None for r in rows if r["year"] == year), "Sample endpoint smoother is populated")
    check(sum(r["neer_ma3"] is not None for r in rows) == 195, "Unexpected NEER smoothing windows")
    check(sum(r["reer_ma3"] is not None for r in rows) == 156, "Unexpected REER smoothing windows")
    # Machine formats must carry identical numeric values and missingness.
    exported = read_csv(analysis_dir / "annual-analysis.csv")
    check(len(exported) == len(rows), "CSV/JSON row count")
    for csv_row, json_row in zip(exported, rows):
        check(set(csv_row) == set(json_row), "CSV/JSON field mismatch")
        for k, value in json_row.items():
            if value is None:
                check(csv_row[k] == "", "CSV missing value not blank")
            elif isinstance(value, (int, float)):
                check(float(csv_row[k]) == value, f"CSV/JSON numeric mismatch: {k}")
            else:
                check(csv_row[k] == value, f"CSV/JSON text mismatch: {k}")
    # Weight/coverage exports preserve their own sources exactly.
    for table, name in [("weights", "eer-partner-weights.csv"), ("coverage", "eer-basket-coverage.csv")]:
        originals = read_csv(data_dir / name)
        check(len(originals) == len(payload[table]), f"{table} row count")
        for original, copied in zip(originals, payload[table]):
            for k, v in original.items():
                check(copied[k] == (v if k == "partner" else float(v)), f"{table} source field changed: {k}")
    for y in range(1920, 1939):
        year_weights = [r for r in payload["weights"] if r["year"] == y]
        check(len(year_weights) == 14, "Expected fourteen partner weights")
        for field in ["export_weight", "import_weight", "total_trade_weight"]:
            near(math.fsum(r[field] for r in year_weights), 1, "Partner weights sum")
    for row in payload["coverage"]:
        for k, value in row.items():
            if k != "year":
                check(0 <= value <= 1, "Coverage outside fraction range")
    for name in metadata["figures"]:
        path = analysis_dir / name
        tree = ET.fromstring(path.read_text())
        check(tree.tag.endswith("svg"), f"Invalid SVG: {name}")
        text = " ".join(tree.itertext())
        check("Source:" in text and "192" in text, f"Missing figure source/year label: {name}")
    archive = analysis_dir / "annual-analysis.zip"
    if archive.exists():
        with zipfile.ZipFile(archive) as z:
            check(z.testzip() is None, "Corrupt ZIP")
            for name, expected in SOURCE_HASHES.items():
                check(hashlib.sha256(z.read("source/"+name)).hexdigest() == expected, "ZIP source changed")
            check(z.read("annual-analysis.json") == (analysis_dir / "annual-analysis.json").read_bytes(), "ZIP JSON mismatch")
            check("check_eer_analysis.py" in z.namelist(), "ZIP lacks independent checker")
    print("Validated EER supplement: 247 rows, 26 index series, 455 observed values; "
          "source preservation, annual changes, log decomposition, smoothing boundaries, "
          "preferred-series agreement, weights, CSV/JSON and ZIP checks passed.")


def main():
    here = Path(__file__).resolve().parent
    packaged = (here / "annual-analysis.json").is_file()
    default_analysis = here if packaged else here.parent / "assets/files/datasets/eer-analysis"
    default_data = here / "source" if packaged else here.parent / "assets/files/datasets"
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--analysis-dir", type=Path, default=default_analysis)
    p.add_argument("--data-dir", type=Path, default=default_data)
    args = p.parse_args()
    validate(args.analysis_dir, args.data_dir)


if __name__ == "__main__":
    main()
