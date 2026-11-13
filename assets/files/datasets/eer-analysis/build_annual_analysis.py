#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Reproduce the annual EER analysis extension from the released reader CSVs.

Python 3.10+; the numerical exports use the standard library. Figures additionally
require matplotlib. Run with --skip-figures for numerical exports only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import zipfile

VERSION = "1.0.0"
RELEASE_DATE = "2026-11-13"
PAGE = "https://adamdittrich.github.io/czechoslovakia-eer.html"
DATA_URL = "https://adamdittrich.github.io/assets/files/datasets/"
SOURCE_NAMES = (
    "eer-all-series.csv", "eer-annual.csv", "eer-partner-weights.csv",
    "eer-basket-coverage.csv",
)
BASIS = [
    {"id": "TWEER", "label": "Total trade"},
    {"id": "XEER", "label": "Exports"},
    {"id": "MEER", "label": "Imports"},
]
METHODS = [
    {"id": "paasche", "label": "Current-year chain (preferred)", "kind": "chain",
     "weights": "Current year", "definition": "Geometric chain using current-year partner weights.",
     "relative_price_interpretation": "Chained relative-price component"},
    {"id": "laspeyres", "label": "Lagged-year chain", "kind": "chain",
     "weights": "Previous year", "definition": "Geometric chain using lagged-year partner weights.",
     "relative_price_interpretation": "Chained relative-price component"},
    {"id": "tornqvist", "label": "Törnqvist chain", "kind": "chain",
     "weights": "Mean of current and previous years", "definition": "Geometric chain using the mean of adjacent annual partner weights.",
     "relative_price_interpretation": "Chained relative-price component"},
    {"id": "fixed1929", "label": "Fixed-1929-weight chain", "kind": "chain",
     "weights": "1929", "definition": "Geometric chain using the 1929 partner weights throughout.",
     "relative_price_interpretation": "Chained relative-price component"},
    {"id": "direct_current", "label": "Direct current-weighted index", "kind": "direct",
     "weights": "Current year", "definition": "100 × exp(sum_i w(i,t) × [ln z(i,t) − ln z(i,1929)]), where z=e for NEER and z=q for REER. Direct aggregation of bilateral relatives to 1929; supplied for total trade only.",
     "relative_price_interpretation": "Real/nominal ratio; annual residual may include reweighting"},
]
FIELDS = [
    "year", "basis", "method", "neer", "reer", "neer_yoy_pct", "reer_yoy_pct",
    "neer_log_change", "reer_log_change", "relative_price_index",
    "relative_price_log_change", "neer_ma3", "reer_ma3", "sample",
]
FIGURES = [
    "eer-levels.svg", "eer-annual-changes.svg", "eer-relative-prices.svg",
    "eer-decomposition.svg", "eer-method-sensitivity.svg", "eer-partner-weights.svg",
    "eer-coverage.svg", "eer-trade-bases.svg",
]
LICENSE = """Czechoslovakia EER: Annual Analysis Extension — licences and source rights
Copyright (c) 2026 Adam Dittrich

NEW ANALYTICAL TABLES, FIGURES AND DOCUMENTATION
The new derived tables, SVG figures, dictionaries and explanatory documentation
in this analysis extension are licensed under Creative Commons Attribution
4.0 International (CC BY 4.0):
https://creativecommons.org/licenses/by/4.0/
https://creativecommons.org/licenses/by/4.0/legalcode
Attribute Adam Dittrich and identify the extension version and release date.
Indicate any changes. This licence applies to the new material, not to any
underlying third-party content or rights outside the author's authority.

SOURCE READER FILES
The original reader CSVs copied into source/ in the ZIP, the original Excel
workbook and historical inputs retain their existing rights and terms. The
reader source files do not state a separate data reuse licence. No new licence
for those original source files is asserted by this extension.

SOFTWARE: MIT LICENCE
This licence applies to build_annual_analysis.py, check_eer_analysis.py and the
new EER explorer JavaScript and CSS supplied with the website update.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def number(value: str) -> float | None:
    if value == "":
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"Nonfinite source number: {value}")
    return result


def growth(current: float | None, previous: float | None, log: bool = False) -> float | None:
    if current is None or previous is None or current <= 0 or previous <= 0:
        return None
    return 100 * (math.log(current / previous) if log else current / previous - 1)


def build_series(data_dir: Path) -> list[dict]:
    rows = []
    keys = set()
    for raw in read_csv(data_dir / "eer-all-series.csv"):
        row = {"year": int(raw["year"]), "basis": raw["trade_basis"], "method": raw["method"],
               "neer": number(raw["NEER"]), "reer": number(raw["REER"]), "sample": raw["sample"]}
        key = (row["year"], row["basis"], row["method"])
        if key in keys:
            raise ValueError(f"Duplicate source key: {key}")
        keys.add(key)
        row["relative_price_index"] = 100 * row["reer"] / row["neer"] if row["reer"] is not None else None
        rows.append(row)
    by_key = {(r["year"], r["basis"], r["method"]): r for r in rows}
    for row in rows:
        y, b, m = row["year"], row["basis"], row["method"]
        prev = by_key.get((y - 1, b, m), {})
        nxt = by_key.get((y + 1, b, m), {})
        for index in ("neer", "reer"):
            row[index + "_yoy_pct"] = growth(row[index], prev.get(index))
            row[index + "_log_change"] = growth(row[index], prev.get(index), log=True)
            window = (prev, row, nxt)
            complete = all(r.get("sample") == row["sample"] and r.get(index) is not None for r in window)
            row[index + "_ma3"] = math.fsum(r[index] for r in window) / 3 if complete else None
        row["relative_price_log_change"] = growth(row["relative_price_index"], prev.get("relative_price_index"), log=True)
    order_b = {x["id"]: i for i, x in enumerate(BASIS)}
    order_m = {x["id"]: i for i, x in enumerate(METHODS)}
    rows.sort(key=lambda r: (r["year"], order_b[r["basis"]], order_m[r["method"]]))
    return [{k: r[k] for k in FIELDS} for r in rows]


def data_dictionary() -> list[dict]:
    def entry(name, unit, definition, missing="Blank in CSV; null in JSON"):
        return {"field": name, "unit": unit, "definition": definition, "missing_value": missing}
    return [
        entry("year", "calendar year", "Reference year of the source annual observation.", "Never missing"),
        entry("basis", "category", "TWEER: total trade; XEER: exports; MEER: imports.", "Never missing"),
        entry("method", "category", "Method identifier; see method-dictionary.csv.", "Never missing"),
        entry("neer", "index, 1929=100", "Nominal effective exchange rate; higher means nominal depreciation."),
        entry("reer", "index, 1929=100", "CPI-based real effective exchange rate; higher means real depreciation. Missing in 1920–1922."),
        entry("neer_yoy_pct", "percent", "100 × (NEER(t)/NEER(t−1) − 1); requires adjacent calendar years."),
        entry("reer_yoy_pct", "percent", "100 × (REER(t)/REER(t−1) − 1); requires adjacent calendar years."),
        entry("neer_log_change", "log points", "100 × ln(NEER(t)/NEER(t−1)); not an ordinary percentage change."),
        entry("reer_log_change", "log points", "100 × ln(REER(t)/REER(t−1)); not an ordinary percentage change."),
        entry("relative_price_index", "index, 1929=100", "100 × REER/NEER. For matched chains: cumulative chained relative-price component. For direct_current: real/nominal ratio."),
        entry("relative_price_log_change", "log points", "100 × Δln(REER/NEER). Exact real-minus-nominal log change. Inflation-differential interpretation applies to matched geometric chains; direct_current can include reweighting."),
        entry("neer_ma3", "index, source scale", "Centered three-calendar-year arithmetic mean of NEER levels; requires three observed years in the same sample segment. Not independently rebased."),
        entry("reer_ma3", "index, source scale", "Centered three-calendar-year arithmetic mean of REER levels; requires three observed years in the same sample segment. Not independently rebased."),
        entry("sample", "category", "Original label: pre-stabilisation extension (1920–1924) or analytical core (1925–1938).", "Never missing"),
    ]


def make_figures(out: Path, payload: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
    import numpy as np

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.titlesize": 15, "axes.labelsize": 10, "svg.fonttype": "none",
                         "svg.hashsalt": "dittrich-eer-analysis-v1", "axes.spines.top": False,
                         "axes.spines.right": False, "axes.edgecolor": "#cad3d9",
                         "axes.labelcolor": "#253448", "xtick.color": "#4c5e70",
                         "ytick.color": "#4c5e70", "text.color": "#253448"})
    navy, orange, teal, purple = "#234b72", "#c4662b", "#147d80", "#7d5c9d"
    rows = payload["series"]
    preferred = [r for r in rows if r["basis"] == "TWEER" and r["method"] == "paasche" and r["year"] >= 1925]
    years = [r["year"] for r in preferred]
    source = "Source: Adam Dittrich, Czechoslovakia EER reader edition (22 October 2026)."
    sub = "Total-trade weights · current-year geometric chain · annual observations"

    def setup(title, subtitle, ylabel, figsize=(10.8, 6.1)):
        fig, ax = plt.subplots(figsize=figsize)
        fig.subplots_adjust(left=.09, right=.97, bottom=.21, top=.77)
        fig.text(.09, .94, title, ha="left", va="top", size=16, weight="bold")
        fig.text(.09, .875, subtitle, ha="left", va="top", size=10, color="#566b80")
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", color="#e5e9ee", lw=.7)
        ax.set_axisbelow(True)
        ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True, nbins=8))
        return fig, ax

    def save(fig, ax, name, note, legend=True):
        if legend:
            ax.legend(loc="upper left", bbox_to_anchor=(0, 1.13), ncol=3,
                      frameon=False, fontsize=9, borderaxespad=0)
        fig.text(.09, .10, note, fontsize=9, ha="left", va="top", color="#4c5e70")
        fig.text(.09, .045, source, fontsize=8, ha="left", va="top", color="#66788b")
        fig.savefig(out / name, format="svg", metadata={"Date": RELEASE_DATE,
                    "Creator": "Adam Dittrich", "Title": name.removesuffix(".svg"),
                    "Description": note + " " + source + " " + PAGE})
        plt.close(fig)

    fig, ax = setup("Nominal and real effective exchange rates", sub, "Index, 1929 = 100")
    for field, label, color in [("neer", "NEER", navy), ("reer", "REER", orange)]:
        ax.plot(years, [r[field] for r in preferred], marker="o", ms=4, lw=2, color=color, label=label)
    ax.axhline(100, color="#8b99a5", lw=.8, ls="--")
    save(fig, ax, "eer-levels.svg", "Higher indices indicate depreciation. The reference value 100 is a normalisation.")

    fig, ax = setup("Annual changes in nominal and real indices", sub, "Annual change, %")
    ax.bar(np.array(years) - .18, [r["neer_yoy_pct"] for r in preferred], width=.36, color=navy, label="NEER")
    ax.bar(np.array(years) + .18, [r["reer_yoy_pct"] for r in preferred], width=.36, color=orange, label="REER")
    ax.axhline(0, color="#77899a", lw=.8)
    save(fig, ax, "eer-annual-changes.svg", "Change = 100 × (I(t) / I(t−1) − 1). The 1925 change uses the released 1924 observation.")

    fig, ax = setup("Chained relative-price component", sub, "100 × REER / NEER, 1929 = 100")
    ax.plot(years, [r["relative_price_index"] for r in preferred], marker="o", ms=4, lw=2.2, color=teal, label="Relative-price component")
    ax.axhline(100, color="#8b99a5", lw=.8, ls="--")
    r35 = next(r for r in preferred if r["year"] == 1935)
    ax.annotate(f"1935: {r35['relative_price_index']:.2f}", (1935, r35["relative_price_index"]),
                xytext=(1931, 91), color=teal, arrowprops={"arrowstyle": "-", "color": teal})
    save(fig, ax, "eer-relative-prices.svg", "A fall means relative-price movements reduce the real index relative to the nominal index.")

    fig, ax = setup("Annual real change: nominal and relative-price components", sub, "Annual log change × 100")
    nom = np.array([r["neer_log_change"] for r in preferred]); price = np.array([r["relative_price_log_change"] for r in preferred])
    ax.bar(years, nom, width=.62, color=navy, label="Nominal component")
    bottom = np.where(nom * price >= 0, nom, 0)
    ax.bar(years, price, bottom=bottom, width=.62, color=orange, label="Relative-price component")
    ax.plot(years, [r["reer_log_change"] for r in preferred], color=teal, marker="D", ms=4, lw=1.6, label="Real change (sum)")
    ax.axhline(0, color="#77899a", lw=.8)
    save(fig, ax, "eer-decomposition.svg", "Real log change = nominal log change + relative-price log change. Accounting decomposition.")

    fig, ax = setup("Sensitivity of the real index to its formula", "Total-trade REER · annual observations · 1929 = 100", "Index, 1929 = 100")
    matrix = [[next(r["reer"] for r in rows if r["year"] == y and r["basis"] == "TWEER" and r["method"] == m)
               for m in ("paasche", "laspeyres", "tornqvist", "fixed1929")] for y in years]
    ax.fill_between(years, [min(v) for v in matrix], [max(v) for v in matrix], color=navy, alpha=.16, label="Range across four chains")
    ax.plot(years, [r["reer"] for r in preferred], color=navy, marker="o", ms=3, lw=2, label="Preferred current-year chain")
    direct = [next(r["reer"] for r in rows if r["year"] == y and r["basis"] == "TWEER" and r["method"] == "direct_current") for y in years]
    ax.plot(years, direct, color=orange, ls="--", marker="s", ms=3, lw=1.8, label="Direct current-weighted")
    ax.axhline(100, color="#8b99a5", lw=.8, ls=":")
    save(fig, ax, "eer-method-sensitivity.svg", "The shaded range describes formula sensitivity. It is not a statistical confidence interval.")

    partners = payload["partners"]
    years_w = list(range(1920, 1939))
    weights = {(r["year"], r["partner"]): r for r in payload["weights"]}
    partners = sorted(partners, key=lambda p: weights[(1929, p)]["total_trade_weight"], reverse=True)
    matrix = np.array([[100 * weights[(y, p)]["total_trade_weight"] for y in years_w] for p in partners])
    fig, ax = setup("Changing composition of the fourteen-partner basket", "Total-trade weights · share within the included basket", "", figsize=(11.3, 7.6))
    fig.subplots_adjust(left=.20, right=.89, bottom=.18, top=.79)
    im = ax.imshow(matrix, cmap="Blues", vmin=0, vmax=math.ceil(float(matrix.max()) / 5) * 5,
                   aspect="auto", interpolation="nearest")
    ax.set_xticks(range(len(years_w))); ax.set_xticklabels(years_w, rotation=55, ha="right", fontsize=8)
    ax.set_yticks(range(len(partners))); ax.set_yticklabels(partners, fontsize=9)
    ax.grid(False)
    for spine in ax.spines.values(): spine.set_visible(False)
    cb = fig.colorbar(im, ax=ax, fraction=.027, pad=.025); cb.set_label("Basket weight, %")
    save(fig, ax, "eer-partner-weights.svg", "Partner weights sum to 100% within the basket. National basket coverage is shown separately.", legend=False)

    fig, ax = setup("Coverage of the EER trade basket", "Fourteen partners · shares of national trade · annual observations", "Coverage, %")
    cov = payload["coverage"]
    for key, label, col, ls in [("export_coverage", "Exports", navy, "-"), ("import_coverage", "Imports", orange, "--"), ("total_trade_coverage", "Total trade", teal, "-")]:
        ax.plot([r["year"] for r in cov], [100*r[key] for r in cov], lw=2, marker="o", ms=3, color=col, ls=ls, label=label)
    ax.set_ylim(70, 100)
    save(fig, ax, "eer-coverage.svg", "National coverage shares are distinct from partner weights normalised within the basket.")

    fig, ax = setup("Real effective exchange rates by trade basis", "Current-year geometric chains · annual observations · 1929 = 100", "Index, 1929 = 100")
    for basis, col, ls in [("TWEER", navy, "-"), ("XEER", teal, "--"), ("MEER", orange, ":")]:
        vals = [next(r["reer"] for r in rows if r["year"] == y and r["basis"] == basis and r["method"] == "paasche") for y in years]
        label = next(b["label"] for b in BASIS if b["id"] == basis)
        ax.plot(years, vals, lw=2, marker="o", ms=3, color=col, ls=ls, label=label)
    ax.axhline(100, color="#8b99a5", lw=.8, ls="--")
    save(fig, ax, "eer-trade-bases.svg", "The trade basis changes the partner weights. All three series retain the same index direction.")


def make_readme() -> str:
    return f"""Czechoslovakia EER: Annual Analysis Extension
Version {VERSION}. Released {RELEASE_DATE}.
Author: Adam Dittrich
Dataset page: {PAGE}

CONTENTS AND SOURCES
annual-analysis.csv and annual-analysis.json contain 247 annual specification rows:
13 nominal/real pairs over 1920–1938. The reader edition supplies 247 NEER values and
208 REER values (REER begins in 1923). All 26 observed series equal 100 in 1929.
The original four EER reader tables are included in the ZIP under source/.
The original Excel reader edition is dated 22 October 2026:
{DATA_URL}Czechoslovakia_EER_1920_1938.xlsx
The related replication deposit is https://doi.org/10.3886/E251023V1.
This extension is a separately dated analytical extension, not a new DOI version.
metadata.json records source URLs and SHA-256 hashes. No original observations,
weights or coverage shares are changed. The source precision is retained.
Construction notes, bilateral inputs, currency-unit rules and an independent
source-level reproducer are available in the companion documentation:
{DATA_URL}eer-documentation/provenance-notes.txt
{DATA_URL}eer-documentation/README.txt

READING THE INDICES
Higher NEER means nominal depreciation. Higher CPI-based REER means real
depreciation. The value 100 is a reference-year normalisation. It does not identify
an equilibrium exchange rate. CPI-based REER is a broad relative-price measure,
not a direct observation of exporters' costs, profit margins or non-price factors.
TWEER uses total-trade weights, XEER export weights and MEER import weights.
method-dictionary.csv describes the five formulas. direct_current is supplied for
total trade only. The other four specifications are geometric chains.

DERIVED COLUMNS
Annual percent change: 100 * (I[t] / I[t-1] - 1).
Annual log change: 100 * ln(I[t] / I[t-1]), measured in log points.
Relative-price index C[t]: 100 * REER[t] / NEER[t].
Relative-price log change: 100 * ln(C[t] / C[t-1]).
The exact accounting identity is real log change = nominal log change +
relative-price log change. With identical matched geometric-chain weights,
the last term is the weighted foreign CPI log change less the domestic CPI log
change. C[t] is a cumulative chained relative-price component; time-varying
weights mean it is not generally a current-weighted relative-CPI level index.
For direct_current, the ratio remains defined, but its annual residual can include
reweighting and must not be interpreted solely as an inflation differential.

SMOOTHING
neer_ma3 and reer_ma3 are centered three-calendar-year arithmetic averages of
index levels: (I[t-1] + I[t] + I[t+1]) / 3. A complete observed window is required.
Smoothing is calculated separately within each source sample segment: the
1920–1924 pre-stabilisation extension and the 1925–1938 analytical core.
It never crosses the 1924/1925 boundary. Endpoints and missing-data windows remain
blank. A moving average is only a descriptive overlay. The annual observations
remain the primary series. A moving average need not equal exactly 100 in 1929,
because it averages source-scale index levels and is not separately rebased.

DISPLAY AND MISSINGNESS
The default analytical interval is 1925–1938. The source's early extension and
sample field are preserved in the exports. REER in 1920–1922 remains unavailable.
CSV missing values are empty fields; JSON uses null. No interpolation is applied.
Changes require adjacent observed calendar years. The 1925 annual change uses
the released 1924 observation even though the default chart begins in 1925.
Reference-year rebasing is a display transformation: 100 * I[t] / I[b]. It does
not change annual growth rates. Smooth overlays use the same scaling factor as
their corresponding observed series. See data-dictionary.csv for every field.

PARTNER WEIGHTS AND COVERAGE
The weights table has 14 partners in each of 19 years, with total-trade, export
and import weights. Each weight family sums to one within the included basket.
Coverage measures that basket's share of national trade. Both are stored as
fractions from zero to one; charts multiply them by 100. Coverage is not applied
as a scalar adjustment to the EER. The eight SVG figures carry method and source
labels. The method-sensitivity range describes alternative specifications; it is
not a confidence interval.

REPRODUCING THE PACKAGE
Use Python 3.10 or later. Install the optional plotting dependency from
requirements.txt to regenerate SVG figures. From an extracted ZIP directory:
    python build_annual_analysis.py
    python check_eer_analysis.py
From the website source repository:
    python assets/files/datasets/eer-analysis/build_annual_analysis.py
    python scripts/check_eer_analysis.py
For CSV/JSON and documentation only, append --skip-figures. Use --data-dir PATH
and --output-dir PATH to choose source and destination directories explicitly.
The default source location is source/ beside this script in the ZIP, or the
parent datasets directory in the repository. Numerical computation needs only
the Python standard library. Matplotlib is required only for the static figures.

VALIDATION
The independent checker verifies source hashes, source/derived value agreement,
the 1929 normalisation, method availability, calendar continuity, missing-value
handling, smoothing boundaries, exact log-change decomposition, preferred-series
agreement, partner-weight sums and selected reference calculations. It checks
the arithmetic of this extension; historical input construction is documented
in the companion provenance notes and source-level reproduction materials.

CITATION AND REUSE
Cite Adam Dittrich, Czechoslovakia's Effective Exchange Rates, 1920–1938, Excel
reader edition of 22 October 2026, and identify this analysis extension,
version {VERSION} ({RELEASE_DATE}). Cite the related replication deposit separately
as doi:10.3886/E251023V1. The new derived tables, figures and documentation are
licensed CC BY 4.0; new software is licensed MIT. See LICENSE.txt. The original
reader source files retain their existing rights and terms. This extension
does not assign new rights to the original historical inputs.

METHOD REFERENCES
ECB, Harmonised competitiveness indicators (CPI interpretation and caveats):
https://www.ecb.europa.eu/stats/balance_of_payments_and_external/hci/html/index.en.html
BIS, Effective exchange rates (geometric aggregation and reference-year meaning):
https://data.bis.org/topics/EER
The BIS uses appreciation-up indices; the present dataset retains the opposite,
depreciation-up convention documented in its reader workbook.
"""


def build(data_dir: Path, out: Path, figures: bool = True) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    for name in SOURCE_NAMES:
        if not (data_dir / name).is_file():
            raise FileNotFoundError(f"Required EER source file missing: {data_dir / name}")
    series = build_series(data_dir)
    weights = [{"year": int(r["year"]), "partner": r["partner"],
                **{k: float(r[k]) for k in ("total_trade_weight", "export_weight", "import_weight")}}
               for r in read_csv(data_dir / "eer-partner-weights.csv")]
    coverage = [{"year": int(r["year"]), **{k: float(r[k]) for k in ("export_coverage", "import_coverage", "total_trade_coverage")}}
                for r in read_csv(data_dir / "eer-basket-coverage.csv")]
    hashes = {name: sha256(data_dir / name) for name in SOURCE_NAMES}
    source = {"title": "Czechoslovakia EER, 1920–1938: Excel reader edition", "author": "Adam Dittrich",
              "reader_edition_date": "2026-10-22", "page": PAGE, "related_deposit_doi": "10.3886/E251023V1",
              "construction_notes": DATA_URL + "eer-documentation/provenance-notes.txt",
              "files": [{"name": n, "url": DATA_URL+n, "sha256": hashes[n]} for n in SOURCE_NAMES]}
    payload = {"schema_version": "1.0", "version": VERSION, "release_date": RELEASE_DATE,
               "basis": BASIS, "methods": METHODS, "years": sorted({r["year"] for r in series}),
               "partners": sorted({r["partner"] for r in weights}), "series": series,
               "weights": weights, "coverage": coverage, "source": source}
    write_csv(out / "annual-analysis.csv", series, FIELDS)
    (out / "annual-analysis.json").write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n", encoding="utf-8")
    write_csv(out / "method-dictionary.csv", METHODS, list(METHODS[0]))
    dd = data_dictionary(); write_csv(out / "data-dictionary.csv", dd, list(dd[0]))
    metadata = {"title": "Czechoslovakia EER: Annual Analysis Extension", "version": VERSION,
                "release_date": RELEASE_DATE, "source": source, "row_count": len(series),
                "index_series_count": 26, "available_index_observations": 455,
                "frequency": "Annual", "reference_year": 1929, "index_direction": "Higher means depreciation",
                "preferred_method": "paasche", "default_basis": "TWEER", "default_period": [1925, 1938],
                "missing_values": {"csv": "empty field", "json": None},
                "smoothing": {"method": "centered three-year arithmetic mean of levels", "window": 3,
                              "complete_calendar_window_required": True, "crosses_sample_boundary": False,
                              "independently_rebased": False},
                "change_uses_previous_observation_outside_display_range": True,
                "direct_current_price_residual": "May include reweighting; not a pure inflation contribution",
                "licences": {"new_tables_figures_documentation": "CC BY 4.0",
                             "new_software": "MIT", "terms_file": "LICENSE.txt",
                             "source_reader_files": "Existing terms retained; no new licence asserted"},
                "figures": FIGURES if figures else [], "fields": dd}
    (out / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")
    (out / "README.txt").write_text(make_readme(), encoding="utf-8")
    (out / "CHANGELOG.txt").write_text(f"{VERSION} — {RELEASE_DATE}\nAdded annual percentage and log changes, matched nominal/real ratios and log\ncomponents, centered three-year overlays, eight figures, machine-readable\ndictionaries and reproducible analysis exports. Source reader values are preserved.\n", encoding="utf-8")
    (out / "requirements.txt").write_text("# Optional, only for static figure reproduction\nmatplotlib>=3.8,<4\n", encoding="utf-8")
    (out / "LICENSE.txt").write_text(LICENSE, encoding="utf-8")
    if figures:
        make_figures(out, payload)
    script = Path(__file__).resolve()
    if script.parent != out.resolve():
        shutil.copy2(script, out / script.name)
    candidate_checkers = [script.parent / "check_eer_analysis.py", script.parents[4] / "scripts/check_eer_analysis.py"]
    checker = next((p for p in candidate_checkers if p.is_file()), None)
    packaged = ["annual-analysis.csv", "annual-analysis.json", "metadata.json", "data-dictionary.csv",
                "method-dictionary.csv", "README.txt", "CHANGELOG.txt", "requirements.txt", "LICENSE.txt", "build_annual_analysis.py"]
    if figures:
        packaged += FIGURES
    with zipfile.ZipFile(out / "annual-analysis.zip", "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        def put(name, content):
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 13, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        for name in packaged:
            put(name, (out / name).read_bytes())
        for name in SOURCE_NAMES:
            put("source/" + name, (data_dir / name).read_bytes())
        if checker:
            put("check_eer_analysis.py", checker.read_bytes())
    return payload


def main():
    here = Path(__file__).resolve().parent
    default_data = here / "source" if (here / "source").is_dir() else here.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=default_data)
    parser.add_argument("--output-dir", type=Path, default=here)
    parser.add_argument("--skip-figures", action="store_true")
    args = parser.parse_args()
    result = build(args.data_dir.resolve(), args.output_dir.resolve(), figures=not args.skip_figures)
    print(f"Built {len(result['series'])} annual specification rows and "
          f"{0 if args.skip_figures else len(FIGURES)} figures in {args.output_dir}")


if __name__ == "__main__":
    main()
