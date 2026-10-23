#!/usr/bin/env python3
"""Redraw The Missing J reader figures from the supplied replication outputs.

Run from the website checkout:
    python scripts/build_missing_j_figures.py

Or read the original journal replication package:
    python scripts/build_missing_j_figures.py --source /path/to/package

The reader's results/ directory contains byte-for-byte copies of the source
tables and event-window CSVs, plus an explicitly selected four-country extract
of the processed effective-rate panel. This script does not re-estimate models,
impute missing observations, or rescale the stored local-projection estimates.
Dependencies: pandas, numpy, matplotlib.
"""

from __future__ import annotations

import argparse
from html import escape
from io import BytesIO, StringIO
import os
from pathlib import Path
import re
import tempfile

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "dittrich-missing-j-matplotlib"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MultipleLocator
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
READER = ROOT / "assets/files/datasets/missing-j"
if not READER.is_dir():
    READER = Path(__file__).resolve().parent

INK = "#162b36"
MUTED = "#53636a"
BURGUNDY = "#7a2e34"
TEAL = "#346a73"
OCHRE = "#a67932"
SLATE = "#65757f"
GRID = "#e5e2dc"
SOFT = "#f5f1e9"
WHITE = "#ffffff"

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
    "axes.labelsize": 10.5,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "figure.facecolor": WHITE,
    "axes.facecolor": WHITE,
    "savefig.facecolor": WHITE,
    "svg.fonttype": "none",
    "svg.hashsalt": "dittrich-missing-j-reader-2026",
    "lines.solid_capstyle": "round",
    "legend.frameon": False,
    "legend.fontsize": 10,
})


def read_csv(source: Path, name: str) -> pd.DataFrame:
    for directory in (source, source / "results", source / "results/tables", source / "data/processed", source / "data"):
        path = directory / name
        if path.is_file():
            return pd.read_csv(path)
    raise FileNotFoundError(f"Cannot find {name} under {source}")


def header(fig, title, subtitle):
    fig.text(.075, .956, title, fontsize=19, fontfamily="DejaVu Serif", va="top")
    fig.text(.075, .904, subtitle, fontsize=10.3, color=MUTED, va="top")


def footer(fig, note):
    fig.text(.075, .033, note, fontsize=9.0, color=MUTED, va="bottom")


def style_axis(ax, zero=True):
    ax.set_axisbelow(True)
    ax.grid(axis="y", color=GRID, linewidth=.7)
    ax.tick_params(axis="both", length=0, pad=7)
    if zero:
        ax.axhline(0, color="#a8aaa6", linewidth=.8, zorder=1)


def response_axis(ax):
    style_axis(ax)
    ax.set_xlim(-.2, 24.3)
    ax.set_xticks([0, 3, 6, 9, 12, 15, 18, 21, 24])
    ax.set_xlabel("Months after depreciation")
    ax.set_ylabel("Log points (100 × log change)")
    ax.axvline(12, color="#c8c6c0", linewidth=.8, linestyle=(0, (3, 3)), zorder=1)


def lp_band(ax, data, color, label=None):
    ax.fill_between(data.h, data.ci95_low_10pct_percent,
                    data.ci95_high_10pct_percent, color=color, alpha=.13, linewidth=0)
    ax.plot(data.h, data.effect_10pct_percent, color=color, linewidth=2.1,
            marker="o", markersize=3.3, label=label, zorder=3)


def save(fig, out: Path, name: str, title: str, description: str):
    out.mkdir(parents=True, exist_ok=True)
    svg = out / f"{name}.svg"
    vector = StringIO()
    fig.savefig(vector, format="svg", metadata={"Date": None, "Creator": "Adam Dittrich dataset reader"})
    raw = vector.getvalue()
    raw = re.sub(r"<svg\b", '<svg role="img" aria-labelledby="figure-title figure-description"', raw, count=1)
    root_end = raw.index(">", raw.index("<svg")) + 1
    raw = raw[:root_end] + (
        f'\n <title id="figure-title">{escape(title)}</title>'
        f'\n <desc id="figure-description">{escape(description)}</desc>\n'
    ) + raw[root_end:]
    svg.write_text(raw, encoding="utf-8")
    raster = BytesIO()
    fig.savefig(raster, format="png", dpi=180, metadata={"Author": "Adam Dittrich"})
    (out / f"{name}.png").write_bytes(raster.getvalue())
    plt.close(fig)
    print(name)


def effective_rates(source, out):
    try:
        data = read_csv(source, "selected_effective_rate_paths.csv")
    except FileNotFoundError:
        data = read_csv(source, "interwar_jcurve_effective_panel.csv")
    data["date"] = pd.to_datetime(data.date)
    fig, ax = plt.subplots(figsize=(10.4, 5.9))
    fig.subplots_adjust(left=.085, right=.965, bottom=.22, top=.79)
    header(fig, "Real depreciation follows different national paths",
           "Selected European real effective rates · lagged annual bilateral trade weights · 1928–1936")
    style_axis(ax)
    examples = [
        ("GreatBritain", "Great Britain", TEAL, "-"),
        ("Czechoslovakia", "Czechoslovakia", BURGUNDY, "-"),
        ("Belgium", "Belgium", OCHRE, (0, (5, 2))),
        ("France", "France", SLATE, (0, (3, 2, 1, 2))),
    ]
    for country, label, color, linestyle in examples:
        frame = data.loc[(data.albers_country == country) & (data.date >= "1928-01-01")].sort_values("date")
        base = frame.loc[frame.date == "1929-01-01", "ln_reer_bilat_lagged"]
        if len(base) != 1:
            raise ValueError(f"Expected one January 1929 reference observation for {country}")
        ax.plot(frame.date, 100 * (frame.ln_reer_bilat_lagged - float(base.iloc[0])),
                label=label, color=color, linewidth=2, linestyle=linestyle, zorder=3)
    for dt, label, align in [
        ("1931-09-01", "Sep. 1931", "center"),
        ("1934-02-01", "Feb. 1934", "center"),
        ("1935-04-01", "Apr. 1935", "center"),
        ("1936-10-01", "Oct. 1936", "right"),
    ]:
        stamp = pd.Timestamp(dt)
        ax.axvline(stamp, color="#b2b5b3", linewidth=.8, linestyle=(0, (3, 3)), zorder=1)
        ax.text(stamp, .98, label, transform=ax.get_xaxis_transform(), ha=align,
                va="top", color=MUTED, fontsize=9.2,
                bbox={"facecolor": WHITE, "edgecolor": "none", "alpha": .9, "pad": 2})
    ax.set_xlim(pd.Timestamp("1928-01-01"), pd.Timestamp("1936-12-01"))
    ax.set_ylim(-18, 25)
    ax.set_ylabel("Log points relative to January 1929")
    ax.yaxis.set_major_locator(MultipleLocator(10))
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.legend(loc="upper left", bbox_to_anchor=(0, -.16), ncol=4, handlelength=2.5,
              borderaxespad=0, columnspacing=1.65)
    footer(fig, "Upward movements indicate real depreciation; gaps mark missing observations. Vertical markers: major devaluation dates.")
    save(fig, out, "missing-j-effective-rates", "Real depreciation follows different national paths",
         "Monthly real effective depreciation paths for Great Britain, Czechoslovakia, Belgium and France, 1928–1936. "
         "Each series is the chained log effective rate minus its January 1929 value, multiplied by 100. "
         "Upward movements indicate depreciation. Annual bilateral total-trade weights enter with a one-year lag. "
         "Vertical markers identify September 1931, February 1934, April 1935 and October 1936. "
         "Missing observations are left as gaps: France has no value for January 1928 or January 1930 through January 1931.")


def baseline(source, out):
    data = read_csv(source, "lp_baseline_lagged_bilateral_trade_balance.csv")
    fig, ax = plt.subplots(figsize=(10.4, 5.9))
    fig.subplots_adjust(left=.085, right=.965, bottom=.18, top=.79)
    header(fig, "The early deterioration is missing",
           "Export/import ratio after an approximately 10% real effective depreciation · 18 European economies")
    response_axis(ax)
    lp_band(ax, data, BURGUNDY)
    ax.set_ylim(-6, 11.5)
    ax.set_yticks([-5, 0, 5, 10])
    for h, xytext, align in [(1, (1.2, 6.4), "left"), (3, (4.1, 10.1), "left"), (12, (14.0, 8.9), "left")]:
        row = data.loc[data.h == h].iloc[0]
        ax.scatter([h], [row.effect_10pct_percent], s=34, color=BURGUNDY, zorder=5)
        ax.annotate(f"Month {h} · {row.effect_10pct_percent:+.1f}",
                    xy=(h, row.effect_10pct_percent), xytext=xytext, ha=align,
                    fontsize=10.3, color=BURGUNDY,
                    arrowprops={"arrowstyle": "-", "color": BURGUNDY, "lw": .85})
    ax.text(.99, .08, "Later confidence intervals\ninclude zero", transform=ax.transAxes,
            ha="right", va="bottom", fontsize=9.5, color=MUTED)
    footer(fig, "Shading: 95% confidence intervals; country-clustered standard errors. Responses are scaled to a 0.10-log-unit shock.")
    save(fig, out, "missing-j-baseline-response", "The early deterioration is missing",
         "Baseline local projections of the cumulative change in log exports divided by imports from month t minus one to t plus h. "
         "The response to a 0.10-log-unit real effective depreciation is 2.15 log points after one month, "
         "5.77 after three months and 4.93 after twelve months. Estimates are positive through month fifteen; "
         "later confidence intervals include zero. Shading shows 95 percent intervals based on country-clustered standard errors. "
         "This is a conditional panel association, not an externally identified causal shock.")


def components(source, out):
    exports = read_csv(source, "lp_baseline_lagged_bilateral_exports.csv")
    imports = read_csv(source, "lp_baseline_lagged_bilateral_imports.csv")
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 5.9), sharey=True)
    fig.subplots_adjust(left=.085, right=.965, bottom=.20, top=.75, wspace=.16)
    header(fig, "The first-year response is led by export values",
           "Separate local projections for nominal exports and imports · the same depreciation scaling")
    for ax, frame, color, label in zip(axes, [exports, imports], [BURGUNDY, TEAL], ["Export values", "Import values"]):
        response_axis(ax)
        ax.set_xticks([0, 6, 12, 18, 24])
        lp_band(ax, frame, color)
        row = frame.loc[frame.h == 12].iloc[0]
        ax.set_ylim(-6, 13)
        ax.set_yticks([-5, 0, 5, 10])
        ax.text(0, 1.08, label, color=color, fontsize=12.3, weight="bold", transform=ax.transAxes)
        ax.scatter([12], [row.effect_10pct_percent], s=35, color=color, zorder=5)
        ax.annotate(f"Month 12 · {row.effect_10pct_percent:+.1f}",
                    xy=(12, row.effect_10pct_percent), xytext=(12.7, 11.9),
                    ha="center", fontsize=10.2, color=color,
                    arrowprops={"arrowstyle": "-", "color": color, "lw": .85})
    axes[1].set_ylabel("")
    footer(fig, "Common vertical scale; shaded 95% confidence intervals. Nominal trade values do not identify trade-volume responses.")
    save(fig, out, "missing-j-export-import-response", "The first-year response is led by export values",
         "Separate local projections of export and import values after a 0.10-log-unit real effective depreciation. "
         "After twelve months, the export-value response is 8.41 log points, with a 95 percent interval of 5.95 to 10.88; "
         "the import-value response is 2.89, with an interval of minus 0.01 to 5.79. Both panels share a vertical scale. "
         "The models use outcome-specific lagged controls, so subtracting these separately estimated responses "
         "does not reproduce the direct export/import-ratio regression. These are nominal values, not volumes.")


def event_mean(source, out):
    data = read_csv(source, "table_A5_european_full_window_event_mean_paths.csv")
    fig, ax = plt.subplots(figsize=(10.4, 5.9))
    fig.subplots_adjust(left=.085, right=.965, bottom=.22, top=.79)
    header(fig, "A stronger trade ratio across nine devaluation episodes",
           "Observed event paths · arithmetic means of country indices · month before devaluation = 100")
    style_axis(ax, zero=False)
    ax.axhline(100, color="#a8aaa6", linewidth=.8)
    series = [("mean_x_index", "Export values", BURGUNDY, "o", "-"),
              ("mean_m_index", "Import values", TEAL, "s", (0, (4, 2))),
              ("mean_xm_index", "Export/import ratio", INK, "^", "-")]
    for col, label, color, marker, ls in series:
        ax.plot(data.rel_month, data[col], color=color, linewidth=2.1, marker=marker,
                markersize=4, linestyle=ls, label=label)
    ax.set_xlim(-.15, 12.3)
    ax.set_ylim(98, 119)
    ax.set_xticks([0, 3, 6, 9, 12])
    ax.set_yticks([100, 105, 110, 115])
    ax.set_xlabel("Months after devaluation")
    ax.set_ylabel("Index, month −1 = 100")
    ax.legend(loc="upper left", bbox_to_anchor=(0, -.18), ncol=3, handlelength=2.5,
              borderaxespad=0, columnspacing=2.0)
    footer(fig, "Each complete episode has equal weight. Descriptive paths include concurrent economic and policy changes.")
    save(fig, out, "missing-j-event-mean", "A stronger trade ratio across nine devaluation episodes",
         "Arithmetic mean of nine complete country-specific event paths, each indexed to 100 in the month before devaluation. "
         "At month twelve the mean export-value index is 111.29, the import-value index 100.63 and the export/import-ratio "
         "index 112.57. An average of separately exponentiated indices is not the exponent of the average log change. "
         "The separately reported twelve-month mean log-ratio change is 10.58 log points. "
         "These descriptive event paths do not isolate a causal effect of devaluation.")


def event_countries(source, out):
    data = read_csv(source, "curated_devaluation_event_windows.csv")
    summary = read_csv(source, "table_A7_european_event_h12_country_summary.csv")
    # Use the source summary's event order, which is chronological and resolves
    # ties consistently with the supplied manuscript.
    labels = summary.event_label.tolist()
    data = data.loc[data.event_label.isin(labels) & data.rel_month.between(0, 12)]
    if len(labels) != 9 or data.groupby("event_label").size().ne(13).any():
        raise ValueError("Expected nine complete event paths with months 0 through 12")
    fig, axes = plt.subplots(3, 3, figsize=(10.4, 9.6), sharex=True, sharey=True)
    fig.subplots_adjust(left=.085, right=.965, bottom=.14, top=.83, hspace=.42, wspace=.14)
    header(fig, "The average conceals different national experiences",
           "Nine complete devaluation windows · nominal trade values and their ratio · identical scales in every panel")
    for ax, label in zip(axes.flat, labels):
        frame = data.loc[data.event_label == label].sort_values("rel_month")
        country, period = label.rsplit(" ", 1)
        country = country.replace("GreatBritain", "Great Britain")
        style_axis(ax, zero=False)
        ax.axhline(100, color="#a8aaa6", linewidth=.8)
        for col, color, ls, lw in [("x_index", BURGUNDY, "-", 1.5),
                                   ("m_index", TEAL, (0, (4, 2)), 1.5),
                                   ("xm_index", INK, "-", 2.0)]:
            ax.plot(frame.rel_month, frame[col], color=color, linewidth=lw, linestyle=ls)
        ax.set_xlim(0, 12)
        ax.set_ylim(40, 205)
        ax.set_xticks([0, 6, 12])
        ax.set_yticks([50, 100, 150, 200])
        ax.tick_params(labelsize=9, pad=5)
        ax.text(0, 1.07, country, transform=ax.transAxes, fontsize=10.2, weight="bold")
        ax.text(1, 1.07, pd.Timestamp(period + "-01").strftime("%b %Y"),
                transform=ax.transAxes, ha="right", fontsize=8.7, color=MUTED)
    for ax in axes[-1, :]:
        ax.set_xlabel("Months after devaluation", fontsize=9.4)
    for ax in axes[:, 0]:
        ax.set_ylabel("Index, month −1 = 100", fontsize=9.4)
    handles = [Line2D([0], [0], color=BURGUNDY, lw=1.8),
               Line2D([0], [0], color=TEAL, lw=1.8, linestyle=(0, (4, 2))),
               Line2D([0], [0], color=INK, lw=2.1)]
    fig.legend(handles, ["Export values", "Import values", "Export/import ratio"],
               ncol=3, loc="lower center", bbox_to_anchor=(.53, .069), handlelength=2.5, columnspacing=2.5)
    footer(fig, "The 1936 episodes lack a full twelve-month window and are excluded. These paths are descriptive, not causal estimates.")
    save(fig, out, "missing-j-country-event-paths", "The average conceals different national experiences",
         "Nine small multiples show exports, imports and their ratio, indexed to 100 in the month before each devaluation. "
         "Every panel uses the same scale, from 40 to 205. The complete events are Austria, Great Britain and Denmark "
         "in September 1931; Norway, Sweden and Finland in October 1931; Estonia in June 1933; Czechoslovakia "
         "in February 1934; and Belgium in April 1935. Trade-ratio changes at month twelve are positive in six "
         "episodes and negative in Austria, Finland and Belgium. Later 1936 episodes lack complete twelve-month windows.")


def formal_event(source, out):
    data = read_csv(source, "table_5_formal_event_study_coefficients.csv").sort_values("rel_month")
    diag = read_csv(source, "table_A4_event_pretrend.csv").iloc[0]
    fig, ax = plt.subplots(figsize=(10.4, 5.9))
    fig.subplots_adjust(left=.085, right=.965, bottom=.18, top=.79)
    header(fig, "Event timing carries pre-existing dynamics",
           "Formal event study · eight devaluation episodes · country and calendar-month fixed effects")
    style_axis(ax)
    ax.axvspan(-6.35, -.5, color=SOFT, linewidth=0, zorder=0)
    ax.axvline(0, color=MUTED, linewidth=.8, linestyle=(0, (3, 3)), zorder=1)
    for mask in (data.rel_month < -1, data.rel_month >= 0):
        group = data.loc[mask]
        ax.fill_between(group.rel_month, group.ci95_low_percent, group.ci95_high_percent,
                        color=TEAL, alpha=.14, linewidth=0)
        ax.plot(group.rel_month, group.effect_percent, color=TEAL, linewidth=1.9,
                marker="o", markersize=4, zorder=3)
    ax.scatter([-1], [0], s=43, facecolor=WHITE, edgecolor=MUTED, linewidth=1.1, zorder=5)
    ax.annotate("Reference month", xy=(-1, 0), xytext=(-2.2, 8.8), ha="center",
                color=MUTED, fontsize=9.4,
                arrowprops={"arrowstyle": "-", "color": MUTED, "lw": .8})
    ax.text(.99, .96, f"Joint pre-event test\np = {diag.pretrend_p_value:.3f}",
            transform=ax.transAxes, ha="right", va="top", fontsize=10.3, color=TEAL,
            bbox={"facecolor": WHITE, "edgecolor": "none", "pad": 3})
    ax.set_xlim(-6.35, 12.3)
    ax.set_ylim(-29, 19)
    ax.set_xticks([-6, -3, -1, 0, 3, 6, 9, 12])
    ax.set_yticks([-20, -10, 0, 10])
    ax.set_xlabel("Months relative to devaluation")
    ax.set_ylabel("Difference in log exports/imports × 100")
    footer(fig, "Shading: 95% confidence intervals. Month −1 is the omitted reference; pre-event leads −6 through −2 are tested jointly.")
    save(fig, out, "missing-j-formal-event-study", "Event timing carries pre-existing dynamics",
         "Formal event-study coefficients for eight European devaluation episodes, with country and calendar-month "
         "fixed effects and country-clustered 95 percent confidence intervals. Estonia is excluded from this event-study "
         "definition. The omitted reference month is minus one and is shown as an unfilled zero marker, not an estimate. "
         "Pre-event coefficients are negative and jointly significant, p equals 0.011. The month-twelve coefficient "
         "is 1.28 log points with an interval from minus 8.83 to 11.38. This evidence limits a causal interpretation "
         "of the descriptive devaluation-event paths.")


def placebo(source, out):
    dist = read_csv(source, "placebo_event_randomization_europe_distribution.csv")
    summary = read_csv(source, "table_A6_european_event_placebo_randomization.csv").iloc[0]
    values = 100 * dist.placebo_mean_xm_h12.dropna()
    actual = float(summary.actual_mean_xm_h12_percent)
    p95 = float(summary.placebo_p95_percent)
    fig, ax = plt.subplots(figsize=(10.4, 5.9))
    fig.subplots_adjust(left=.085, right=.965, bottom=.20, top=.79)
    header(fig, "The observed event mean is unusual in placebo windows",
           "10,000 within-country placebo draws · nine complete episodes · twelve-month change in the trade ratio")
    style_axis(ax, zero=False)
    counts, bins, patches = ax.hist(values, bins=38, color=TEAL, alpha=.72,
                                   edgecolor=WHITE, linewidth=.7, zorder=2)
    ax.axvline(actual, color=BURGUNDY, linewidth=2.1, zorder=4)
    ax.axvline(p95, color=MUTED, linewidth=1.0, linestyle=(0, (4, 3)), zorder=3)
    ymax = max(counts) * 1.17
    ax.set_ylim(0, ymax)
    ax.set_xlim(min(values.min() - 1, -22), max(values.max() + 1, 16))
    ax.text(actual + .48, ymax * .91, f"Observed mean\n{actual:+.1f}",
            color=BURGUNDY, fontsize=10.2, ha="left", va="top")
    ax.text(p95 - .45, ymax * .91, f"Placebo 95th\npercentile {p95:+.1f}",
            color=MUTED, fontsize=9.4, ha="right", va="top")
    ax.text(.02, .96, f"One-sided randomization\np = {summary.randomization_p_one_sided:.4f}",
            transform=ax.transAxes, va="top", color=INK, fontsize=10.2,
            bbox={"facecolor": WHITE, "edgecolor": "none", "alpha": .93, "pad": 3})
    ax.set_xlabel("Mean twelve-month log change in exports/imports × 100")
    ax.set_ylabel("Placebo draws")
    footer(fig, "Placebos preserve countries and exclude windows near recorded events. This diagnostic does not remove event endogeneity.")
    save(fig, out, "missing-j-placebo-distribution", "The observed event mean is unusual in placebo windows",
         "Distribution of 10,000 within-country placebo means for the twelve-month change in log exports divided by imports. "
         "The actual nine-event mean is 10.58 log points, compared with a placebo mean of minus 1.36 and a placebo "
         "95th percentile of 5.23. The one-sided randomization p-value is 0.0018. All draws, including the tails, are shown. "
         "The comparison demonstrates that the observed event mean is unusual relative to the chosen placebo windows; "
         "it does not make devaluation timing exogenous.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=READER,
                        help="Original package root or reader directory containing results/")
    parser.add_argument("--output", type=Path, default=READER / "figures",
                        help="Output directory for seven SVG and PNG pairs")
    args = parser.parse_args()
    for plot in (effective_rates, baseline, components, event_mean, event_countries, formal_event, placebo):
        plot(args.source, args.output)


if __name__ == "__main__":
    main()
