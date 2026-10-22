# Dataset website update — 22 October 2026

Prepared against main commit 25bb1f71f27cd675effe794d0e16d7f59b7c7ef1.
This package has NOT been committed or deployed.

## Apply
Upload this folder's contents into the root of adamdittrich/adamdittrich.github.io and commit to main. Preserve the existing .github folder, _quarto.yml, healthcare page and other files. The existing Publish Quarto website workflow will build the eleven pages. This update adds no paid service or external script dependency.

## Changes
Two dataset detail pages; seven figures; original Excel downloads; CSV exports; DOI and Ljungberg references; linked entries in Data, Research, Publications, homepage and web CV. Accepted journal articles are labelled Forthcoming, with 2027 retained as an expected publication year rather than an inferred bibliographic year. The downloadable CV PDF is not modified.

Existing edited content pages are preserved from the exact latest deployment and written as Quarto raw-HTML blocks. This avoids overwriting the current tracker updates or healthcare links with an older site package. The original publication and section identifiers are retained.

## Data integrity
The two Excel downloads are byte-identical to the uploaded workbooks. All seven charts use stored values from those workbooks, not synthetic or inferred observations. The EER charts use the specified analytical core, 1925–1938; the early extension remains in the files. CSVs preserve numerical values but not formulas/formatting.

The monthly trade sums do NOT always match the annual national totals. The website makes this explicit and supplies a full comparison CSV. No cause for these discrepancies is inferred. In particular, 1932 imports are 8,157.914 million Kč in the annual sheet versus 7,461.300 million Kč in the monthly sum. Readers should not silently substitute one for the other.

## References
The EER DOI 10.3886/E251023V1 and deposit date come from the uploaded workbook's Definitions sheet. The DOI resolver and openICPSR page could not be independently fetched in this session; no claim is made that the newly packaged workbook is the same file as the 30 June 2026 deposit.

Ljungberg's database landing page and institutional working-paper record were checked. His 2024 Cliometrica article (online 2022), Appendix A, confirms eight Czechoslovak partners representing 69% of total trade in 1929. The 2019 working-paper text confirms current-year chain weighting, CPI adjustment and the depreciation-upward convention. A separate benchmark-index overlay is not shown because the underlying Ljungberg workbook was not retrieved. No external data were invented or copied into the author’s Excel workbook.

## Validation
The updated checker expects eleven pages and keeps the healthcare-image checker. The added checksum validator tests original Excel archives, CSV archives and SVGs. A local browser preview is supplied separately; it is not evidence of a new GitHub deployment. Quarto must still run in GitHub Actions.

### Completed local checks
All eleven HTML pages passed the structural/link validator with zero warnings. The original XLSX bytes and all thirty dataset assets matched their SHA-256 checksums; Excel and CSV ZIP archives passed integrity checks. All seven SVG figures were rasterised successfully and their PNG alternatives decoded. Quarto frontmatter was parsed and existing section IDs were preserved. The healthcare page and its assets are unchanged.

A new production Quarto build and live deployment were not performed. Browser navigation was blocked by the environment, and the attempted self-contained browser review timed out. No completed browser layout review is claimed. The preview ZIP contains the exact existing published assets with the updated page content and can be opened locally; full site search normally requires HTTP hosting.
