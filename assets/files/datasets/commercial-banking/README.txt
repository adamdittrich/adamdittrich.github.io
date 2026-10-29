CZECHOSLOVAK COMMERCIAL BANKING, 1919–1937
Joint-stock banks in the Czech lands
Version 0.1.0 | Released 29 October 2026
Compiled by Adam Dittrich

OVERVIEW

This research dataset brings together annual commercial-bank accounts, a
named-bank panel, and the source information needed to interpret them. It is
designed for reuse in economic history, banking history and historical
macroeconomics. The accompanying page and workbook provide ways to explore
the observations before working directly with the CSV files.

The principal historical question is broader than the recovery examined in the
accompanying research: how did the scale, financing, asset composition and
recorded earning power of commercial banking change between the establishment
of Czechoslovakia and the late 1930s?

This is the first public release, dated 29 October 2026.
Dataset page: https://adamdittrich.github.io/czechoslovak-commercial-banking.html
Repository: https://github.com/adamdittrich/adamdittrich.github.io/tree/main/assets/files/datasets/commercial-banking
No DOI has been assigned.

START HERE

1. Open index.html in a modern browser to explore the standalone dataset page.
   Its charts and CSV downloads work from embedded data without a server.
2. Open Czechoslovak_Commercial_Banking_1919_1937.xlsx for the Excel edition.
3. Read docs/Banking_Dataset_Guide.pdf for a compact guide to coverage and use.
4. Use data/ for analysis and metadata/variable_dictionary.csv for definitions.
5. Rebuild the CSV release with python code/build_dataset.py from the extracted
   package. Inputs are frozen under inputs/; the data build does not require
   the original workspace, an account, or network access.

The worksheet and website views are conveniences. The CSV observations,
definitions, source locators and frozen inputs are the research release.

POPULATIONS AND COVERAGE

Annual aggregate, 1919–1937: nineteen annual observations of the changing
population of active joint-stock banks in Bohemia, Moravia and Silesia. Sources
are the League of Nations commercial-banking volumes. The series is not a
constant-membership panel and does not cover the whole financial system of
Czechoslovakia. Ordinary savings banks, cooperative credit associations and
the separate eastern joint-stock institutions are outside this published
category. Joint-stock savings or cooperative central institutions can belong.
The geography describes the reporting institutions, not necessarily the location
of every branch, borrower or claim.

Named-bank panel, 1933–1937: fourteen institutions and seventy bank-years from
the 1938 bank handbook. Institutions are fixed over these five years. Inclusion
depends on the institutions covered by the consulted handbook; exits cannot be
recovered from this panel. The source is a modern digital retyping of the
contemporary handbook, rather than facsimiles of original bank annual reports.

National roster, 1929: twenty-two institutions in the national statistical
handbook, with fourteen matched to the later panel. Its coverage measures are
dated comparisons within that national source. They do not measure later
League asset coverage. The eight unmatched institutions are retained and are
not classified as failures merely because they are absent from the panel.

Central-bank context, 1929–1937: nine annual National Bank observations supplied
as a separate contextual table. They are not commercial-bank observations and
must not be added to commercial-bank totals as if they formed a consolidated
banking system.

Price context: annual CPI observations are available for 1923–1938 in the
retained source extract. Earlier years remain blank. Wholesale-price coverage
and the available month count are recorded explicitly. Original index values
and any explicit rebasing are distinguished. These price concepts do not share
all the geographic, timing and balance-sheet characteristics of the banks.

FILE GUIDE

data/annual_aggregate.csv
    A compact annual research table joining the principal balance-sheet and
    income quantities while retaining separate reporting counts.
data/annual_balance_sheet.csv
    Full annual balance-sheet detail and source/category notes.
data/annual_income.csv
    Income, expenditure, write-offs and profit appropriation detail.
data/annual_components.csv
    Additional published components, including cash, lending, earnings and
    funds whose distinctions are important for historical interpretation.
data/annual_ratios.csv
    Shares, income intensities, annual growth and indices with explicit bases.
data/bank_panel.csv
    The fourteen named banks with stable identifiers, recorded accounts,
    page locators and source exceptions; original category labels are in the
    variable dictionary.
data/bank_ratios.csv
    Bank-level ratios and indices derived from the named-bank accounts.
data/central_bank_context.csv
    National Bank accounts, kept separate from the commercial-bank sample.
data/institution_crosswalk_1929.csv
    National roster, matches, omitted institutions and identity decisions.
data/coverage_1929.csv
    The matched institutions' shares of national-source categories in 1929.
data/reserve_events.csv
    Dated reserve and stabilisation transactions documented by the sources.
data/price_context.csv
    Retained CPI and WPI observations, timing and coverage information.
data/observations_long.csv
    Tidy numeric observations with dataset, entity, year, variable, unit,
    population, status, source and flag fields. Use the dataset identifiers
    to select a coherent series; convenience wide tables overlap by design.
data/source_observations.csv
    The selected-source ledger retaining original publication identifiers,
    labels, symbols and page references. It is not a complete archive of
    alternative publication vintages. Do not pool it with observations_long.csv.

metadata/variable_dictionary.csv
    Definitions, units and construction of the public fields.
metadata/source_index.csv
    Publications, editions, locations and source identifiers.
metadata/population_definitions.csv
    Coverage of each distinct observational population.
metadata/raw_to_analytic.csv
    Mapping between the retained inputs and public research fields.
metadata/release_counts.json
    Counts and coverage of the released tables. Counts of wide and long copies
    must not be added to create an inflated count of independent observations.
metadata/validation.json
    Reconciliation and transformation checks generated with the data.

inputs/
    Frozen transcribed inputs and provenance used by the data builder.
code/
    Data transformation, standalone page, workbook and documentation builders.
figures/
    Downloadable chart files, with the population and units stated on each.
docs/
    Human-readable dataset guide, release notes and validation notes.
CITATION.cff
    Machine-readable citation identifying the public dataset version.
SHA256SUMS.txt
    Hashes of the files distributed in the complete package.

MEASUREMENT CONVENTIONS

Core account amounts are nominal millions of Czechoslovak crowns. The national
institution roster retains explicitly named thousand-Kč source columns, while
its coverage summary reports millions. Source units are preserved in the
dictionary and provenance. In the bank panel, the Všeobecná družstevní banka table originally reports thousands and has
been converted to millions. Ratios ending in _pct are percentages: a value of
9.7 means 9.7%, not 0.097. An index with _1930_100 equals 100 in 1930; the bank
panel's _1933_100 indices instead use 1933.

Balance-sheet quantities are year-end stocks. Income quantities refer to annual
flows. Income divided by year-end assets is an income intensity and is not a
net interest margin based on average earning assets.

Loans and discounted bills include banking and correspondent claims. They do
not isolate credit to domestic nonfinancial borrowers. The extended lending
measure adds separately identified mortgage, municipal and related loans.
Securities and industrial participations remain separate where the source
distinguishes them; institution-specific combinations are flagged.

Published capital and reserves combine paid capital with the published reserve
line. They do not include every hidden reserve, pension fund, earmarked fund or
other economic loss-bearing resource. Dated reserve transfers are events with
their own accounting meanings; their amounts are not automatic corrections to
an aggregate capital total.

The named-bank source's general creditors are not an interbank-only category.
Its deposits are not uniformly customer deposits: the Legiobanka line includes
mortgage borrowing. Source cash can include Treasury bills at the savings-bank
central institution. Original labels and institution-specific notes should be
read before constructing new measures.

MISSINGNESS AND COMPARABILITY

Blank numeric cells are missing, unreported, or inapplicable values, not zeros.
The tidy table's status and flag fields identify why particular observations
are unavailable or require care. Published zero, a derived arithmetic zero,
and a source dash treated as zero in the accepted national-roster
transcription are distinguished in the metadata.

Two breaks matter for commonly used ratios. The 1919 creditor category does
not separately identify bank creditors. The comparable deposit series and its
ratios therefore begin in 1920; the original reported 1919 creditor/deposit
total remains available in the source-oriented detail. In 1936 the League
income account covers twenty-two banks while its balance sheet covers
twenty-three. Income-to-assets ratios for that aggregate year remain blank.
Equal bank counts in other years do not prove identical membership.

The Moravská banka asset components for 1933 differ from the printed asset
total by 20 million crowns. The liability total supports the printed total.
The release preserves the source discrepancy and identifies it; no component
is filled by residual to make the balance sheet appear consistent.

The aggregate and the named-bank panel use different populations and reporting
categories. They should not be spliced into one series or treated as matching
totals. Their common direction can be studied, with their definitions retained.

EXAMPLES

Python, from the extracted package directory:

    import pandas as pd
    ratios = pd.read_csv('data/annual_ratios.csv')
    view = ratios[['year', 'capital_assets_pct', 'loans_bills_assets_pct']]
    print(view.to_string(index=False))

    banks = pd.read_csv('data/bank_ratios.csv')
    endpoints = banks.pivot(index='bank_id', columns='year',
                            values='capital_assets_pct')
    change = endpoints[1937] - endpoints[1933]
    print(change.sort_values())

R:

    ratios <- read.csv('data/annual_ratios.csv', na.strings = '')
    plot(ratios$year, ratios$loans_bills_assets_pct, type = 'l',
         xlab = 'Year', ylab = 'Loans and bills / assets (%)')

Stata:

    import delimited "data/bank_ratios.csv", clear encoding(utf8)
    encode bank_id, gen(bank_numeric_id)
    xtset bank_numeric_id year

SOURCE AND TRANSFORMATION AUDIT

Selected publication vintages, source pages and original labels are part of
the release. The aggregate uses the latest definitionally corresponding nonmissing observation from the consulted League editions;
later blank entries do not erase earlier reported detail. The source-oriented
inputs preserve the material needed to inspect those choices.

Rebuilding checks the transformation from frozen observations to the public
tables. It does not independently repeat digitisation from source scans. Full
historical scans and downloaded research papers are not redistributed here.

The main data rebuild uses Python's standard library only. The standalone HTML page
is self-contained at runtime. The supplied Excel workbook is immediately usable in Excel or
LibreOffice; rebuilding its presentation uses the separate authoring environment
described by its generator. The data pipeline does not depend on that renderer.

CITATION AND PUBLICATION

Suggested citation:
Dittrich, Adam (2026). Czechoslovak Commercial Banking, 1919–1937: Joint-stock
banks in the Czech lands. Version 0.1.0. Research dataset, 29 October 2026.
https://adamdittrich.github.io/czechoslovak-commercial-banking.html

Retain the version, citation and underlying source references when reusing the
observations. No additional reuse licence is assigned by this release.
Underlying historical publications, research supplements and software retain
their own terms. No DOI has been registered. See docs/RELEASE_NOTES.txt for
version history and the relationship to the reviewed preview.
