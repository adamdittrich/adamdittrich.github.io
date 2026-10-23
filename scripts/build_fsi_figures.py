#!/usr/bin/env python3
"""Build the financial-stress reader figures from the released replication CSVs.

Usage:
    python scripts/build_fsi_figures.py --source /path/to/Replication_Package

The source may be the replication root (with data/ and results/ subdirectories)
or a flat directory containing the same CSVs. No models are re-estimated and no
observations are imputed. Figures use the stored results at full precision.
Dependencies: pandas, numpy, matplotlib.
"""

from __future__ import annotations

import argparse
from html import escape
import os
from pathlib import Path
import re
import tempfile

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "dittrich-fsi-matplotlib"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.lines import Line2D
from matplotlib.ticker import MultipleLocator, FormatStrFormatter
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
READER = ROOT / "assets/files/datasets/fsi"
if not READER.is_dir():
    READER = Path(__file__).resolve().parent
INK = "#162b36"
MUTED = "#53636a"
BURGUNDY = "#7a2e34"
TEAL = "#346a73"
OCHRE = "#a67932"
GRID = "#e5e2dc"
SOFT = "#f5f1e9"
WHITE = "#ffffff"
BREAK = pd.Timestamp("1934-02-01")

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 11,
    "text.color": INK,
    "axes.labelcolor": MUTED,
    "axes.edgecolor": GRID,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.titlecolor": INK,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.spines.left": False,
    "axes.labelsize": 11,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "figure.facecolor": WHITE,
    "axes.facecolor": WHITE,
    "savefig.facecolor": WHITE,
    "svg.fonttype": "none",
    "svg.hashsalt": "dittrich-financial-stress-reader-2026",
    "lines.solid_capstyle": "round",
    "legend.frameon": False,
    "legend.fontsize": 10,
})


def read_csv(source: Path, name: str) -> pd.DataFrame:
    for candidate in (source / name, source / "data" / name, source / "results" / name):
        if candidate.is_file():
            frame = pd.read_csv(candidate)
            if "date" in frame:
                frame["date"] = pd.to_datetime(frame["date"])
            return frame
    raise FileNotFoundError(f"Cannot find {name} in {source}")


def header(fig, title, subtitle):
    fig.text(.075, .956, title, fontsize=19, fontfamily="DejaVu Serif", va="top")
    fig.text(.075, .904, subtitle, fontsize=10.6, color=MUTED, va="top")


def style_axis(ax, *, dates=None, zero=True):
    ax.set_axisbelow(True)
    ax.grid(axis="y", color=GRID, linewidth=.7)
    ax.tick_params(axis="both", length=0, pad=7)
    if zero:
        ax.axhline(0, color="#a8aaa6", linewidth=.8, zorder=1)
    if dates is not None:
        ax.set_xlim(dates.min(), dates.max())
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))


def footer(fig, note):
    fig.text(.075, .036, note, fontsize=9.2, color=MUTED, va="bottom")


def save(fig, out: Path, name: str, title: str, description: str):
    out.mkdir(parents=True, exist_ok=True)
    svg = out / f"{name}.svg"
    fig.savefig(svg, metadata={"Date": None, "Creator": "Adam Dittrich dataset reader"})
    fig.savefig(out / f"{name}.png", dpi=180, metadata={"Author": "Adam Dittrich"})
    raw = svg.read_text(encoding="utf-8")
    raw = re.sub(r"<svg\b", '<svg role="img" aria-labelledby="figure-title figure-description"', raw, count=1)
    root_end = raw.index(">", raw.index("<svg")) + 1
    raw = raw[:root_end] + (
        f'\n <title id="figure-title">{escape(title)}</title>'
        f'\n <desc id="figure-description">{escape(description)}</desc>\n'
    ) + raw[root_end:]
    svg.write_text(raw, encoding="utf-8")
    plt.close(fig)
    print(name)


def overview(data, episodes, out):
    fig, ax = plt.subplots(figsize=(10.4, 5.7))
    fig.subplots_adjust(left=.085, right=.97, bottom=.19, top=.79)
    header(fig, "Financial stress peaks in March 1932",
           "Narrow financial stress (FSI) and broad macro-financial distress (MFSI), November 1929–August 1938")
    style_axis(ax, dates=data.date)
    for _, row in episodes[episodes["index"] == "FSI"].iterrows():
        start = pd.Timestamp(row.start)
        end = pd.Timestamp(row.end) + pd.offsets.MonthBegin(1)
        ax.axvspan(start, end, color=BURGUNDY, alpha=.055, linewidth=0, zorder=0)
    ax.plot(data.date, data.financial_stress_index, color=BURGUNDY, linewidth=2.2,
            label="FSI · financial indicators only", zorder=4)
    ax.plot(data.date, data.macro_financial_stress_index, color=TEAL, linewidth=1.9,
            label="MFSI · adds real-economy distress", zorder=3)
    ax.axvline(BREAK, color=MUTED, linewidth=.9, linestyle=(0, (3, 3)), zorder=2)
    ax.text(BREAK + pd.Timedelta(days=42), 1.29, "February 1934\nreserve reform", fontsize=9.2,
            va="top", color=MUTED, bbox={"facecolor": WHITE, "edgecolor": "none", "alpha": .9, "pad": 1.8})
    peak = data.loc[data.financial_stress_index.idxmax()]
    ax.scatter([peak.date], [peak.financial_stress_index], color=BURGUNDY, s=31, zorder=5)
    ax.annotate(f"March 1932 · {peak.financial_stress_index:.3f}",
                xy=(peak.date, peak.financial_stress_index),
                xytext=(pd.Timestamp("1930-01-01"), 1.34),
                arrowprops={"arrowstyle": "-", "color": BURGUNDY, "lw": .9},
                fontsize=10, color=BURGUNDY)
    ax.set_ylim(-1.12, 1.48)
    ax.set_ylabel("Index points")
    ax.yaxis.set_major_locator(MultipleLocator(.5))
    ax.legend(loc="upper left", bbox_to_anchor=(0, -.145), ncol=2, handlelength=2.6,
              columnspacing=2.5, borderaxespad=0)
    footer(fig, "Zero is the sample mean. Pale bands mark the FSI’s high-stress months (mean + one sample SD).")
    save(fig, out, "fsi-overview", "Financial stress peaks in March 1932",
         "Monthly narrow FSI and broad MFSI, November 1929 to August 1938. Both peak in March 1932. "
         "Pale bands identify narrow-FSI high-stress episodes. A vertical marker identifies the February 1934 reserve reform. "
         "The indices average standardized components, so their index-point scales are not unit-standard-deviation scales.")


def sectors(data, out):
    fig, axes = plt.subplots(3, 1, figsize=(10.4, 7.2), sharex=True, sharey=True)
    fig.subplots_adjust(left=.085, right=.97, top=.81, bottom=.115, hspace=.35)
    header(fig, "The financial and real-economy peaks are distinct",
           "Three equal-weight block averages · the real-distress block enters MFSI, but not the narrow FSI")
    specs = [
        ("market_block", "Financial markets", "4 indicators", BURGUNDY),
        ("banking_monetary_block", "Banking and monetary conditions", "4 indicators", TEAL),
        ("real_distress_block", "Real-economy distress", "3 indicators", OCHRE),
    ]
    for ax, (column, label, count, color) in zip(axes, specs):
        style_axis(ax, dates=data.date)
        ax.plot(data.date, data[column], color=color, linewidth=1.9)
        ax.set_ylim(-1.95, 2.2)
        ax.set_yticks([-1, 0, 1, 2])
        ax.axvline(BREAK, color="#c8c6c0", linestyle=(0, (3, 3)), linewidth=.8)
        ax.text(0, 1.055, label, transform=ax.transAxes, fontsize=11.2, weight="bold", color=color)
        ax.text(1, 1.055, count, transform=ax.transAxes, fontsize=9.3, ha="right", color=MUTED)
        peak = data.loc[data[column].idxmax()]
        ax.scatter([peak.date], [peak[column]], s=23, color=color, zorder=5)
        ax.annotate(peak.date.strftime("%B %Y"), xy=(peak.date, peak[column]),
                    xytext=(pd.Timestamp("1934-09-01"), 1.55),
                    arrowprops={"arrowstyle": "-", "color": color, "lw": .8},
                    fontsize=9.4, color=color, va="center")
    axes[1].set_ylabel("Block index points")
    footer(fig, "All panels use the same vertical scale. Dashed markers identify February 1934. Higher values indicate more stress.")
    save(fig, out, "fsi-sector-sequence", "Financial and real-economy stress peak at different times",
         "Three monthly blocks on an identical vertical scale. Market stress peaks in May 1932; banking and monetary stress "
         "peaks in March 1932; real-economy distress peaks in March 1933. The real block includes unemployment, bankruptcies, "
         "and court-administered settlements.")


def components(data, out):
    fig = plt.figure(figsize=(10.4, 7.6))
    grid = fig.add_gridspec(3, 1, height_ratios=[4, 4, 3], left=.263, right=.97,
                           top=.81, bottom=.21, hspace=.39)
    header(fig, "Eleven indicators reveal the composition of stress",
           "Each row is a stress-oriented z-score · all 106 complete months · positive values mean greater stress")
    cmap = LinearSegmentedColormap.from_list("fsi_stress", ["#346a73", "#fbfaf7", "#8c3740"])
    blocks = [
        ("FINANCIAL MARKETS", ["stock_index", "bond_yield", "stock_turnover", "equity_yield"],
         ["Stock index", "Government bond yield", "Stock-market turnover", "Equity yield"]),
        ("BANKING AND MONETARY CONDITIONS", ["fx_reserves", "gold_cover", "emission_gap", "deposits"],
         ["FX/gold reserves", "Gold cover ratio", "Emission gap", "Savings-bank deposits"]),
        ("REAL-ECONOMY DISTRESS", ["unemployment", "bankruptcies", "settlements"],
         ["Unemployment", "Bankruptcies", "Court settlements"]),
    ]
    nums = mdates.date2num(data.date)
    boundaries = np.r_[nums, mdates.date2num(data.date.iloc[-1] + pd.offsets.MonthBegin(1))]
    for i, (group, columns, labels) in enumerate(blocks):
        ax = fig.add_subplot(grid[i])
        values = data[["z_" + col for col in columns]].to_numpy().T
        im = ax.pcolormesh(boundaries, np.arange(len(columns) + 1), values,
                           cmap=cmap, norm=Normalize(-4, 4), shading="flat", rasterized=False)
        ax.set_yticks(np.arange(len(columns)) + .5, labels=labels, fontsize=10)
        ax.invert_yaxis()
        ax.tick_params(axis="both", length=0, pad=8)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.set_xlim(boundaries[0], boundaries[-1])
        ax.xaxis_date()
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.text(0, 1.12, group, transform=ax.transAxes, fontsize=9.4, weight="bold", color=MUTED)
        ax.axvline(mdates.date2num(BREAK), color=INK, linewidth=.8, linestyle=(0, (2, 2)))
        if i < 2:
            ax.tick_params(labelbottom=False)
    cax = fig.add_axes([.35, .105, .46, .021])
    cb = fig.colorbar(im, cax=cax, orientation="horizontal", ticks=[-4, -2, 0, 2, 4])
    cb.ax.tick_params(length=0, pad=5, labelsize=9)
    cb.outline.set_visible(False)
    fig.text(.263, .114, "Less stress", fontsize=9.4, color=TEAL, ha="right", va="center")
    fig.text(.835, .114, "More stress", fontsize=9.4, color=BURGUNDY, va="center")
    footer(fig, "Full-sample standardisation; no color clipping. Vertical dashed line: February 1934 reserve reform.")
    save(fig, out, "fsi-components", "Eleven stress-oriented indicators",
         "Heatmap of eleven component z-scores grouped into markets, banking and monetary conditions, and real-economy distress. "
         "Teal indicates below-average stress; burgundy indicates above-average stress. All components use the same color scale "
         "from minus four to plus four and no values are clipped. February 1934 is marked by a vertical dashed line.")


def reform(data, summary, out):
    fig = plt.figure(figsize=(10.4, 5.6))
    gs = fig.add_gridspec(1, 2, width_ratios=[3.4, 1.8], left=.085, right=.97,
                          bottom=.27, top=.77, wspace=.29)
    ax = fig.add_subplot(gs[0])
    bars = fig.add_subplot(gs[1])
    header(fig, "February 1934 is also a measurement break",
           "Reserve definitions and the statutory cover ratio change at the same time as the devaluation")
    d = data[data.date.between("1932-01-01", "1935-12-01")]
    style_axis(ax, dates=d.date)
    ax.plot(d.date, d.financial_stress_index, color=BURGUNDY, linewidth=2.1, label="Baseline FSI")
    ax.plot(d.date, d.fsi_break_neutralized, color=TEAL, linewidth=1.9,
            linestyle=(0, (5, 2)), label="FSI with the reserve-series jump removed")
    ax.axvline(BREAK, color=MUTED, linewidth=.9, linestyle=(0, (3, 3)))
    ax.text(BREAK + pd.Timedelta(days=26), 1.26, "Feb 1934", color=MUTED, fontsize=9.4)
    ax.set_ylabel("Index points")
    ax.set_ylim(-.65, 1.4)
    ax.set_title("The adjusted path retains subsequent monthly changes", loc="left", fontsize=9.6, pad=15)
    vals = summary.set_index("quantity").value
    total = vals["Narrow FSI Jan-Feb 1934 change"]
    affected = vals["Affected reserve-variable contribution to narrow change"]
    # Exact accounting contributions, with the total displayed for comparison.
    names = ["Total FSI", "Affected\nreserves", "Other\ncomponents"]
    numbers = [total, affected, total - affected]
    bars.axhline(0, color="#a8aaa6", linewidth=.8)
    bars.bar(np.arange(3), numbers, width=.58, color=[BURGUNDY, TEAL, "#a5aaa6"], zorder=3)
    for x, val in enumerate(numbers):
        bars.text(x, val - .035, f"{val:.3f}", ha="center", va="top", fontsize=10, color=INK)
    bars.set_ylim(-.82, .08)
    bars.set_yticks([-.6, -.4, -.2, 0])
    bars.set_xticks(np.arange(3), labels=names, fontsize=9.1)
    style_axis(bars, zero=False)
    bars.set_title("January → February 1934\nContribution in FSI points", loc="left", fontsize=9.6, pad=15)
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower left", bbox_to_anchor=(.078, .09), fontsize=9.8,
               ncol=1, handlelength=2.8)
    footer(fig, "Affected series: FX/gold reserves, gold cover and emission gap. This is a measurement diagnostic, not a policy counterfactual.")
    save(fig, out, "fsi-1934-break", "The February 1934 measurement break",
         "Baseline FSI and a diagnostic removing only the January-February 1934 jumps in FX/gold reserves, gold cover and "
         "the emission gap, while retaining subsequent movements. The FSI falls by 0.630 points in that month; 0.471 points, "
         "or 74.8 percent, come from the three affected reserve variables. The diagnostic is not a causal policy counterfactual.")


def robustness(robust, out):
    fig, ax = plt.subplots(figsize=(10.4, 5.6))
    fig.subplots_adjust(left=.085, right=.97, bottom=.22, top=.79)
    header(fig, "Alternative weights preserve the broad chronology",
           "Comparison series are each re-standardized to zero mean and one sample standard deviation")
    style_axis(ax, dates=robust.date)
    base = robust.baseline_fsi_z
    specs = [
        ("pca_first_component", "Principal component", TEAL, (0, (5, 2))),
        ("variance_weighted_fsi", "Dispersion-weighted blocks", OCHRE, (0, (2, 2))),
    ]
    for col, label, color, ls in specs:
        r = base.corr(robust[col])
        ax.plot(robust.date, robust[col], color=color, linewidth=1.65, linestyle=ls,
                label=f"{label} · r = {r:.3f}", zorder=3)
    ax.plot(robust.date, base, color=BURGUNDY, linewidth=2.0, label="Baseline FSI", zorder=4)
    ax.set_ylabel("Standardized comparison index")
    ax.set_ylim(-2.35, 2.85)
    ax.yaxis.set_major_locator(MultipleLocator(1))
    handles, labels = ax.get_legend_handles_labels()
    order = [2, 0, 1]
    ax.legend([handles[j] for j in order], [labels[j] for j in order],
              loc="upper left", bbox_to_anchor=(0, -.15), ncol=2, handlelength=2.8,
              columnspacing=2.4, borderaxespad=0)
    footer(fig, "Level correlations with baseline FSI. Dispersion weights: markets 60.47%; banking and monetary conditions 39.53%.")
    save(fig, out, "fsi-robustness", "Alternative aggregation preserves the broad chronology",
         "The baseline, principal-component, and dispersion-weighted FSI measures all peak in March 1932. "
         "Each plotted series is standardized to zero mean and unit sample standard deviation for comparison. "
         "Correlations with baseline FSI are 0.973 for the principal component and 0.990 for the dispersion-weighted index.")


def forecast(oos, out):
    fig, axes = plt.subplots(2, 3, figsize=(10.4, 7.0))
    fig.subplots_adjust(left=.085, right=.97, bottom=.135, top=.80, hspace=.55, wspace=.20)
    header(fig, "Forecast performance varies by outcome and horizon",
           "Out-of-sample RMSE relative to a controls-only model · below 1 means lower forecast error")
    outcomes = ["Exports", "Imports", "Wholesale prices", "Pig iron", "Rail freight"]
    for i, outcome in enumerate(outcomes):
        ax = axes.flat[i]
        d = oos[oos.outcome == outcome]
        baseline = d[d.model == "Baseline"].set_index("h")
        for model, label, color, marker in [
            ("Narrow FSI", "Financial FSI", BURGUNDY, "o"),
            ("Broad MFSI", "Broad MFSI", TEAL, "s"),
        ]:
            m = d[d.model == model].set_index("h").sort_index()
            ratio = m.rmse / baseline.rmse
            ax.plot(m.index, ratio, color=color, marker=marker, markersize=4.3, linewidth=1.7, label=label)
        style_axis(ax, zero=False)
        ax.axhline(1, color=INK, linewidth=.9, linestyle=(0, (3, 3)))
        ax.set_ylim(.69, 1.39)
        ax.set_xlim(2, 13)
        ax.set_yticks([.75, 1, 1.25], labels=["0.75", "1.00", "1.25"])
        ax.set_xticks([3, 6, 9, 12], labels=[f"{h}m\nn={int(baseline.loc[h, 'n'])}" for h in [3, 6, 9, 12]], fontsize=9)
        ax.set_title(outcome, loc="left", fontsize=11.6, pad=12)
        if i % 3:
            ax.tick_params(labelleft=False)
    key = axes.flat[5]
    key.axis("off")
    handles, labels = axes.flat[0].get_legend_handles_labels()
    key.legend(handles, labels, loc="upper left", bbox_to_anchor=(-.025, 1.03), fontsize=11,
               handlelength=2.7, labelspacing=1.0)
    key.text(0, .53, "1.00 = controls-only benchmark", fontsize=10.1, weight="bold", transform=key.transAxes, va="top")
    key.text(0, .35, "n = evaluated forecasts\nm = months ahead", fontsize=10.4, color=MUTED,
             transform=key.transAxes, linespacing=1.7, va="top")
    footer(fig, "Expanding estimation windows; training-only predictor scaling. Benchmark: outcome momentum, trend and calendar-month effects.")
    save(fig, out, "fsi-forecast-comparison", "Out-of-sample forecast errors by outcome and horizon",
         "Forecast RMSE ratios compare models augmented with narrow FSI or broad MFSI against the same controls-only "
         "baseline across five outcomes and four horizons. Ratios below one indicate improvement. The graphs show mainly "
         "higher errors, with improvements for wholesale prices and pig iron at some longer horizons. Each cell reports its "
         "number of evaluated forecasts; the smallest count is nineteen for twelve-month rail-freight forecasts.")


def future_distress(future, out):
    fig, ax = plt.subplots(figsize=(10.4, 5.4))
    fig.subplots_adjust(left=.085, right=.97, bottom=.22, top=.78)
    header(fig, "Association with later real-economy distress",
           "Coefficient for a one-standard-deviation higher current FSI, conditional on controls")
    style_axis(ax)
    ax.errorbar(future.horizon_months, future.beta, yerr=1.96 * future.se,
                fmt="o", markersize=5.5, color=BURGUNDY, ecolor="#9b8081",
                capsize=5, capthick=1.2, elinewidth=1.5, zorder=4)
    ax.plot(future.horizon_months, future.beta, color=BURGUNDY, linewidth=1.5, zorder=3)
    ax.set_xlim(-.15, 25.2)
    ax.set_ylim(-.28, .40)
    ax.set_ylabel("Real-distress index points")
    ax.yaxis.set_major_locator(MultipleLocator(.1))
    ax.yaxis.set_major_formatter(FormatStrFormatter("%.1f"))
    ax.set_xticks(future.horizon_months, labels=[f"{int(h)}\nn={int(n)}" for h, n in zip(future.horizon_months, future.n)], fontsize=9.5)
    ax.set_xlabel("Months ahead", labelpad=10)
    ax.text(.985, .035, "Bars: approximate 95% intervals", transform=ax.transAxes,
            color=MUTED, fontsize=9.3, ha="right")
    footer(fig, "Controls include current real distress, trend and month effects. Newey–West standard errors. These are predictive associations.")
    save(fig, out, "fsi-future-distress", "Current financial stress and later real-economy distress",
         "Coefficients for a one-sample-standard-deviation increase in current narrow FSI in regressions for the future "
         "real-distress block, controlling for current real distress, a linear trend, and calendar-month effects. "
         "Points are estimates at one, three, six, nine, twelve, eighteen and twenty-four months; bars use beta plus or minus "
         "1.96 Newey-West standard errors. The associations are positive through twelve months; the longer-horizon intervals cross zero.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=READER / "data")
    parser.add_argument("--output", type=Path, default=READER / "figures")
    args = parser.parse_args()
    data = read_csv(args.source, "monthly_derived_indices_r.csv")
    if len(data) != 106 or data.date.min() != pd.Timestamp("1929-11-01") or data.date.max() != pd.Timestamp("1938-08-01"):
        raise ValueError("Expected the 106-month complete analysis panel, November 1929–August 1938")
    overview(data, read_csv(args.source, "table_crisis_episodes.csv"), args.output)
    sectors(data, args.output)
    components(data, args.output)
    reform(data, read_csv(args.source, "table_1934_break_summary.csv"), args.output)
    robustness(read_csv(args.source, "monthly_robustness_series.csv"), args.output)
    forecast(read_csv(args.source, "table_predictive_oos_external.csv"), args.output)
    future_distress(read_csv(args.source, "table_real_distress_horizons.csv"), args.output)


if __name__ == "__main__":
    main()
