#!/usr/bin/env python3
"""Build transparent smoothers and trade indicators from the supplied monthly CSV.

Run from a website checkout, or unzip the research package and run this script
there. The input CSV is never modified. Dependencies: NumPy and Matplotlib.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import zipfile

import numpy as np

UPDATED = "2026-11-13"
LAMBDA = 129600.0
MIN_HP_MONTHS = 24
FIELDS = [
    "date", "method", "exports_million_kc", "imports_million_kc",
    "trade_balance_million_kc", "total_trade_million_kc",
    "export_import_ratio_pct", "normalized_balance_pct",
]
METHODS = [
    {"id": "raw", "label": "Observed monthly values",
     "description": "Original monthly exports and imports, with indicators calculated from those flows."},
    {"id": "trailing3", "label": "3-month trailing average", "window_months": 3,
     "description": "Mean of the current month and preceding two months; complete windows only."},
    {"id": "trailing6", "label": "6-month trailing average", "window_months": 6,
     "description": "Mean of the current month and preceding five months; complete windows only."},
    {"id": "trailing12", "label": "12-month trailing average", "window_months": 12,
     "description": "Mean of the current month and preceding eleven months; complete windows only. This smooth series lags turning points."},
    {"id": "centered12", "label": "Centered 12-month average (2 × 12)", "window_months": 13,
     "description": "Average of two adjacent 12-month means: weights 1/24 at t−6 and t+6, and 1/12 at t−5 through t+5. The first and last six months are unavailable."},
    {"id": "hp129600", "label": "HP trend (λ = 129,600)", "lambda": 129600,
     "minimum_segment_months": MIN_HP_MONTHS,
     "description": "Two-sided Hodrick–Prescott trend fitted to monthly flow levels over each complete contiguous sample, using λ = 129,600. At least 24 consecutive observed months are required."},
]


def month_id(value: date) -> int:
    return value.year * 12 + value.month - 1


def month_date(value: int) -> str:
    year, month = divmod(value, 12)
    return date(year, month + 1, 1).isoformat()


def load_source(path: Path):
    records = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
    if not records:
        raise ValueError("The source has no observations.")
    observed = {}
    previous = None
    for row in records:
        stamp = date.fromisoformat(row["date"])
        if stamp.day != 1 or stamp.isoformat() != row["date"]:
            raise ValueError(f"Expected a YYYY-MM-01 monthly date: {row['date']!r}")
        key = month_id(stamp)
        if previous is not None and key <= previous:
            raise ValueError("Source dates must be unique and strictly increasing.")
        previous = key
        values = []
        for field in ("exports_million_kc", "imports_million_kc"):
            raw = row[field].strip()
            value = float(raw) if raw else np.nan
            if raw and (not np.isfinite(value) or value < 0):
                raise ValueError(f"Invalid nonnegative flow: {row['date']} {field}={raw}")
            values.append(value)
        observed[key] = values
    calendar = list(range(min(observed), max(observed) + 1))
    dates = [month_date(key) for key in calendar]
    flows = np.array([observed.get(key, [np.nan, np.nan]) for key in calendar], dtype=float)
    gaps = [month_date(key) for key in calendar if key not in observed]
    return dates, flows, gaps, len(records)


def complete_runs(valid):
    start = None
    for index, available in enumerate(list(valid) + [False]):
        if available and start is None:
            start = index
        elif not available and start is not None:
            yield start, index
            start = None


def smooth_flows(flows: np.ndarray) -> dict[str, np.ndarray]:
    """Use common valid X/M support for every smoothed pair; preserve raw values."""
    result = {"raw": flows.copy()}
    valid = np.isfinite(flows).all(axis=1)
    n = len(flows)
    for window in (3, 6, 12):
        out = np.full_like(flows, np.nan)
        for i in range(window - 1, n):
            if valid[i - window + 1:i + 1].all():
                out[i] = flows[i - window + 1:i + 1].mean(axis=0)
        result[f"trailing{window}"] = out
    centered = np.full_like(flows, np.nan)
    weights = np.array([1] + [2] * 11 + [1], dtype=float) / 24
    for i in range(6, n - 6):
        if valid[i - 6:i + 7].all():
            centered[i] = weights @ flows[i - 6:i + 7]
    result["centered12"] = centered
    hp = np.full_like(flows, np.nan)
    for start, stop in complete_runs(valid):
        size = stop - start
        if size < MIN_HP_MONTHS:
            continue
        # D contains the second differences of the latent trend. Solving this
        # positive-definite linear system minimizes the standard HP objective.
        d = np.diff(np.eye(size), n=2, axis=0)
        hp[start:stop] = np.linalg.solve(np.eye(size) + LAMBDA * d.T @ d, flows[start:stop])
    result["hp129600"] = hp
    return result


def finite(value):
    return float(value) if np.isfinite(value) else None


def indicator_row(stamp, method, values):
    x, m = (finite(value) for value in values)
    pair = x is not None and m is not None
    balance = x - m if pair else None
    turnover = x + m if pair else None
    return {
        "date": stamp, "method": method,
        "exports_million_kc": x, "imports_million_kc": m,
        "trade_balance_million_kc": balance,
        "total_trade_million_kc": turnover,
        "export_import_ratio_pct": 100 * x / m if pair and m > 0 else None,
        "normalized_balance_pct": 100 * balance / turnover if pair and turnover > 0 else None,
    }


def write_csv(path, fields, records):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def write_figures(output, dates, rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    from matplotlib.lines import Line2D
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10,
        "axes.titlesize": 15, "axes.labelsize": 10,
        "axes.titleweight": "normal", "axes.labelcolor": "#465a63",
        "text.color": "#163343", "xtick.color": "#465a63", "ytick.color": "#465a63",
        "axes.edgecolor": "#c9c3b9", "svg.fonttype": "none",
        "svg.hashsalt": "czechoslovak-monthly-trade-analysis-v1",
    })
    blue, orange, green, purple = "#1f77b4", "#ff7f0e", "#2ca02c", "#9467bd"
    xs = [date.fromisoformat(stamp) for stamp in dates]
    table = {method["id"]: [row for row in rows if row["method"] == method["id"]] for method in METHODS}

    def values(method, field):
        return np.array([row[field] if row[field] is not None else np.nan for row in table[method]])

    def style(ax, units, baseline=None):
        ax.set_ylabel(units, labelpad=12)
        ax.set_xlim(xs[0], xs[-1])
        ax.xaxis.set_major_locator(mdates.YearLocator(2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.grid(axis="y", color="#e6e2dc", linewidth=.7)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(length=3)
        if baseline is not None:
            ax.axhline(baseline, color="#6f6b65", lw=.9, ls=(0, (4, 3)))

    def finish(fig, filename, title, subtitle, extra=None):
        fig.suptitle(title, x=.105, y=.97, ha="left", fontsize=15)
        fig.text(.105, .914, subtitle, ha="left", va="top", fontsize=10, color="#53636a")
        fig.text(.105, .059, "Source: Adam Dittrich, Czechoslovak Foreign Trade: Interwar Dataset; supplied monthly observations.",
                 ha="left", fontsize=8.1, color="#53636a")
        note = extra or "Current-price values; smoothing is neither deflation nor a formal seasonal adjustment."
        fig.text(.105, .026, note, ha="left", fontsize=8.1, color="#53636a")
        fig.savefig(output / filename, format="svg", metadata={
            "Date": UPDATED, "Title": title, "Description": subtitle + " " + note,
            "Creator": "Adam Dittrich; reproducible monthly-analysis build script",
        })
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(10.8, 5.8))
    fig.subplots_adjust(left=.105, right=.97, top=.80, bottom=.17)
    for field, color, label, dash in [
        ("exports_million_kc", blue, "Exports", "-"),
        ("imports_million_kc", orange, "Imports", (0, (5, 2))),
    ]:
        ax.plot(xs, values("raw", field), color=color, lw=.8, alpha=.30)
        ax.plot(xs, values("trailing12", field), color=color, lw=2.3, label=label, linestyle=dash)
    style(ax, "Million current Kč")
    ax.set_ylim(bottom=0)
    ax.legend(loc="upper right", frameon=False, ncol=2)
    finish(fig, "monthly-flows.svg", "Monthly exports and imports, 1924–1938",
           "Strong lines: 12-month trailing averages · faint lines: observed monthly values")

    specs = [
        ("monthly-balance.svg", "The monthly trade balance", "trade_balance_million_kc", green,
         "Million current Kč", 0, "Positive values indicate a surplus; negative values a deficit."),
        ("monthly-coverage.svg", "Exports relative to imports", "export_import_ratio_pct", purple,
         "Export coverage of imports (%)", 100, "100 × exports / imports; the dashed line marks equal export and import values."),
        ("monthly-normalized-balance.svg", "The balance relative to total trade", "normalized_balance_pct", green,
         "Balance / total trade (%)", 0, "100 × (exports − imports) / (exports + imports); the dashed line marks balance."),
        ("monthly-turnover.svg", "Monthly total trade", "total_trade_million_kc", blue,
         "Million current Kč", None, "Exports plus imports; the smoothed line is an average monthly value, not a 12-month total."),
    ]
    for filename, title, field, color, units, baseline, note in specs:
        fig, ax = plt.subplots(figsize=(10.8, 5.8))
        fig.subplots_adjust(left=.105, right=.97, top=.80, bottom=.17)
        observed, smooth = values("raw", field), values("trailing12", field)
        ax.plot(xs, observed, color=color, lw=.85, alpha=.32, label="Observed monthly")
        ax.plot(xs, smooth, color=color, lw=2.3, label="From 12-month average flows")
        if field in {"trade_balance_million_kc", "normalized_balance_pct"}:
            ax.fill_between(xs, smooth, 0, where=smooth >= 0, color=green, alpha=.10, interpolate=True)
            ax.fill_between(xs, smooth, 0, where=smooth < 0, color="#d62728", alpha=.12, interpolate=True)
        style(ax, units, baseline)
        if baseline is None:
            ax.set_ylim(bottom=0)
        ax.legend(loc="upper right", frameon=False, ncol=2, fontsize=9)
        finish(fig, filename, title + ", 1924–1938", note,
               "Indicators use the same smoothed exports/imports. Current-price flows; no formal seasonal adjustment.")

    fig, axes = plt.subplots(2, 1, figsize=(10.8, 8.2), sharex=True)
    fig.subplots_adjust(left=.105, right=.97, top=.85, bottom=.13, hspace=.30)
    for ax, field, color, label in zip(axes,
            ["exports_million_kc", "imports_million_kc"], [blue, orange], ["Exports", "Imports"]):
        ax.plot(xs, values("raw", field), color=color, lw=.75, alpha=.28)
        ax.plot(xs, values("trailing12", field), color=color, lw=1.8)
        ax.plot(xs, values("hp129600", field), color="#243746", lw=2, linestyle=(0, (5, 2)))
        style(ax, "Million current Kč")
        ax.set_ylim(bottom=0)
        ax.text(.015, .92, label, transform=ax.transAxes, fontsize=12, color=color,
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": .85, "pad": 2})
    axes[0].legend(handles=[
        Line2D([0], [0], color="#80909a", lw=.8, alpha=.5, label="Observed monthly"),
        Line2D([0], [0], color=blue, lw=1.8, label="12-month trailing average"),
        Line2D([0], [0], color="#243746", lw=2, linestyle=(0, (5, 2)), label="HP trend (λ = 129,600)"),
    ], loc="upper right", frameon=False, fontsize=9)
    finish(fig, "monthly-hp-comparison.svg", "Comparing moving averages and HP trends",
           "Monthly exports and imports, 1924–1938 · filters estimated before any display-range selection",
           "HP uses full-sample flow levels; endpoints and abrupt breaks require care. Current values; no seasonal adjustment.")


def main():
    here = Path(__file__).resolve().parent
    default_source = here / "source-monthly.csv" if (here / "source-monthly.csv").exists() else here.parent / "foreign-trade-monthly.csv"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=default_source)
    parser.add_argument("--output", type=Path, default=here)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    dates, flows, gaps, source_rows = load_source(args.source)
    smooth = smooth_flows(flows)
    rows = [indicator_row(stamp, method["id"], smooth[method["id"]][i])
            for method in METHODS for i, stamp in enumerate(dates)]
    source_sha = hashlib.sha256(args.source.read_bytes()).hexdigest()
    metadata = {
        "schema_version": 1, "updated": UPDATED,
        "title": "Czechoslovak foreign trade: monthly smoothing and trade indicators",
        "source": {"file": "foreign-trade-monthly.csv", "sha256": source_sha,
                   "observations": source_rows, "calendar_months": len(dates),
                   "start": dates[0], "end": dates[-1], "inserted_missing_months": gaps,
                   "units": "million current Kč", "price_basis": "nominal; not deflated"},
        "methods": METHODS,
        "default_method": "trailing12",
        "ratio_convention": "Smooth exports and imports first, then calculate all indicators; never average monthly ratios.",
        "missing_value_convention": "JSON null / CSV blank; no zero-filling or interpolation. Smoothers require common complete export/import support.",
        "display_range_convention": "Filter the full available calendar before slicing a display range; zooming does not refit a smoother.",
        "hp_convention": "Solve (I + 129600 D'D) tau = y on flow levels; D is the second-difference matrix. Each common complete run requires at least 24 months.",
        "interpretation": [
            "Moving averages and HP trends are descriptive smoothers, not seasonally adjusted or constant-price series.",
            "Trailing averages lag turning points. Centered averages use future months and omit six months at each end.",
            "HP is a two-sided full-sample trend; endpoints and abrupt changes require caution.",
            "Smoothing does not harmonize changes in territory, classification, valuation or currency; the supplied series' scope is retained.",
            "A 12-month mean is an average monthly flow. Its export/import ratio equals the ratio of the corresponding 12-month sums.",
        ],
        "references": [
            {"citation": "Ravn, M. O., and H. Uhlig. 2002. On Adjusting the Hodrick–Prescott Filter for the Frequency of Observations. Review of Economics and Statistics 84(2): 371–376.",
             "url": "https://doi.org/10.1162/003465302317411604"},
            {"citation": "Statsmodels documentation: Hodrick–Prescott filter (monthly λ = 129,600).",
             "url": "https://www.statsmodels.org/stable/generated/statsmodels.tsa.filters.hp_filter.hpfilter.html"},
            {"citation": "Hyndman and Athanasopoulos, Forecasting: Principles and Practice, moving averages and classical decomposition.",
             "url": "https://otexts.com/fpp3/decomposition.html"},
        ],
    }
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    payload = {"schema_version": 1, "updated": UPDATED, "source": metadata["source"],
               "default_method": "trailing12", "methods": METHODS, "rows": rows}
    (output / "monthly-analysis.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8")
    write_csv(output / "monthly-analysis.csv", FIELDS, rows)
    write_figures(output, dates, rows)
    # Ship readable provenance and build files alongside the data and figures.
    for filename in ("build_monthly_analysis.py", "requirements.txt", "README.txt", "data-dictionary.csv"):
        if here != output:
            (output / filename).write_bytes((here / filename).read_bytes())
    members = {p.name: p.read_bytes() for p in output.iterdir()
               if p.is_file() and p.suffix in {".py", ".txt", ".csv", ".json", ".svg"}}
    members["source-monthly.csv"] = args.source.read_bytes()
    with zipfile.ZipFile(output / "monthly-analysis.zip", "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(members.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    print(f"Built {len(rows)} rows ({len(METHODS)} methods × {len(dates)} calendar months), six SVG figures and a reproducible ZIP.")
    print(f"Source SHA-256: {source_sha}; inserted missing months: {len(gaps)}")


if __name__ == "__main__":
    main()
