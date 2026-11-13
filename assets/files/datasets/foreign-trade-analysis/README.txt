CZECHOSLOVAK FOREIGN TRADE: MONTHLY SMOOTHING AND TRADE INDICATORS
Adam Dittrich | 13 November 2026 | schema version 1

Purpose and source
------------------
This derived dataset adds transparent smoothers and consistent trade indicators
to the supplied monthly national trade observations, January 1924–December 1938.
The original Excel workbook and foreign-trade-monthly.csv are not modified.
Exports and imports retain the source's million current Kč units. These are
nominal trade values, not physical quantities or constant-price estimates.
Source file hash and coverage are recorded in metadata.json.

Files
-----
monthly-analysis.csv: long-form analytical table (180 months × six methods).
monthly-analysis.json: the same observations plus method labels and source data.
metadata.json: conventions, source checksum, coverage and references.
data-dictionary.csv: variable definitions, units and denominator rules.
Six SVG figures: observed series, moving-average views and an HP comparison.
build_monthly_analysis.py and requirements.txt: reproducible generation.
monthly-analysis.zip: all analytical files plus the exact source-monthly.csv.

Methods
-------
raw: observed exports and imports, with derived indicators calculated from them.
trailing3 / trailing6 / trailing12: arithmetic mean of the current month and the
previous 2 / 5 / 11 calendar months. Complete windows only; the first 2 / 5 / 11
values are blank. The default website view uses trailing12. A trailing average
lags historical turning points; it is assigned to the window's last month.

centered12: the correctly centered 2 × 12-month moving average. It spans t−6
through t+6. Endpoint weights are 1/24; the eleven interior weights are 1/12.
This is the average of two adjacent 12-month averages. Six observations at each
end are unavailable. The method uses future as well as past observations.

hp129600: the two-sided Hodrick–Prescott trend of the flow LEVELS, not logs.
For each complete contiguous segment, solve (I + λ D'D) τ = y, where D calculates
second differences and λ = 129,600 = 1,600 × (12/4)^4. This is the monthly
frequency adjustment of Ravn and Uhlig (2002), starting from quarterly λ=1,600.
The trend minimizes squared deviations from the observed values plus λ times
the sum of squared changes in the trend's first differences. A minimum of 24
common observed months is required; this threshold is a design choice to avoid
presenting HP trends for very short fragments, not a theoretical guarantee.

Data and indicator conventions
-----------------------------
Dates must be unique, sorted first-of-month dates. An absent calendar month is
reinserted as missing. Values are never interpolated or filled with zero.
Smoothed exports and imports use identical complete calendar support. Rolling
windows containing a missing flow remain blank; HP runs stop at every gap.
The supplied release has 180 consecutive months with both flows observed.

All smoothing is calculated on the full available sample before any display
date range is selected. Changing the chart's dates does not refit the HP trend
or reset the moving-average windows.

The export/import ratio is 100 × X/M; 100% means equal exports and imports.
The balance is X−M, total trade is X+M, and the normalized balance is
100 × (X−M)/(X+M). All are calculated AFTER applying the selected smoother to
X and M. A ratio of smoothed flows is not the arithmetic mean of monthly
ratios. The ratio of 12-month means equals the ratio of their 12-month sums.
Ratios require positive denominators. Missing outputs are CSV blanks or JSON
null, never infinity or zero. Smoothed flow values remain average monthly
values, not multi-month totals.

Interpretation
--------------
Smoothing is neither deflation nor a complete seasonal-adjustment procedure.
HP estimates are descriptive trends, not identified causal effects or a unique
measure of the economic cycle. They can be sensitive at sample boundaries and
around abrupt changes. Smoothing does not harmonize changes in territory,
classification, valuation or currency. The supplied series' scope is retained.

Reproduction
------------
With Python 3.11 or later, install the pinned dependencies:
    python -m pip install -r requirements.txt
Then, in the extracted package:
    python build_monthly_analysis.py --source source-monthly.csv --output .
In the website repository, the script's default input is the adjacent original
foreign-trade-monthly.csv and its default output is its own directory:
    python assets/files/datasets/foreign-trade-analysis/build_monthly_analysis.py
The generator uses fixed SVG metadata, stable SVG identifiers, sorted ZIP
members and fixed ZIP timestamps. Its output contains no execution timestamp.

References
----------
Ravn, Morten O., and Harald Uhlig. 2002. On Adjusting the Hodrick–Prescott Filter
for the Frequency of Observations. Review of Economics and Statistics 84(2):
371–376. https://doi.org/10.1162/003465302317411604
Open-access record: https://discovery.ucl.ac.uk/id/eprint/18641/

Statsmodels official HP-filter documentation (parameter and matrix definition):
https://www.statsmodels.org/stable/generated/statsmodels.tsa.filters.hp_filter.hpfilter.html

Hyndman, Rob J., and George Athanasopoulos. Forecasting: Principles and Practice,
3rd edition. Moving averages and classical decomposition:
https://otexts.com/fpp3/decomposition.html

Citation
--------
Dittrich, Adam. 2026. Czechoslovak Foreign Trade: Interwar Dataset. Monthly
smoothing and trade-indicator supplement, 13 November 2026. Personal academic
website. https://adamdittrich.github.io/czechoslovak-foreign-trade.html
