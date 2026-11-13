Czechoslovakia EER: construction inputs and provenance
Documentation release: 13 November 2026 · Adam Dittrich

Start with provenance-notes.txt. The original index observations are preserved.
Download construction-package.zip for this documentation, the bilateral inputs,
the reconstruction script, and an unchanged copy of the reader index table.

Files
-----
bilateral-inputs.csv          Unchanged 266-row processed bilateral input panel.
currency-unit-rules.csv       Unchanged five-rule conversion ledger from the publication archive.
source-ledger.csv             File, method, aggregation and geographic provenance.
cpi-source-ledger.csv         Exact CPI provenance labels and worksheet row locations.
bilateral-data-dictionary.csv Definitions for every bilateral input field.
early-year-links.csv          Recomputed preferred-chain partner contributions, links ending 1921–1925.
reproduce_indices.py          Standard-library numerical reconstruction of all 26 index variants.
validation-report.json        Verification counts and numerical tolerance result.
source-manifest.json          Original paths, release identity and SHA-256 checksums.
release-notes.txt             Scope of this documentation release.
LICENSE.txt                  Rights and reuse terms for new material.

Reproduction
------------
Requires Python 3.10 or later, no external packages.

From the website repository root:
python assets/files/datasets/eer-documentation/reproduce_indices.py --check-reader assets/files/datasets/eer-all-series.csv

From the unpacked construction-package.zip:
python reproduce_indices.py --check-reader source/eer-all-series.csv

The archive includes the unchanged reader CSV under source/.
A copy of this folder alone can also check its bilateral inputs with:
python reproduce_indices.py

To write diagnostics to a separate directory and optionally export reconstructed indices:
python reproduce_indices.py --output-dir reproduced --export-indices

Use --check-reader PATH with a downloaded eer-all-series.csv to verify the reader data.
The reconstruction reads raw quotations, currency factors, prices and trade values from
bilateral-inputs.csv, recalculates weights and links, and verifies the stored transformations.
It does not depend on the manuscript, web access, the original Excel program, or a database.

Conventions
-----------
Trade values in the bilateral panel are thousands of current Czechoslovak crowns.
Exchange rates are crowns per foreign-currency unit. The harmonised rate multiplies
the raw quotation by the recorded factor. Price indices use 1929 = 100.
Weights are proportions. Annual link values dln_e and dln_q are natural log changes;
the diagnostic contribution columns multiply those changes by 100 and a partner weight.
They are log points, not ordinary percentage points. Blank values are unavailable.

The source manuscript calls observations annual averages; the exact within-year
averaging rule is not encoded. See provenance-notes.txt for historical-verification scope.

Related deposit: https://doi.org/10.3886/E251023V1
Website: https://adamdittrich.github.io/czechoslovakia-eer.html
