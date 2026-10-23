FINANCIAL STRESS IN INTERWAR CZECHOSLOVAKIA
Revised reader data and figures — 23 October 2026
Adam Dittrich, Prague University of Economics and Business
https://adamdittrich.github.io/czechoslovakia-financial-stress.html

SOURCE AND EDITION
These files reproduce selected data and results from the consolidated revised research package accompanying "Measuring Financial Stress under the Gold Standard: Evidence from Interwar Czechoslovakia". This is a reader edition, not a separately DOI-registered release or a claim of journal publication.
The original public archive is openICPSR project 247312, Version 1, 7 April 2026: https://doi.org/10.3886/E247312V1.
That DOI identifies the original V1 files, not this revised reader edition. The source package was prepared for a later openICPSR release. Use the exact version-specific citation belonging to any archive you download.

FILES
monthly-indices.csv: 106 monthly rows and six columns: date, financial_stress_index, macro_financial_stress_index, market_block, banking_monetary_block, real_distress_block. Column values retain the source CSV precision; only columns were selected.
data/monthly_raw_data.csv: underlying historical observations; 141 dated rows from January 1927 to September 1938 with variable-specific missing values.
data/monthly_derived_indices_r.csv: full released derived series, including standardized inputs, blocks, indices and diagnostics.
data/monthly_robustness_series.csv and monthly_leave_one_out_series.csv: alternative constructions.
data/data_dictionary.csv: original variable descriptions, raw units, roles, stress signs and availability.
data/table_*.csv: original research result tables used for chronology, institutional-break diagnostics, robustness and predictive comparisons.
build_fsi_figures.py: script for the seven website figures. This draws from the released data and result tables; it is not a replacement for the study's full estimation workflow.
citations.bib: separate records for the original archive, this reader edition and the manuscript.
checksums.json: SHA-256 hashes for the files in this reader bundle.

CONSTRUCTION
The balanced composite sample is November 1929–August 1938. September 1938 is not filled or interpolated.
Higher standardized inputs represent more stress. Means and sample SDs are calculated over the balanced 106-month sample.
Market = mean of stock_index, bond_yield, stock_turnover, equity_yield after stress orientation and standardization.
Banking/monetary = mean of fx_reserves, gold_cover, emission_gap, deposits after stress orientation and standardization.
Real distress = mean of unemployment, bankruptcies, settlements after standardization.
FSI = (Market + Banking/monetary) / 2.
MFSI = (Market + Banking/monetary + Real distress) / 3.
Consequently FSI has 1/8 weight per financial component; MFSI has 1/12 per financial component and 1/9 per real-distress component.
Baseline composites are averages of z scores, not unit-variance z scores themselves. Zero is the sample mean, not zero stress.

IMPORTANT REUSE DETAILS
Deposits are savings-bank deposits, not total banking-system deposits. Stock turnover is a transaction count, not a currency value. The historical average yield on quoted securities retains the variable name equity_yield.
Raw yield and cover ratios are proportions. Other raw units are documented in the data dictionary.
February 1934 changes reserve eligibility and the legal cover rule. The break-neutralized series is a sensitivity diagnostic that removes immediate legal relief as well as the reporting break; it is not a causal no-devaluation counterfactual.
Exports, imports, wholesale prices, pig iron and rail freight are outcomes, not index inputs. The discount rate is a policy diagnostic. stavka_unused is preserved but is not analyzed because its meaning is undocumented.
The baseline uses full-sample normalization. Predictive associations do not establish causation. Expanding-window forecast origins begin in 1935, not before the 1931 escalation.

FIGURE REPRODUCTION
Requirements: Python 3, pandas, numpy, matplotlib.
From the extracted bundle directory run:
    python build_fsi_figures.py --source data --output figures
Run python build_fsi_figures.py --help for additional options. The script also accepts the original replication-package directory structure.
The ZIP does not duplicate the image files: rendered SVG/PNG versions are available beside each figure on the reader page.

PROVENANCE
The data/*.csv files are byte-for-byte copies of the supplied revised research data and result tables, excluding internal audit reports. No research estimates have been refitted for the website. The compact monthly-indices.csv selects six columns from monthly_derived_indices_r.csv. Web figures are redrawn from those released values.
The source manuscript documents the primary National Bank reports, report dates and page locators in its data-provenance appendix.

CITATION
Please cite the manuscript and the dataset edition actually used. Cite this reader edition by its title, author, date and URL. Cite openICPSR V1 only when identifying the original archived deposit. Machine-readable entries are in citations.bib.
