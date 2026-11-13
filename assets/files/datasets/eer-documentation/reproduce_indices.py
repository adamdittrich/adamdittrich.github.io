#!/usr/bin/env python3
"""Reproduce released EER indices from the published bilateral input panel.

Python 3.10+; standard library only. No source observations are changed.
Run beside bilateral-inputs.csv and currency-unit-rules.csv. With the full
website checkout, --check-reader verifies the published eer-all-series.csv.
Copyright (c) 2026 Adam Dittrich. MIT licence; see LICENSE.txt.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

BASIS = {"TWEER": ("total_trade_tis_kc", "w_T"),
         "XEER": ("export_csr_tis_kc", "w_X"),
         "MEER": ("import_csr_tis_kc", "w_M")}
CHAINS = ("paasche", "laspeyres", "tornqvist", "fixed1929")


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def load_panel(folder):
    rows = read_csv(folder / "bilateral-inputs.csv")
    rules = {r["partner"]: r for r in read_csv(folder / "currency-unit-rules.csv")}
    panel = {}
    checks = {"partner_year_rows": len(rows), "conversion_checks": 0,
              "weight_checks": 0, "log_level_checks": 0}
    for raw in rows:
        partner, year = raw["partner"], int(raw["year"])
        key = partner, year
        assert key not in panel, f"Duplicate partner-year: {key}"
        rule = rules.get(partner)
        factor = float(rule["factor"]) if rule and year <= int(rule["through_year"]) else 1.0
        assert factor == float(raw["currency_conversion_factor"]), key
        e = float(raw["exchange_rate_raw_kcs_per_reported_fx"]) * factor
        assert math.isclose(e, float(raw["exchange_rate_kcs_per_harmonised_fx"]), rel_tol=1e-13), key
        assert e > 0 and math.isfinite(e), key
        checks["conversion_checks"] += 1
        r = dict(raw)
        r["year"] = year
        r["e"] = e
        r["ln_e_rebuilt"] = math.log(e)
        r["ln_q_rebuilt"] = None
        if year >= 1923:
            pf, pc = float(raw["cpi_foreign_base1929"]), float(raw["cpi_czechoslovakia_base1929"])
            assert pf > 0 and pc > 0, key
            r["ln_q_rebuilt"] = math.log(e) + math.log(pf) - math.log(pc)
        for name, stored in (("ln_e_rebuilt", "ln_e"), ("ln_q_rebuilt", "ln_q")):
            if r[name] is not None:
                assert math.isclose(r[name], float(raw[stored]), rel_tol=1e-12, abs_tol=1e-12), (key, stored)
                checks["log_level_checks"] += 1
        panel[key] = r
    partners = sorted({p for p, _ in panel})
    assert len(partners) == 14
    assert set(panel) == {(p, y) for p in partners for y in range(1920, 1939)}
    for year in range(1920, 1939):
        for _, (trade, weight) in BASIS.items():
            total = math.fsum(float(panel[p, year][trade]) for p in partners)
            assert total > 0
            for p in partners:
                r = panel[p, year]
                rebuilt = float(r[trade]) / total
                assert math.isclose(rebuilt, float(r[weight]), rel_tol=1e-12, abs_tol=1e-14), (p, year, weight)
                r[weight + "_rebuilt"] = rebuilt
                checks["weight_checks"] += 1
    return panel, partners, checks


def index_levels(panel, partners, basis, method, metric):
    start = 1920 if metric == "NEER" else 1923
    field = "ln_e_rebuilt" if metric == "NEER" else "ln_q_rebuilt"
    weight = BASIS[basis][1] + "_rebuilt"
    if method == "direct_current":
        return {y: 100.0 * math.exp(math.fsum(
            panel[p, y][weight] * (panel[p, y][field] - panel[p, 1929][field])
            for p in partners)) for y in range(start, 1939)}
    log_levels = {start: 0.0}
    for year in range(start + 1, 1939):
        weights = []
        for p in partners:
            if method == "paasche":
                w = panel[p, year][weight]
            elif method == "laspeyres":
                w = panel[p, year - 1][weight]
            elif method == "tornqvist":
                w = 0.5 * (panel[p, year][weight] + panel[p, year - 1][weight])
            elif method == "fixed1929":
                w = panel[p, 1929][weight]
            else:
                raise ValueError(method)
            weights.append(w)
        normalizer = math.fsum(weights)
        link = math.fsum(w / normalizer * (panel[p, year][field] - panel[p, year - 1][field])
                         for p, w in zip(partners, weights))
        log_levels[year] = log_levels[year - 1] + link
    anchor = log_levels[1929]
    return {y: 100.0 * math.exp(v - anchor) for y, v in log_levels.items()}


def build_indices(panel, partners):
    result = []
    for basis in BASIS:
        for method in CHAINS + (("direct_current",) if basis == "TWEER" else ()):
            n = index_levels(panel, partners, basis, method, "NEER")
            r = index_levels(panel, partners, basis, method, "REER")
            for year in range(1920, 1939):
                result.append({"year": year, "trade_basis": basis, "method": method,
                               "NEER": n[year], "REER": r.get(year),
                               "sample": "analytical core" if year >= 1925 else "pre-stabilisation extension"})
    return result


def early_links(panel, partners):
    result = []
    for year in range(1921, 1926):
        for p in partners:
            r, previous = panel[p, year], panel[p, year - 1]
            w = r["w_T_rebuilt"]
            nominal = 100 * (r["ln_e_rebuilt"] - previous["ln_e_rebuilt"])
            real = None if year < 1924 else 100 * (r["ln_q_rebuilt"] - previous["ln_q_rebuilt"])
            result.append({
                "year": year, "previous_year": year - 1, "partner": p,
                "total_trade_weight": w,
                "previous_raw_exchange_rate": float(previous["exchange_rate_raw_kcs_per_reported_fx"]),
                "raw_exchange_rate": float(r["exchange_rate_raw_kcs_per_reported_fx"]),
                "previous_conversion_factor": float(previous["currency_conversion_factor"]),
                "conversion_factor": float(r["currency_conversion_factor"]),
                "previous_harmonised_exchange_rate": previous["e"],
                "harmonised_exchange_rate": r["e"],
                "previous_foreign_cpi": previous["cpi_foreign_base1929"] or None,
                "foreign_cpi": r["cpi_foreign_base1929"] or None,
                "previous_czechoslovak_cpi": previous["cpi_czechoslovakia_base1929"] or None,
                "czechoslovak_cpi": r["cpi_czechoslovakia_base1929"] or None,
                "bilateral_nominal_change_log_points": nominal,
                "bilateral_real_change_log_points": real,
                "nominal_contribution_log_points": w * nominal,
                "relative_price_contribution_log_points": None if real is None else w * (real - nominal),
                "real_contribution_log_points": None if real is None else w * real,
                "sample": r["sample_status"],
            })
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--check-reader", type=Path, metavar="CSV", help="Compare with eer-all-series.csv")
    parser.add_argument("--output-dir", type=Path, help="Write early links and verification report here")
    parser.add_argument("--export-indices", action="store_true", help="Also write reproduced-indices.csv to --output-dir")
    args = parser.parse_args()
    panel, partners, report = load_panel(args.input_dir)
    indices = build_indices(panel, partners)
    report.update({"specification_pairs": 13, "index_rows": len(indices),
                   "available_index_observations": sum(x[k] is not None for x in indices for k in ["NEER", "REER"]),
                   "base_year": 1929, "base_value": 100,
                   "input_sha256": hashlib.sha256((args.input_dir / "bilateral-inputs.csv").read_bytes()).hexdigest(),
                   "verification_scope": "Numerical reconstruction from released bilateral inputs; no claim of independent historical transcription verification."})
    assert report["available_index_observations"] == 455
    assert all(x[k] == 100 for x in indices if x["year"] == 1929 for k in ["NEER", "REER"])
    if args.check_reader:
        reader = read_csv(args.check_reader)
        assert len(reader) == 247
        keyed = {(int(x["year"]), x["trade_basis"], x["method"]): x for x in reader}
        assert len(keyed) == len(reader)
        errors = []
        for x in indices:
            original = keyed[x["year"], x["trade_basis"], x["method"]]
            assert original["sample"] == x["sample"]
            for metric in ["NEER", "REER"]:
                actual, expected = x[metric], original[metric]
                assert (actual is None) == (expected == "")
                if actual is not None:
                    expected = float(expected)
                    error = abs(actual - expected) / expected
                    errors.append(error)
                    assert math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-10), (x, metric, expected)
        report.update({"reader_observations_checked": len(errors), "maximum_relative_error": max(errors),
                       "reader_sha256": hashlib.sha256(args.check_reader.read_bytes()).hexdigest()})
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        if args.export_indices:
            write_csv(args.output_dir / "reproduced-indices.csv", indices, list(indices[0]))
        links = early_links(panel, partners)
        write_csv(args.output_dir / "early-year-links.csv", links, list(links[0]))
        (args.output_dir / "validation-report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
