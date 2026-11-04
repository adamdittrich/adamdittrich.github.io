# Reconstructing the source inputs

**Historical GIS of the Czech lands · public collection v0.6.1**

The public edition distributes district research outputs and source metadata. Original regional feature collections are obtained directly from the providers under their own terms. Read [Sources and reuse](SOURCES_AND_REUSE.md) before redistributing an upstream archive or a new combined database.

## What can be reproduced directly

The public district layers and separately supplied climate tables can be read without downloading any upstream archives. To recover the climate fields separated from the wide district table, join `gis_climate_normals` by `geography` and `district_year_id` (or by `district_year_id` after filtering both tables to one geography). Monthly joins additionally require year and month; annual joins require year. Inspect the actual table keys in the data dictionary.

The [original v0.6 build scripts](../code/original_v06/scripts/) and [requirements](../code/original_v06/requirements.txt) preserve the methods and acquisition URLs. They are an archived implementation, not a promise of a clean-room, one-command rebuild. Several expect `inputs/base_v05_inputs.gpkg`, earlier modules or historical working paths; adapt those paths explicitly. The archived integration script checks the exact v0.5 input hash and must not be presented as accepting an arbitrary public-edition replacement.

The v0.6.1 railway chronology correction is a separate release step. Running the unchanged original `build_rail.py` alone reproduces the older chronology logic, not the corrected public values. Consult the public release's correction note and supplied correction code.

## Provider downloads

These examples fetch original public files into a new local `source-inputs` directory. They do not execute downloaded code or upload anything. Some archives are large. Preserve the provider response, the retrieval date and a SHA-256 checksum; source services can change after this release.

```bash
mkdir -p source-inputs
curl --fail --location --retry 3 --output source-inputs/ZelezniceCR.zip \
  'https://dprace.geoinf.upol.cz/dprace/magisterske/bedrunka23/files/ZelezniceCR.zip'
curl --fail --location --retry 3 --output source-inputs/HydroRIVERS_v10_eu_shp.zip \
  'https://data.hydrosheds.org/file/HydroRIVERS/HydroRIVERS_v10_eu_shp.zip'
curl --fail --location --retry 3 --output source-inputs/hybas_eu_lev01-12_v1c.zip \
  'https://data.hydrosheds.org/file/hydrobasins/standard/hybas_eu_lev01-12_v1c.zip'
curl --fail --location --retry 3 --output source-inputs/zuj1.zip \
  'https://web.natur.cuni.cz/ksgrrsek/lucc/wp-content/uploads/2017/06/zuj1.zip'
curl --fail --location --retry 3 --output source-inputs/CShapes-2.0.geojson \
  'https://icr.ethz.ch/data/cshapes/CShapes-2.0.geojson'
curl --fail --location --retry 3 --output source-inputs/170240-17data.zip \
  'https://csu.gov.cz/docs/107516/0c242a34-ca97-0209-581f-dde18a20a25f/170240-17data.zip?version=1.0'
```

Original rail-archive SHA-256 recorded by the research release: `313c13451d56a65ef06f1aaf3ddcce7b0a799f6b02fce065ad67c283c03e0aca`.

### CRU-TS v4.10: pin the version and slice

Use the [v4.10 release](https://crudata.uea.ac.uk/cru/data/hrg/cru_ts_4.10/), not a mutable “latest” link. The release manifest records ten variables × four decade files (1901–1910 through 1931–1940). The final analysis excludes months after December 1938.

Example of one actual manifest URL:

```bash
curl --fail --location --retry 3 \
  --output source-inputs/cru_ts4.10.1901.1910.pre.dat.nc.gz \
  'https://crudata.uea.ac.uk/cru/data/hrg/cru_ts_4.10/cruts.2604091129.v4.10/pre/cru_ts4.10.1901.1910.pre.dat.nc.gz'
```

For the complete set, use the `gis_source_catalog` entries: each specifies the original URL, file name, bytes and SHA-256. The following Python example reads that catalogue from the public GeoPackage and downloads only CRU v4.10 entries. Set `gpkg` to the actual downloaded filename. It refuses an existing mismatched file and checks every completed download.

```python
from pathlib import Path
import hashlib
import sqlite3
import urllib.request

gpkg = Path('YOUR_DOWNLOADED_PUBLIC_GEOPACKAGE.gpkg')
destination = Path('source-inputs/cru-v4.10')
destination.mkdir(parents=True, exist_ok=True)
with sqlite3.connect(gpkg) as connection:
    records = connection.execute(
        'SELECT url, filename, bytes, sha256 FROM gis_source_catalog'
    ).fetchall()

def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()

for url, filename, expected_bytes, expected_sha in records:
    if not url.startswith(
        'https://crudata.uea.ac.uk/cru/data/hrg/cru_ts_4.10/'
    ):
        continue
    target = destination / Path(filename).name
    if not target.exists():
        partial = target.with_name(target.name + '.part')
        urllib.request.urlretrieve(url, partial)
        if partial.stat().st_size != int(expected_bytes) or sha256(partial) != expected_sha:
            raise RuntimeError(f'Source changed or incomplete download: {filename}')
        partial.rename(target)
    if target.stat().st_size != int(expected_bytes) or sha256(target) != expected_sha:
        raise RuntimeError(f'Existing file does not match the manifest: {filename}')
```

The earlier climate/hydrology processing implementation was `scripts/build_wave2.py --stage all` in the historical v0.4/v0.5 project. It is not among the recovered v0.6 script files supplied here; the published climate tables, district weights and manifests remain available, but this guide does not claim that the full earlier computational environment has been restored. Preserve CRU station-support diagnostics when reprocessing.

### Historical district base

Obtain the [Historical GIS layers](https://www.historickygis.cz/cs/shp-vrstvy) and their metadata, or use the documented [RCzechia `historie()` interface](https://rczechia.jla-data.net/reference/historie.html). Relevant public census services include:

- 1930: <https://services1.arcgis.com/LPm07959azIAvFRD/ArcGIS/rest/services/Okresy_Ceska_1930/FeatureServer/0>
- 1921: <https://services1.arcgis.com/LPm07959azIAvFRD/ArcGIS/rest/services/Okresy_Ceska_1921/FeatureServer/0>
- 1930 field definitions: <https://www.arcgis.com/sharing/rest/content/items/5bd6ad3cebfc4d04a12d9f87c82dfadb/data>
- 1921 field definitions: <https://www.arcgis.com/sharing/rest/content/items/8751f8eaf00347fd8e01d6fd5fc8b315/data>

Downloading a present service does not automatically recover the exact audited earlier census cleaning, crosswalks or incomplete political-1921 geometry. Preserve those documented limitations and source versions rather than silently replacing them.

### Soil and elevation rasters

- SoilGrids: <https://files.isric.org/soilgrids/latest/data/>. The original `build_soil.py` records the native grids, relevant tiles, scaling and nodata handling. `latest` is mutable: use archived manifest hashes to identify the actual release inputs. The project uses clay, sand, silt, coarse fragments, pH and organic carbon at 0–5, 5–15 and 15–30 cm.
- Copernicus GLO-90: <https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM>. Obtain the GLO-90 tiles using the provider's currently supported download route. The inherited project summaries use a modern DSM and a 200 m analysis grid; no replacement raster has been substituted in the public release.

### Public vector services

The original scripts page through returned object IDs and preserve source metadata; a single default REST query can silently return only the first page. Keep the count/completeness checks when adapting acquisition code.

| Component | Original script | Actual source |
|---|---|---|
| Railways | `build_rail.py --base PATH` | <https://dprace.geoinf.upol.cz/dprace/magisterske/bedrunka23/> |
| Basins | `build_basins.py --base PATH` | <https://www.hydrosheds.org/products/hydrobasins> |
| Land use | `build_landuse.py --base PATH --min-coverage 0.95` | <https://web.natur.cuni.cz/ksgrrsek/lucc/> |
| State borders | `build_borders.py --base PATH` | <https://icr.ethz.ch/data/cshapes/CShapes-2.0.geojson> |
| Geology | `build_geology.py --base PATH` | <https://mapy.geology.cz/arcgis/rest/services/Projekty/CGS_Bedrock_Geology/MapServer/2> |
| Minerals B/P/R | `build_minerals.py --base PATH` | <https://mapy.geology.cz/arcgis/rest/services/Suroviny/loziska_zdroje/MapServer/0> |
| Minerals D | same script, separate register | <https://mapy.geology.cz/arcgis/rest/services/Suroviny/Surovinovy_informacni_system/MapServer/13> |
| CZ_RETRO | `build_settlements.py --base PATH --stage gazetteer` | <https://geoportal.npu.cz/arcgis/rest/services/CZ_RETRO/CP_CZ_Retro_LS/MapServer/1> |
| ČSÚ reference | `build_settlements.py --base PATH --stage population` | <https://csu.gov.cz/obyvatelstvo-a-domy-v-obcich-podle-vysledku-scitani-od-roku-1869> |

Here `PATH` is the documented local base GeoPackage containing the expected four district layers and fields. Inspect each script's `--help` and input definitions first; `build_soil.py` and `build_spatial.py` use their own original path conventions. Do not point output directories at an irreplaceable copy of a released dataset.

For a fresh geological reconstruction with an explicit CC BY licence, the [INSPIRE-harmonised alternative](https://geoportal.gov.cz/php/micka/record/basic/5c01180b-90d8-4bc2-8b1b-7ae20a010852) is a distinct source choice. Record that change; do not call it an exact reproduction of the original service extraction. The mineral [B/P/R ZIP](https://od.geology.cz/loziska_zdroje_ner_sur.zip) excludes the separate D register.

## Validation after a rebuild

Check source hashes, record counts, district identifiers, geometry coverage, units and time keys before comparing results. Preserve missing values and documented exceptions. Re-running a current service may produce changed records; matching numerical results does not imply byte-identical GeoPackages because library versions and metadata timestamps can differ. The original `validate_release.py` validates the original integration layout and should be adapted explicitly for the public collection layout.
