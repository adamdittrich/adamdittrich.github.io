THE MISSING J — READER DATA AND FIGURES
Adam Dittrich | Reader edition: 23 October 2026
https://adamdittrich.github.io/the-missing-j.html

1. PURPOSE AND VERSION

This companion presents the dataset, selected research findings and seven figures
for readers of The Missing J. It is a snapshot of processed data and reported
outputs, with a separate verification of calendar alignment in the baseline
estimator. It is not the complete raw-source reconstruction or the complete
conference replication archive.

The archival dataset citation is:
Dittrich, Adam. 2026. The Missing J in Interwar Europe: A Monthly Cliometric Dataset
on Effective Exchange Rates and Trade-Balance Adjustment, 1925–1936.
openICPSR, V1. https://doi.org/10.3886/E251239V1

The research manuscript associated with the replication snapshot uses
the same title. The separate conference version is The Missing J: Fast,
Export-Value-Led Trade Adjustment in Interwar Europe, 1928–1936, dated 20 August
2026, prepared for the 14th Biennial Conference of the Czech Economic Society.

The original title describes the broader source period. The conference title
describes the preferred lagged-annual-weight estimation period. These are not
contradictory date ranges. The website reader is a distinct edition and has not
been asserted to be byte-for-byte identical to the DOI deposit. No new DOI version
or journal-publication status is implied.

2. QUICK START

Read data/reader-monthly-panel.csv alongside data/reader-data-dictionary.csv.
The compact file has 4,032 rows and 39 fields. Every selected source cell was
copied as text without numerical rounding, imputation, row filtering or editing.
Missing values are empty fields. Country-month identifiers are albers_country
and period (YYYY-MM). GreatBritain is the source label for Great Britain.

data/interwar_jcurve_effective_panel.csv is the byte-for-byte original processed
panel: 4,032 rows, 161 fields and 28 economies, January 1925–December 1936. Its
alternative designs and cached sample flags are retained as supplied. The compact
dictionary describes its 39 selected fields, not every alternative-design column
in the full file. The compact panel includes all inputs needed for the baseline
verification script bundled here.

To redraw the seven reader figures, install the dependencies in a Python 3.10+
environment, unzip the bundle, and run from its root:

    python -m pip install -r requirements.txt
    python build_missing_j_figures.py

To reproduce the reported baseline at seven selected horizons and compare exact
calendar offsets:

    python check_missing_j_calendar.py

The compact input can also be selected:

    python check_missing_j_calendar.py --panel data/reader-monthly-panel.csv

These scripts do not access the network. The figure script reads stored results
and chart inputs; it does not estimate new models. The calendar script estimates
the baseline from the processed panel and is independent of the original source
estimation module. It does not reproduce the conference-only robustness tests.

The same scripts live in scripts/ in the website Git repository. Their defaults
also support that repository layout. Figure export is deterministic with the same
Python/library/font environment; SVG text remains selectable and every SVG has an
accessible title and description.

3. COVERAGE AND UNITS

The 28-country monthly grid is broader than the preferred regression sample.
The baseline includes 18 European economies: Austria, Belgium, Bulgaria,
Czechoslovakia, Denmark, Finland, France, Germany, Great Britain, Hungary, Italy,
the Netherlands, Norway, Poland, Romania, Spain, Sweden and Switzerland.

The preferred lagged annual European real effective rate begins in January 1928,
using bilateral annual weights first available for 1927. Some countries begin
later or have missing blocks. The full date grid is not a balanced panel of
observed variables. The annual weight archive covers 1927–1938; years beyond the
monthly analysis endpoint are included as source data rather than used to imply
post-1936 local-projection coverage.

Trade values TOTEX and TOTIM are seasonally adjusted nominal values inherited
from the Albers–Uebele panel. Their monetary units are source-specific. They are
not trade volumes, not a common-currency series, and not automatically an index
with a common base. Do not sum those levels across countries without harmonizing
units. The principal outcome is ln_tb_ratio = log(TOTEX) - log(TOTIM).

Wholesale-price and economic-activity indices also retain their source scaling.
The USD quotation is local currency units per dollar. A positive depreciation
measure means that the home currency becomes cheaper in nominal or real terms.

Local-projection results use a +0.10 log-unit real depreciation. Responses are
100 * coefficient * 0.10: log changes multiplied by 100, often described by the
papers as approximate percentages. A 0.10 log-unit shock is an exact 10.52% change.
A reported response of 4.92696 log points is an exact 5.05% ratio change after
exponentiation, not a 4.93-percentage-point increase in the trade balance.
The stored result columns named effect_10pct_percent and ci95_*_10pct_percent
retain their source names and source values; no silent unit conversion is made.

The normalized balance ntb = (TOTEX - TOTIM) / (TOTEX + TOTIM) is a different
outcome. The conference's reported 2.40 at h=12 for this outcome is a change in
percentage points, not a log-point response of exports/imports.

4. WEIGHT CONSTRUCTION AND ELIGIBILITY

Annual partner weights are based on reporting-country exports to and imports
from each observed European partner, divided by total trade with that European
partner set. Monthly year t uses weights from annual year t-1. Monthly bilateral
real depreciation combines changes in home and partner dollar exchange rates
with partner-minus-home wholesale-price changes. The effective change is their
weighted mean over partners observed in adjacent months, with weights rescaled
over the available basket. Chained levels cumulate the available changes.

The baseline flag bilat_lagged_sample requires a baseline home country, the
currency-unit screen, nonmissing log exports/imports, a nonmissing real effective
change, and at least 0.60 of the European FX-and-price basket observed.
There is no additional minimum partner-count rule in that baseline flag.
It is an initial eligibility screen. Further missing lags and future outcomes
reduce usable observations separately for each regression horizon.

1,829 country-months pass the source screen; the stored baseline uses 1,757 at
h=0, 1,739 at h=1, 1,703 at h=3, 1,649 at h=6 and 1,541 at h=12. All these
regressions include 18 country clusters. The flag is not a horizon-specific
estimation flag. The country-coverage table's 'LP obs.' means screen-passing rows.

Two coverage concepts must remain separate:
- Europe/world share: observed European bilateral trade relative to the reporting
  country's world trade in 1928.
- Mean observed basket: the available weight mass within that European basket
  in adjacent monthly FX/price observations.
High monthly basket coverage is not equivalent to worldwide trade coverage.

The explicit lagged-design weights are in
data/effective_rate_partner_weights_used_bilat_lagged.csv. The broader annual
trade-weight file is data/annual_bilateral_trade_weights_europe_1927_1938.csv.

5. REPORTED PANEL RESULTS

The baseline estimates separate local projections of cumulative log X/M changes,
with the lagged outcome, three lags of depreciation and outcome growth, current
and two lagged partner-activity changes, country fixed effects and unrestricted
calendar-month fixed effects. The source uses country-clustered CR1 standard
errors and normal critical values for the 95% intervals.

Reported log-point responses to the common 0.10-log-unit shock are:
    Horizon             0      1      3      6     12     18     24
    Export/import     0.52   2.15   5.77   4.72   4.93  -0.38  -1.25

The central finding concerns the positive 3–12 horizon response. Estimates at
18 and 24 are statistically indistinguishable from zero. The paper's conference
extension reports that h=1 is borderline with small-cluster bootstrap inference.

The export and import regressions use separate outcome-specific lagged controls.
Their coefficients need not subtract exactly to the direct export/import-ratio
coefficient. They show value dynamics, not an identified decomposition into
price and quantity effects. Do not label their estimates as trade-volume effects.

6. CALENDAR-ALIGNMENT VERIFICATION

The original estimator first filters to eligible rows, then applies groupwise
row shifts to form lagged controls and future outcomes. Five 13-month gaps in
that screened sample occur in France, Italy (twice), Norway and Poland. A shift
over retained rows can span more calendar months than the horizon label.

The paper estimates are preserved. check_missing_j_calendar.py first
reproduces those estimates, standard errors and sample counts at seven selected
horizons. It then reports (a) a check aligning only outcome endpoints and (b) a
check aligning both endpoints and lagged controls by exact calendar dates.

The same eligibility screen, variables, fixed effects and clustered covariance
convention are retained. Calendar lookup uses only screen-eligible observations;
no excluded rows are admitted and no values are imputed. The endpoints must occur
at exactly t-1 and t+h; every intervening month need not be observed. This is an
implementation sensitivity check, not a new structural identification strategy.

Fully aligned responses at h=1,3,6,12 are 2.27, 5.81, 4.94 and 5.14 log points.
At h=12 the aligned estimate uses 1,470 observations and its 95% interval is
2.76–7.52. The first-year interpretation is similar; the 95% intervals at h=18 and h=24 still include
zero. At h=12, 59 of the original 1,541 regression rows have at least one outcome
endpoint at a different calendar distance under the retained-row convention.

data/calendar-alignment-audit.csv contains all three conventions and seven
horizons. data/calendar-alignment-audit.json documents the screen gaps and
calendar distances. This is an additional reader verification, distinct from
both research papers and from the conference-only common-sample extensions.

The original processed file also contains cached alternative-specification flags.
In particular, its usd_sample has broader support than the baseline-aligned flag
defined by the current source builder. Retaining that cached file reproduces the
stored output; deleting it and rebuilding can change alternative-sample support.
The compact file omits that ambiguous alternative flag. Compare estimates on
explicit common observations when testing weighting differences.

7. EVENT DATA AND FIGURES

Nine complete European descriptive windows are used: Austria, Great Britain and
Denmark (September 1931); Norway, Sweden and Finland (October 1931); Estonia
(June 1933); Czechoslovakia (February 1934); Belgium (April 1935).

The source chronology is the devaluation column in Bernanke and James (1991),
Table 2.1. Norway and Sweden are shifted from September to October 1931 and
Belgium from March to April 1935 for first-full-month measurement. The event
universe preserves historical dates, empirical dates, source scope and inclusion
rules. It also records truncated late-1936 and unavailable cases. The October
1936 Czechoslovak episode is not the complete February 1934 episode.

The generic event-window CSV includes more cases than the nine complete European
episodes. For those nine, follow diagnostics/table_A1_event_universe.csv and the
exact event labels in the figure reproduction script.

Event levels are indexed to 100 in month -1. The mean-path chart is the arithmetic
mean of the country-specific indices. At month 12, the means are 111.288 for
export values, 100.629 for import values and 112.567 for the export/import ratio.
The ratio mean is calculated independently; it is not the ratio of the other
two means. The nine-country average of log-ratio changes is 10.5775 log points.
These summaries have different formulas and should not be interchanged.

Country panels use identical vertical scales for comparability. The effective-
rate histories use 100 times the log change relative to January 1929 (zero at
that date). They are not base-100 indices. Missing French rate observations
remain visible as gaps instead of being joined across missing periods.

The formal event study has eight episodes, because Estonia is outside the
18-country panel. Its omitted reference month is -1; the chart displays that
reference as an open zero marker, not as an estimated coefficient. The joint
test of leads -6 to -2 gives p=0.011072. The h=12 formal coefficient is about
1.28 log points with a wide interval including zero. It is not the descriptive
nine-event average or the baseline depreciation local projection.

The placebo diagnostic uses 10,000 within-country draws. Eighteen simulated
means reach or exceed the observed nine-event mean, giving a one-sided value
of 0.0018 (0.002 rounded in the papers). This describes rarity under the stated
sampling exercise. Crisis and tranquil dates need not be exchangeable, so it
does not establish exogenous policy timing.

8. CONFERENCE-ONLY CHECKS

conference/reported-checks.csv transcribes 20 selected rows from CSE Tables 4–6,
printed pages 13–15, including page/table locators and units. These results were
reported in the conference paper; the corresponding extension code and machine-
readable output were not included in the replication snapshot used here.

On identical 1928–1936 country-month support, six exchange-rate measures produce
h=12 responses between 4.93 and 5.31 log points. The older maximum-sample fixed-
1928 estimate of 1.60 changes both weights and years by adding 1925–1927. It is
not a clean measurement-only comparison.

Other conference checks add country trends, vary lag lengths, exclude six
September–October 1931 devaluation countries, and use the normalized balance.
The small-cluster check uses 999 null-imposed, re-studentized Rademacher wild-
cluster bootstrap draws. Its two-sided p-values are 0.051, 0.003, 0.001 and 0.001
at h=1,3,6,12. The older bootstrap helper in the original package is
not the conference procedure; this reader does not represent it as such.

The transcript retains printed cluster p-values of 0.000 as source text. These
are rounded values, not exactly zero probabilities. No standard errors have
been inferred from significance markers for the common-sample table.

9. FILE MAP AND PROVENANCE

data/          Compact and original monthly panels; compact dictionary; annual
               weights; country coverage; calendar-alignment verification.
results/       Original chart-input CSVs and the four-country rate extract.
diagnostics/   Event universe, leave-one-country-out and rate-correlation tables.
conference/    Explicitly labelled transcription from the conference paper.
figures/       Seven accessible SVG and seven PNG figures.
citations.bib  Dataset, reader, manuscript and underlying-source citations.
source-map.csv File-level source, transformation and SHA-256 hash.
checksums.json Hashes for all distributed files except this manifest and the ZIP.
*.py           Figure reproduction and baseline verification scripts.
requirements.txt Python dependencies for those two scripts.

The ZIP contains these files at its root. The ZIP excludes itself. The website
also records the ZIP hash in its parent dataset-assets integrity manifest.
Source CSV copies retain their original bytes. The selected four-country chart
extract is a numerical full-precision selection from the original panel; the
compact monthly panel preserves the exact text of its selected cells. Generated
results, manually transcribed conference values and original outputs are marked
separately in source-map.csv. Numerical equality and file identity are different
checks; the provenance manifest makes both visible.

10. UNDERLYING SOURCES AND CITATION

Monthly core: Albers and Uebele (2015), monthly international interwar dataset;
Albers (2018), The Prelude and Global Impact of the Great Depression: Evidence
from a New Macroeconomic Dataset, Explorations in Economic History 70:150–163.

Exchange rates: Board of Governors of the Federal Reserve System (1943), Banking
and Monetary Statistics, 1914–1941, Table 173. FRASER is the access route.

Trade weights: author's reconstruction from League of Nations Economic
Intelligence Service international trade reports, including International Trade
Statistics, Review of World Trade, and related trade and payments volumes.

Event chronology: Bernanke and James (1991), The Gold Standard, Deflation, and
Financial Crisis in the Great Depression: An International Comparison, in
Financial Markets and Financial Crises, pp.33–68, Table 2.1. The event-universe
file identifies supplemental sources.

Local projections: Jordà (2005), Estimation and Inference of Impulse Responses
by Local Projections, American Economic Review 95(1):161–182.

Please cite the dataset and relevant underlying sources, and identify this
reader edition and the files used when reporting results from the website.
Use the separate CSE conference reference for checks transcribed from that paper.
The dataset concerns conditional dynamic trade-value relationships. It does not
identify a randomized devaluation effect, a pure quantity elasticity, an
intra-month valuation dip, or a global welfare effect.
