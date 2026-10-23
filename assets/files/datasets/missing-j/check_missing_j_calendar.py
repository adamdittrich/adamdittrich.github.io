#!/usr/bin/env python3
"""Audit calendar alignment in the submitted Missing J baseline local projections.

Requirements: Python 3.10+, numpy, pandas, scipy. No network access is used.

From the website repository root:
    python scripts/check_missing_j_calendar.py

The defaults read the original processed panel and baseline result table distributed
with the reader page and write data/calendar-alignment-audit.csv and .json there.
Use --panel PATH to select reader-monthly-panel.csv instead; its 39 columns retain
all inputs needed here. Explicit --reported-results, --output-csv and --output-json
paths make the script usable outside the website tree.

Purpose
-------
This is a separate implementation audit, not a replacement for the paper's results.
The submitted core_helpers.py first filters to bilat_lagged_sample, then creates
lags and leads with groupby.shift. Where the screen has interior missing months,
a retained-row shift can span more calendar months than its label. The audit:
  1. reproduces that submitted convention and checks it against the archived CSV;
  2. replaces outcome endpoints with exact calendar dates while retaining the
     submitted lagged controls (an intermediate diagnostic);
  3. aligns both outcome endpoints and lagged controls to exact calendar dates.

All three versions retain the same eligibility screen, shock, outcome, controls,
country and calendar-month fixed effects, and country-clustered standard errors.
The calendar lookups use screen-eligible observations only: they neither impute
missing months nor admit data excluded by the submitted eligibility screen. A
future endpoint need not have every intervening month observed, but it must occur
at the exact requested calendar date. This is an implementation sensitivity, not
a re-estimation of the CSE paper's additional robustness exercises.

Response units are 100*log changes for a +0.10 log REER depreciation. These are
usually described as approximate percentage responses to a 10% depreciation.
Inference replicates the submitted normal-approximation 95% intervals and CR1
country-cluster covariance correction; it does not implement a wild bootstrap.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

HORIZONS = (0, 1, 3, 6, 12, 18, 24)
DEP = "ln_tb_ratio"
SHOCK = "d_ln_reer_bilat_lagged"
FDEM = "foreign_activity_eac_bilat_lagged"
SAMPLE = "bilat_lagged_sample"
XCOLS = ([SHOCK, "dep_lag1"]
         + [f"L{lag}_{SHOCK}" for lag in range(1, 4)]
         + [f"L{lag}_d_dep" for lag in range(1, 4)]
         + [f"d_{FDEM}", f"L1_d_{FDEM}", f"L2_d_{FDEM}"])


def parse_arguments() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    reader = root / "assets/files/datasets/missing-j"
    if not reader.is_dir():
        # In the downloadable companion ZIP this script sits beside data/ and results/.
        reader = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--panel", type=Path,
                        default=reader / "data/interwar_jcurve_effective_panel.csv")
    parser.add_argument("--reported-results", type=Path,
                        default=reader / "results/lp_baseline_lagged_bilateral_trade_balance.csv")
    parser.add_argument("--output-csv", type=Path,
                        default=reader / "data/calendar-alignment-audit.csv")
    parser.add_argument("--output-json", type=Path,
                        default=reader / "data/calendar-alignment-audit.json")
    return parser.parse_args()


def absorb_fixed_effects(data: pd.DataFrame, columns: list[str]) -> np.ndarray:
    """Iterative two-way demeaning, as in the submitted core_helpers.py."""
    values = data[columns].astype(float).to_numpy(copy=True)
    for _ in range(200):
        previous = values.copy()
        temp = pd.DataFrame(values, index=data.index, columns=columns)
        values -= temp.groupby(data.albers_country).transform("mean").to_numpy()
        temp = pd.DataFrame(values, index=data.index, columns=columns)
        values -= temp.groupby(data.period).transform("mean").to_numpy()
        if np.max(np.abs(values - previous)) < 1e-10:
            return values
    raise RuntimeError("Two-way fixed-effect demeaning did not converge.")


def fit_local_projection(data: pd.DataFrame, outcome: str) -> tuple[dict, pd.DataFrame]:
    """OLS after demeaning, with the submitted country-cluster CR1 correction."""
    used = data.dropna(subset=[outcome] + XCOLS + ["albers_country", "period"]).copy()
    demeaned = absorb_fixed_effects(used, [outcome] + XCOLS)
    y = demeaned[:, 0]
    all_x = demeaned[:, 1:]
    keep = np.std(all_x, axis=0) > 1e-12
    x = all_x[:, keep]
    names = [name for name, take in zip(XCOLS, keep) if take]
    inverse = np.linalg.pinv(x, rcond=1e-15)
    beta = inverse @ y
    residual = y - x @ beta
    bread = inverse @ inverse.T
    scores = pd.DataFrame(x * residual[:, None], index=used.index)
    cluster_scores = scores.groupby(used.albers_country).sum().to_numpy()
    nobs, k = x.shape
    clusters = used.albers_country.nunique()
    correction = clusters / (clusters - 1) * (nobs - 1) / (nobs - k)
    covariance = correction * bread @ (cluster_scores.T @ cluster_scores) @ bread
    j = names.index(SHOCK)
    coefficient = float(beta[j])
    se = float(np.sqrt(covariance[j, j]))
    return {
        "coefficient": coefficient,
        "coefficient_standard_error": se,
        "response_log_points": 10 * coefficient,
        "standard_error_log_points": 10 * se,
        "ci95_low_log_points": 10 * (coefficient - 1.96 * se),
        "ci95_high_log_points": 10 * (coefficient + 1.96 * se),
        "p_value_normal": float(2 * norm.sf(abs(coefficient / se))),
        "nobs": int(nobs),
        "countries": int(clusters),
    }, used


def prepare_screened_rows(panel: pd.DataFrame) -> pd.DataFrame:
    selected = panel.loc[panel[SAMPLE]].copy().sort_values(["albers_country", "date"])
    selected["dep_lag1"] = selected.groupby("albers_country")[DEP].shift(1)
    selected["d_dep"] = selected.groupby("albers_country")[DEP].diff()
    for lag in range(1, 4):
        selected[f"L{lag}_{SHOCK}"] = selected.groupby("albers_country")[SHOCK].shift(lag)
        selected[f"L{lag}_d_dep"] = selected.groupby("albers_country")["d_dep"].shift(lag)
    for lag in (1, 2):
        selected[f"L{lag}_d_{FDEM}"] = selected.groupby("albers_country")[f"d_{FDEM}"].shift(lag)
    return selected


def main() -> None:
    args = parse_arguments()
    panel = pd.read_csv(args.panel, parse_dates=["date"])
    required = {"albers_country", "period", "date", SAMPLE, DEP, SHOCK, FDEM, f"d_{FDEM}"}
    if not required.issubset(panel.columns):
        raise ValueError(f"Missing panel fields: {sorted(required - set(panel.columns))}")
    flags = panel[SAMPLE].map({True: True, False: False, "True": True, "False": False})
    if flags.isna().any():
        raise ValueError("Eligibility flags must be True or False.")
    panel[SAMPLE] = flags.astype(bool)
    panel["period_ordinal"] = panel.date.dt.year * 12 + panel.date.dt.month
    if panel.duplicated(["albers_country", "period_ordinal"]).any():
        raise ValueError("Duplicate country-month observations.")
    if not (panel.period == panel.date.dt.strftime("%Y-%m")).all():
        raise ValueError("Date and period fields disagree.")
    reported = pd.read_csv(args.reported_results).set_index("h")
    screened = prepare_screened_rows(panel)
    lookup = screened.set_index(["albers_country", "period_ordinal"])

    def at_calendar(frame: pd.DataFrame, column: str, offset: int) -> np.ndarray:
        keys = pd.MultiIndex.from_arrays([frame.albers_country,
                                         frame.period_ordinal + offset])
        return lookup[column].reindex(keys).to_numpy()

    calendar = screened.copy()
    calendar["dep_lag1"] = at_calendar(calendar, DEP, -1)
    calendar["d_dep"] = calendar[DEP] - calendar["dep_lag1"]
    for lag in range(1, 4):
        calendar[f"L{lag}_{SHOCK}"] = at_calendar(calendar, SHOCK, -lag)
        calendar[f"L{lag}_d_dep"] = (at_calendar(calendar, DEP, -lag)
                                             - at_calendar(calendar, DEP, -lag - 1))
    for lag in (1, 2):
        calendar[f"L{lag}_d_{FDEM}"] = at_calendar(calendar, f"d_{FDEM}", -lag)

    gaps = []
    for country, group in screened.groupby("albers_country"):
        spacing = group.period_ordinal.diff().to_numpy()
        for i in np.flatnonzero(spacing > 1):
            gaps.append({"country": country,
                         "last_month_before_gap": group.iloc[i - 1].period,
                         "first_month_after_gap": group.iloc[i].period,
                         "omitted_months": int(spacing[i] - 1)})

    records, horizon_details = [], []
    for horizon in HORIZONS:
        screened["outcome"] = (screened.groupby("albers_country")[DEP].shift(-horizon)
                                - screened.groupby("albers_country")[DEP].shift(1))
        screened["from_ordinal"] = screened.groupby("albers_country").period_ordinal.shift(1)
        screened["to_ordinal"] = screened.groupby("albers_country").period_ordinal.shift(-horizon)
        archived, used = fit_local_projection(screened, "outcome")
        expected = reported.loc[horizon]
        for actual_name, expected_name in [
            ("response_log_points", "effect_10pct_percent"),
            ("standard_error_log_points", "se_10pct_percent"),
        ]:
            if not np.isclose(archived[actual_name], expected[expected_name], atol=1e-6, rtol=0):
                raise AssertionError(f"Archived reproduction differs at h={horizon}: {actual_name}")
        if archived["nobs"] != int(expected.nobs):
            raise AssertionError(f"Archived observation count differs at h={horizon}")
        wrong_lead = (used.to_ordinal - used.period_ordinal) != horizon
        wrong_lag = (used.period_ordinal - used.from_ordinal) != 1
        wrong_endpoint = wrong_lead | wrong_lag
        common = {
            "horizon": horizon,
            "paper_reported_response_log_points": float(expected.effect_10pct_percent),
            "paper_reported_nobs": int(expected.nobs),
            "archived_rows_with_noncalendar_lead": int(wrong_lead.sum()),
            "archived_rows_with_noncalendar_lag": int(wrong_lag.sum()),
            "archived_rows_with_either_noncalendar_endpoint": int(wrong_endpoint.sum()),
        }
        calendar_outcome = at_calendar(screened, DEP, horizon) - at_calendar(screened, DEP, -1)
        screened["calendar_outcome"] = calendar_outcome
        endpoint_only, _ = fit_local_projection(screened, "calendar_outcome")
        calendar["outcome"] = at_calendar(calendar, DEP, horizon) - at_calendar(calendar, DEP, -1)
        aligned, _ = fit_local_projection(calendar, "outcome")
        for method, estimates in [
            ("submitted_screened_row_convention", archived),
            ("calendar_outcome_endpoints_only", endpoint_only),
            ("calendar_outcomes_and_lagged_controls", aligned),
        ]:
            records.append({**common, "method": method, **estimates})
        counts = pd.DataFrame({"country": used.albers_country, "wrong_lead": wrong_lead})
        horizon_details.append({
            **common,
            "maximum_future_calendar_span_in_archived_fit": int((used.to_ordinal - used.period_ordinal).max()),
            "noncalendar_lead_rows_by_country": {
                country: int(count) for country, count in counts.groupby("country").wrong_lead.sum().items()
                if count > 0
            },
        })

    table = pd.DataFrame(records)
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.output_csv, index=False, float_format="%.12g", lineterminator="\n")
    metadata = {
        "title": "Calendar-alignment audit of the submitted Missing J baseline",
        "status": "Reader companion implementation audit; paper estimates are unchanged.",
        "panel_file": args.panel.name,
        "panel_sha256": hashlib.sha256(args.panel.read_bytes()).hexdigest(),
        "reported_results_file": args.reported_results.name,
        "reported_results_sha256": hashlib.sha256(args.reported_results.read_bytes()).hexdigest(),
        "audit_csv_sha256": hashlib.sha256(args.output_csv.read_bytes()).hexdigest(),
        "eligible_records": int(len(screened)),
        "eligible_countries": int(screened.albers_country.nunique()),
        "response_units": "100 times log outcome change per +0.10 log real effective depreciation",
        "outcome": "log nominal exports minus log nominal imports",
        "fixed_effects": ["country", "calendar month"],
        "controls": XCOLS,
        "inference": "OLS after two-way demeaning; CR1 country-cluster covariance, normal approximation, 95% intervals using 1.96 standard errors. No wild bootstrap.",
        "comparison": "All methods retain the same screen-eligible observations. Submitted lags/leads shift over retained rows. Calendar methods require exact date matches within that same screened set. The endpoint-only method changes outcome dates and retains submitted controls; the full calendar method also aligns all lagged controls.",
        "missing_data": "No imputation. Missing required outcome endpoints or controls are dropped separately at each horizon. A dated future endpoint can be used even if an intervening month is absent.",
        "limitations": "This checks the baseline time indexing, not historical source reconstruction or the CSE paper's additional robustness exercises. It retains the submitted statistical model and its identifying assumptions.",
        "screen_gaps": gaps,
        "horizon_details": horizon_details,
    }
    args.output_json.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for horizon in HORIZONS:
        rows = table.loc[table.horizon == horizon].set_index("method")
        original = rows.loc["submitted_screened_row_convention"]
        aligned = rows.loc["calendar_outcomes_and_lagged_controls"]
        print(f"h={horizon:2d}: reported/reproduced {original.response_log_points:7.3f}; "
              f"calendar {aligned.response_log_points:7.3f}; "
              f"N {int(original.nobs)} -> {int(aligned.nobs)}")
    print(f"Saved {args.output_csv.name} and {args.output_json.name}.")


if __name__ == "__main__":
    main()
