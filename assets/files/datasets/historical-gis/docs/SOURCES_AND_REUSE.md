# Sources, attribution and reuse

**Historical GIS of the Czech lands · public research collection v0.6.1**  
Source conditions checked on **4 November 2026**.

## A collection of independently licensed components

This release combines district-level research outputs from separately licensed sources. Each component retains its attribution and reuse conditions. The original computation code has a separate MIT licence; that licence does not transfer copyright in the source data. The collection has **no single blanket MIT, Creative Commons or non-commercial licence**.

The public edition contains the four historical district layers, a climate grid, computed tables, weights, diagnostics and documentation. Original regional railway, river, basin, land-use, locality, geological and mineral feature collections are obtained from their providers. Their public availability is not presented as a new redistribution grant.

Climate remains an independent **ODbL 1.0 component**, including separate monthly/annual tables and `gis_climate_normals`. The 18 climate-summary fields are separated from the wide district tables. Join them by the supplied district identifiers to recover the full analytical field set. Other components' non-commercial conditions do not apply to the separate climate downloads. Packaging independent tables in a ZIP or GeoPackage does not give them a common licence; a newly distributed merged database must still satisfy its applicable component terms.

Use the table dictionary for units, denominators and missingness, and [sources.json](../sources.json) for the machine-readable source catalogue. The [source reconstruction guide](SOURCE_RECONSTRUCTION.md) links the original inputs and build scripts.

## Source register

| Source | Temporal meaning | Reuse conditions |
|---|---|---|
| Historical GIS / URRlab | Census data and boundaries for 1921/1930 | Provider-specific attribution; full source acknowledgment below |
| CRU-TS v4.10 | Monthly climate reconstruction, 1901–1938 in this project | ODbL 1.0; Database Contents License |
| HydroRIVERS v1.0 | Modern network; modelled mean discharge 1971–2000 | HydroSHEDS licence and required notice |
| HydroBASINS v1c | Modern topographic basins, levels 6/8/12 | HydroSHEDS licence and required notice |
| Copernicus GLO-90 | Modern surface model, not a 1930 terrain survey | WorldDEM-90 licence and required notice |
| SoilGrids 2.0 | Modern soil model, 0–30 cm summaries | CC BY 4.0 |
| LUCC Czechia | 1845, 1948, 1990, 2000; no 1930 interpolation | Academic/study, non-commercial, attribution |
| Bedrunka / UPOL railways | Reconstructed annual network, 1901–1938 | Original-network licence unspecified; computed summaries only |
| CShapes 2.0 | Five dated state-border snapshots | CC BY-NC-SA 4.0 |
| CZ_RETRO | Multitemporal reference localities | NPÚ service: BY-SA; author page: BY-NC-SA; discrepancy retained |
| ČGS geological map | Geological substrate, map published 2007 | Specific source terms; no blanket open licence inferred |
| ČGS B/P/R minerals | Contemporary inventory, retrieved 2026-11-03 | CC BY 4.0 for the identified open B/P/R dataset |
| ČGS D minerals | Contemporary inventory, retrieved 2026-11-03 | Full-register terms unspecified; computed summaries only |
| ČSÚ 170240-17 | Censuses 1869–2011 in municipal boundaries of 2015 | Current ČSÚ policy: CC BY 4.0; separate reference table |
| Inherited elections | Selected interwar fields, uneven coverage | Publication-level provenance and reuse terms incomplete |

### Historical boundaries and census base

Provider: **Urbánní a regionální laboratoř (URRlab), Faculty of Science, Charles University**. [Historical GIS](https://www.historickygis.cz/cs/shp-vrstvy); [the actual judicial-1930 item and its `licenseInfo`](https://www.arcgis.com/sharing/rest/content/items/e198e22fc0ed4607bd551596b4738d7b?f=pjson).

Citation: Jíchová, J., Soukup, M., Nemeškal, J., Ouředníček, M., Pospíšilová, L., Svoboda, P., Špačková, P. et al. (2014). *Geodatabáze historických statistických a prostorových dat Česka ze Sčítání lidu, domů a bytů 1921–2011*. Urbánní a regionální laboratoř, Přírodovědecká fakulta Univerzity Karlovy v Praze, Praha.

**Required acknowledgment of the underlying Charles University source.** The following provider-prescribed text concerns the original Historical GIS output; it is not a claim that the grant funded Adam Dittrich's later integration or this website:

> Tento výstup vznikl v rámci řešení projektu číslo DF12P01OVV033 Zpřístupnění historických prostorových a statistických dat v prostředí GIS řešeného v rámci programu Aplikovaného výzkumu a vývoje národní a kulturní identity (NAKI), jehož poskytovatel je Ministerstvo kultury České republiky.

The provider permits access and specifies acknowledgment when results are published. It does not label the data MIT or CC0. [RCzechia's `historie()` interface](https://rczechia.jla-data.net/reference/historie.html) accesses the same underlying source; its software licence does not replace these data conditions. District layers describe the Czech lands, not all interwar Czechoslovakia.

### CRU-TS v4.10 climate component

Attribution: **Climatic Research Unit, University of East Anglia**. Source: <https://crudata.uea.ac.uk/cru/data/hrg/cru_ts_4.10/>. Citation: Harris, Osborn, Jones & Lister (2020), *Scientific Data* 7, 109, <https://doi.org/10.1038/s41597-020-0453-3>. This is the methodological citation; the v4.10 page did not supply a version-specific DOI.

The district climate database and its climate normals are available under [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/); individual contents are covered by the [Database Contents License](https://opendatacommons.org/licenses/dbcl/1-0/). Preserve attribution, licence notices and applicable share-alike obligations. Climate maps should credit CRU/UEA and link to these data and terms. Area weighting uses the original 0.5° grid and does not create new independent local weather measurements. Station-support diagnostics remain relevant.

### HydroRIVERS and HydroBASINS

Sources: <https://www.hydrosheds.org/products/hydrorivers> and <https://www.hydrosheds.org/products/hydrobasins>. Citation: Lehner & Grill (2013), *Hydrological Processes* 27(15), 2171–2186, <https://doi.org/10.1002/hyp.9740>. Core HydroSHEDS citation: Lehner, Verdin & Jarvis (2008), *Eos* 89(10), 93–94.

The [HydroSHEDS licence, Appendix A](https://data.hydrosheds.org/file/technical-documentation/HydroSHEDS_TechDoc_v1_4.pdf), governs these district derivatives and any incorporated licensed materials. Preserve its attribution and end-user conditions when passing on this component; it is not an unrestricted standalone redistribution of the original network or basin polygons.

Required Exhibit B notice, with the derivative-product name inserted:

> This product Historical GIS of the Czech lands incorporates data from the HydroSHEDS version 1 database which is © World Wildlife Fund, Inc. (2006-2022) and has been used herein under license. WWF has not evaluated the data as altered and incorporated within Historical GIS of the Czech lands, and therefore gives no warranty regarding its accuracy, completeness, currency or suitability for any particular purpose. Portions of the HydroSHEDS v1 database incorporate data which are the intellectual property rights of © USGS (2006-2008), NASA (2000-2005), ESRI (1992-1998), CIAT (2004-2006), UNEP-WCMC (1993), WWF (2004), Commonwealth of Australia (2007), and Her Royal Majesty and the British Crown and are used under license. The HydroSHEDS v1 database and more information are available at https://www.hydrosheds.org.

HydroRIVERS flow attributes describe a modelled 1971–2000 mean. Basin membership is a topographic reference. Neither supplies interwar annual river flows.

### Copernicus GLO-90

Source and DOI: [Copernicus DEM](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM), <https://doi.org/10.5270/ESA-c5d3d65>. Use the **GLO-90 Full, Free & Open** section of the [licence document](https://dataspace.copernicus.eu/sites/default/files/media/files/2025-06/copernicus_contributing_mission_data_access_v2_cop_dem_licenses.pdf), rather than conditions for other products appearing earlier in that PDF.

Required adapted-product notice:

> produced using Copernicus WorldDEM-90 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved

Required liability notice:

> The organisations in charge of the Copernicus programme by law or by delegation do not incur any liability for any use of the Copernicus WorldDEM™-90.

The licence permits distribution and adaptation with these conditions and no implication of provider endorsement. Elevation and slope are derived from a modern surface model, which can include vegetation and buildings.

### SoilGrids 2.0

Provider: **ISRIC – World Soil Information**. [Data and access policy](https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_02.html): [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Citation: Poggio et al. (2021), *SoilGrids 2.0: producing soil information for the globe with quantified spatial uncertainty*, **SOIL** 7, 217–240, <https://doi.org/10.5194/soil-7-217-2021>.

The district outputs are modified, area/depth-aggregated model predictions. Credit the source and identify these transformations; do not describe them as an interwar soil survey.

### LUCC Czechia

Citation: **Databáze LUCC Czechia: Databáze dlouhodobých změn využití ploch Česka (1845–2000). Ivan Bičík a kolektiv, Přírodovědecká fakulta Univerzity Karlovy v Praze.** [Project](https://web.natur.cuni.cz/ksgrrsek/lucc/); [provider terms](https://web.natur.cuni.cz/ksgrrsek/lucc/wp-content/uploads/2017/06/info_zuj.pdf).

Use is restricted to academic/study purposes without commercial use and with citation. This is a provider-specific condition, not an invented Creative Commons licence. District values are area allocations of source-unit totals. The 1845 label refers to stable-cadastre material approximately 1826–1843; no 1930 land-use observations were manufactured by interpolation.

### Historical railways

Citation: **Ondřej Bedrunka (2023), *Interaktivní mapa vývoje železniční sítě v Česku*, diploma thesis, Department of Geoinformatics, Palacký University Olomouc.** [Project and original download](https://dprace.geoinf.upol.cz/dprace/magisterske/bedrunka23/); [thesis](https://dprace.geoinf.upol.cz/dprace/magisterske/bedrunka23/files/DP_Bedrunka.pdf).

A public download is available, but no explicit reusable-data licence was found in the original archive. This edition publishes its own non-reconstructive district analytical summaries and links the original network at its provider. Treating those summaries as publishable research results is the release's editorial judgment; it is not a claim that the author supplied a general redistribution licence. No licence to the original network is granted here. Version 0.6.1 applies the separately documented chronology correction; original v0.6 scripts alone do not reproduce that correction.

### State borders: CShapes 2.0

Source: <https://icr.ethz.ch/data/cshapes/>. Citation: Schvitz et al. (2022), *Mapping the International System, 1886–2017: The CShapes 2.0 Dataset*, *Journal of Conflict Resolution* 66(1), 144–161. [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) applies to the relevant component and adaptations. Record the dated snapshot and changes when using the district distances. The generalised border geometry does not establish the precise day-by-day occupation of territory in 1938.

### CZ_RETRO

Credit **Karel Kuča, with Štěpán Mleziva; SOVAMM**, with service provision by **NPÚ**. Citation: Kuča (2018), *CZ_Retro user manual*, second expanded edition. [Actual source service](https://geoportal.npu.cz/arcgis/rest/services/CZ_RETRO/CP_CZ_Retro_LS/MapServer); [author's page](https://sovamm.wordpress.com/projekty/aktualni-projekty-sovamm/cz_retro/).

The archived service states **CC BY-SA 4.0 SOVAMM**; the author's broader page states **CC BY-NC-SA 4.0**. These are distinct, documented statements, not a single licence chosen by this project. The public edition supplies district research summaries/linkage information and refers readers to the provider for original locality geometries. It does not grant new rights to the underlying gazetteer. Counts cover multitemporal reference records, not necessarily settlements active in 1930.

### Geology and minerals: Czech Geological Survey

Credit **Česká geologická služba / Czech Geological Survey**, identify the source layer, retrieval date and transformations. [Copyright and attribution](https://cgs.gov.cz/en/copyright); [provision of data](https://cgs.gov.cz/en/maps-and-data/provision-of-data).

- **Geology:** the actual [CGS_Bedrock_Geology layer](https://mapy.geology.cz/arcgis/rest/services/Projekty/CGS_Bedrock_Geology/MapServer/2) has no explicit standard licence in its service licence field. A [separate INSPIRE-harmonised 1:500,000 edition](https://geoportal.gov.cz/php/micka/record/basic/5c01180b-90d8-4bc2-8b1b-7ae20a010852) has CC BY 4.0; that does not by itself establish identical terms for every endpoint.
- **B/P/R minerals:** the [specific open-dataset metadata](https://geoportal.gov.cz/php/micka/record/full/65a1c0a2-1d00-4954-8822-10c90a010852) states CC BY 4.0.
- **D minerals:** [full deposit-database metadata](https://geoportal.gov.cz/php/micka/record/basic/769e5c00-5c00-169e-91a9-c88088beb3f3) records unspecified conditions and copyright. The B/P/R licence is not silently extended to D.

The published geological and mineral summaries are newly calculated district research outputs. Their inclusion does not assert a new unrestricted licence to the original source databases. Original provider geometries are linked upstream. Mineral inventory dates are contemporary (retrieved 2026-11-03), not evidence that a mine operated in 1930.

### Czech Statistical Office municipal reference

**ČSÚ (2017), product 170240-17**, [population and houses in municipalities, 1869–2011](https://csu.gov.cz/obyvatelstvo-a-domy-v-obcich-podle-vysledku-scitani-od-roku-1869). The [current provider policy](https://csu.gov.cz/podminky_pro_vyuzivani_a_dalsi_zverejnovani_statistickych_udaju_csu) states CC BY 4.0 and requires modified data to be identified as modified.

This is a separate reference table: the source harmonises census values to **municipal boundaries of 2015**. It has not been assigned to historical districts without a validated historical crosswalk.

### Inherited election fields and project calculations

Selected interwar election fields are inherited from the earlier project. A complete publication-level citation and separate downstream licence are not established in the recovered documentation; no source URL or licence is invented. They are not newly verified transcriptions of printed returns. Treat missing party results as missing, and consult model documentation before interpreting `excess_*` indicators.

Neighbourhoods, distance matrices, weights and integration diagnostics are project calculations based on the cited inputs. Cite the collection and relevant providers. Neither an extra year in a joined panel nor repetition of a static value turns a census, modern soil prediction or current mineral record into an annual historical observation.
