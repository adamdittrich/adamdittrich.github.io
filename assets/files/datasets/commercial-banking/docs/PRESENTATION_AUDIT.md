# Presentation patch 0.1.1 — 1 November 2026

The audit used website commit `8a1c09afa1ed2c5bdcd23c30c216db6b1fd0fa99`
and the original public release of 29 October 2026.

| Surface | Before this patch | Version 0.1.1 |
| --- | --- | --- |
| Website JavaScript | Tab10 palette from `a5f5e17`; release labels still 0.1.0 | Same palette; labels and exports identify 0.1.1 |
| Offline template and HTML | Original subdued series and bar colours | Same annual/income colours and dash patterns as the web; red negative bars, blue positive bars, orange funding bars |
| Four PNG/PDF charts | Original subdued palette | Same meaning-to-colour mapping; numerical series and chart definitions retained |
| PDF guide | Original chart and 0.1.0 labels | Updated chart and 0.1.1 labels; explanatory text retained |
| Excel | Two subdued charts | Blue assets, orange lending, green published capital; cell formulas and values unchanged except two release labels |
| Downloads | 0.1.0 ZIP; standalone HTML excluded from Quarto publication | New 0.1.1 ZIP, updated loose files, directly downloadable offline HTML; original ZIP retained |

The offline HTML and template in the original ZIP were byte-identical to the
loose files before this patch. The earlier colour commit changed only the
website JavaScript and its cache query string; it did not update these files,
the workbook, static charts or guide.

## Preservation and checks

The original archive is retained under its original filename with SHA256:

`60fa210f7118049cb65b33330be3fe8ad51d19f0008003973a7bc2dafffc214d`

All 14 data CSVs, 18 frozen input files and 8 metadata CSVs are byte-identical
to the original archive. The data builder changes only its version/date
constants. Validation checks, population definitions, missing-value rules,
indices, formulas and observation counts remain unchanged: 19 annual years,
14 banks and 70 bank-years. The workbook builder validated 8,417 source cells
and 1,083 derived cells and tested selector and source edits in a disposable
round-trip copy. A separate comparison checked every saved worksheet cell
and formula against 0.1.0, allowing only the two release labels to differ.

`code/chart_palette.json` records the shared colours. The Python figure builder
and Excel builder read it directly. The verifier checks both self-contained
JavaScript copies against that file, as well as series definitions, workbook
chart colours, embedded CSVs/binaries, ZIP members and SHA256 manifests. The
website build runs this verifier before deployment. Original figure granularity
is preserved: the static recovery figure separates loans and discounted bills,
whereas the interactive figure combines them.

## Reproduction

Use the builders inside the original ZIP to reproduce 0.1.0. To rebuild 0.1.1,
extract its ZIP into a fresh directory, retaining the supplied data and inputs:

```sh
python code/build_dataset.py
python code/build_guide.py
node code/build_workbook.mjs --output Czechoslovak_Commercial_Banking_1919_1937.xlsx --qa-dir ../banking-workbook-qa --render-scope publication
python code/build_preview.py --qa-dir ../banking-preview-qa
python code/package_release.py
python code/verify_presentation.py
```

The data/preview/package/verifier commands use Python's standard library.
Figures/guide require pandas, numpy, matplotlib, Pillow and reportlab; the
workbook requires `@oai/artifact-tool`, as in the original release. In ChatGPT's
bundled runtime use `$CODEX_PRIMARY_RUNTIME_NODE` instead of `node`. Runtime
versions and PDF creation metadata may affect binary reproduction; checksums
authenticate the distributed files, while data/formula equality is checked
independently. ZIP ordering and timestamps are fixed for packaging identical
input files. Packaging refuses to overwrite an existing versioned ZIP.
