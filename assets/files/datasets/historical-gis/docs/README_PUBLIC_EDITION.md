# Czech Lands Historical GIS — public research edition 0.6.1

**Adam Dittrich · 4 November 2026**

A documented collection connecting historical district boundaries, census and electoral observations, climate series, and geographical context. The principal unit is the **330 judicial districts of the Czech lands in 1930**. The collection covers Bohemia, Moravia and Czech Silesia. Slovakia and Subcarpathian Ruthenia are outside its district coverage.

[Interactive explorer, atlas and downloads](https://adamdittrich.github.io/czech-lands-historical-gis.html) · [Methods and quality](METHODS_AND_QUALITY.md) · [Sources and reuse](SOURCES_AND_REUSE.md) · [Source reconstruction](SOURCE_RECONSTRUCTION.md)

## Choose a starting point

- **Browse the evidence:** the web explorer offers 49 curated district measures, district search and profiles, five annual climate series, a searchable variable dictionary, and 39 atlas figures containing 42 maps.
- **Work with a spreadsheet or statistical program:** use the CSV district core, the separate climate-normal table, and the thematic CSV/CSV.GZ exports in `data/`. These retain stable IDs and documented missing values.
- **Work in QGIS:** open `outputs/historical_gis_czech_lands_v061.gpkg`, select the desired district layer, then join a thematic table after choosing its observation year or date.
- **Work in R:** install the companion `histCzechia` 0.2.1 source package and connect it to the supplied GeoPackage. It is not on CRAN; package installation does not implicitly download the data.
- **Work in Python:** `code/quickstart.py` uses the standard library to demonstrate the core–climate join and read a district's annual climate from the GeoPackage.

The browser contains selected views. The downloadable collection includes additional geographies, fields, dates, tables and diagnostics that are not all displayed in the browser.

## What the public edition contains

| Historical geography | Districts | Core fields | Separate climate-normal fields | Annual district rows, 1901–1938 |
|---|---:|---:|---:|---:|
| Judicial districts, 1930 | 330 | 444 | 18 | 12,540 |
| Judicial districts, 1921 | 328 | 402 | 18 | 12,464 |
| Political districts, 1930 | 151 | 390 | 18 | 5,738 |
| Political districts, 1921 | 151 | 389 | 18 | 5,738 |

The original research master's **462 fields** for judicial districts in 1930 are recoverable as **444 core fields plus 18 separate climate-normal fields**. This count includes identifiers, flags, alternative definitions and diagnostics. It does not mean that 462 independent historical measurements are observed for every district.

The public GeoPackage contains **46 registered tables**, including five feature tables: the four district layers and the constructed CRU grid. It retains 437,760 monthly climate rows and 36,480 annual climate rows across the four geographies; the main 1930 judicial geography accounts for 150,480 district-months and 12,540 district-years. The public data directory contains 65 CSV exports, of which 50 are gzip-compressed, and the public dictionary documents 2,259 fields across the retained tables.

The main modules are census and demography; selected elections; monthly and annual climate; terrain; river summaries; annual railways; land use; soils; geology; drainage basins; modern mineral-register summaries; dated state borders; locality references; neighbours and district distances. A separate ČSÚ municipality reference has 175,081 population/house records from censuses of 1869–2011, using 2015 municipal boundaries. It is not an additional harmonised historical-district panel.

## Files and identifiers

The public research archive uses these paths:

| Path | Contents |
|---|---|
| `outputs/historical_gis_czech_lands_v061.gpkg` | Integrated public GeoPackage, 376,324,096 bytes uncompressed |
| `data/gis_master_judicial_1930_public_v061.csv` | Main district core, 330 rows and 444 fields |
| `data/climate_normals_judicial_1930.csv` | The same 330 district IDs, 18 climate-normal fields plus geography and ID |
| `data/climate_monthly_judicial_1930.csv.gz` | Ten monthly climate variables and source-support diagnostics |
| `data/climate_annual_judicial_1930.csv.gz` | Annual/seasonal summaries and anomalies |
| `data/GIS_PUBLIC_DATA_DICTIONARY.csv` | Field definitions, units, dates, caveats and public-file mappings |
| `data/publication_quality_flags.csv.gz` | 453 publication notes, warnings, holds and correction records |
| `docs/` | This guide, methods, source conditions and reconstruction notes |
| `code/` | Publication scripts, quick start and recovered earlier build scripts |
| `audit/` | Evidence and checks supporting the railway correction and other publication decisions |
| `release_manifest.json` | Version, geographies, retained-table count and verified database checksum |

The persistent spatial-record key is `district_year_id`; its year identifies the **boundary geography**. Use `geography` together with this key when combining tables from different spatial levels. For time series add `calendar_year`, and for monthly climate add `month`. Historical border tables use exact snapshot identifiers because 1938 has multiple boundary states. Always check a table's dictionary before joining it.

## Quick start in R

After downloading and extracting the public research archive, install the companion source package and its dependencies:

```r
install.packages(c("sf", "DBI", "RSQLite", "digest"))
install.packages("histCzechia_0.2.1.tar.gz", repos = NULL, type = "source")
library(histCzechia)

hc_use("outputs/historical_gis_czech_lands_v061.gpkg")
hc_data_status()

semily <- hc_districts(district = "Semily")
semily[c("NAZEV", "population", "mean_elevation_m", "river_length_km")]
weather <- hc_climate(1930, district = "Semily")
weather[c("calendar_year", "temp_mean_c", "precip_mm")]
hc_quality_flags(district = "Semily")
```

For this release the example returns a 1930 census population of 17,749 for Semily and CRU-derived 1930 means of 6.850685 °C and 1,032.3 mm of precipitation. Elevation and HydroRIVERS indicators describe their separately documented geographical reference sources.

`hc_use()` checks supported release hashes and opens the database read-only. An extracted directory or an archive containing exactly one recognised integrated GeoPackage is also supported. Use a persistent `cache_dir` with ZIP input if extracted files should survive the R session. The package README and help files describe all accessors and compatibility with research releases 0.5 and 0.6.

To explicitly recover all 462 fields:

```r
core <- hc_districts(geometry = FALSE)
normals <- hc_climate_normals()
fields <- grep("^clim_normal", names(normals), value = TRUE)
idx <- match(core$district_year_id, normals$district_year_id)
stopifnot(length(fields) == 18L, !anyNA(idx),
          !anyDuplicated(normals$district_year_id))
combined <- cbind(core, normals[idx, fields, drop = FALSE])
stopifnot(nrow(combined) == 330L, ncol(combined) == 462L)
```

The explicit join keeps the climate component and its ODbL obligations visible. Review [source conditions](SOURCES_AND_REUSE.md) before redistributing a merged result.

## Quick start in Python

From the extracted archive root:

```bash
python code/quickstart.py
```

With GeoPandas installed:

```python
import geopandas as gpd

districts = gpd.read_file(
    "outputs/historical_gis_czech_lands_v061.gpkg",
    layer="judicial_1930",
)
districts.plot(column="population", legend=True)
```

The CSV exports are independently usable. Gzip is ordinary file compression; standard statistical software can either read it directly or decompress it first. Empty numeric cells are missing values, not zero.

## What changed from research release 0.6

Public edition 0.6.1 separates the 18 climate normals from the wide contextual district tables; retains derived thematic data, district boundaries and the grid; supplies publication flags and curated display masks; and corrects the opening year of the represented Horní Lideč–Púchov railway from 1928 to 1937. The correction was recomputed in the network calculations. Its original source record and supporting evidence remain documented.

Fifteen provider geometry collections are omitted from this public edition. These include original regional railway, river, basin, land-use, locality, geological and mineral features and the CShapes source geometry. Their computed summaries and provenance links remain available. Geometry-specific R accessors explain the omission and available alternatives. This archive is not a mirror of every upstream source file.

The earlier research release remains distinct and unchanged. The exact public database SHA-256 is:

```text
7e659df38835713b3835eb22976f7ccbd9c3e212946c599efc6bec0a7e663253
```

## Quality, attribution and citation

Read [Methods and quality](METHODS_AND_QUALITY.md) before estimation or historical interpretation. Particular qualifications concern census/election territorial crosswalks, coarse climate grids, railway-source completeness, modern environmental models, and land-use observation dates. A missing flag is not proof of independent archival verification.

The collection has **component-specific source conditions**. MIT applies to the companion code, not automatically to every data component. CRU-derived climate is a separate ODbL component; other source terms are documented in [Sources and reuse](SOURCES_AND_REUSE.md).

Suggested compilation citation:

> Dittrich, Adam. 2026. *Czech Lands Historical GIS*. Public research edition 0.6.1, 4 November 2026. https://adamdittrich.github.io/czech-lands-historical-gis.html.

Also cite the original sources for the modules used in a publication. No DOI is assigned in this release's metadata.
