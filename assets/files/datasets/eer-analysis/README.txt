Czechoslovakia EER: Annual Analysis Extension
Version 1.0.0. Released 2026-11-13.
Author: Adam Dittrich
Dataset page: https://adamdittrich.github.io/czechoslovakia-eer.html

CONTENTS AND SOURCES
annual-analysis.csv and annual-analysis.json contain 247 annual specification rows:
13 nominal/real pairs over 1920–1938. The reader edition supplies 247 NEER values and
208 REER values (REER begins in 1923). All 26 observed series equal 100 in 1929.
The original four EER reader tables are included in the ZIP under source/.
The original Excel reader edition is dated 22 October 2026:
https://adamdittrich.github.io/assets/files/datasets/Czechoslovakia_EER_1920_1938.xlsx
The related replication deposit is https://doi.org/10.3886/E251023V1.
This extension is a separately dated analytical extension, not a new DOI version.
metadata.json records source URLs and SHA-256 hashes. No original observations,
weights or coverage shares are changed. The source precision is retained.
Construction notes, bilateral inputs, currency-unit rules and an independent
source-level reproducer are available in the companion documentation:
https://adamdittrich.github.io/assets/files/datasets/eer-documentation/provenance-notes.txt
https://adamdittrich.github.io/assets/files/datasets/eer-documentation/README.txt

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
version 1.0.0 (2026-11-13). Cite the related replication deposit separately
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
