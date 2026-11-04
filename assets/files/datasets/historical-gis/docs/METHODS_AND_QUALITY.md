# Methods, temporal coverage and quality — public edition 0.6.1

**4 November 2026.** This document explains what the supplied district measures mean and where the principal limits arise. Detailed field definitions and source conditions remain in the [public dictionary](../data/GIS_PUBLIC_DATA_DICTIONARY.csv) and [Sources and reuse](SOURCES_AND_REUSE.md). The [public-edition guide](README_PUBLIC_EDITION.md) describes files and software use.

## 1. Spatial units and stable joins

The principal layer contains 330 judicial districts using 1930 boundaries. Additional layers contain 328 judicial districts of 1921, 151 political districts of 1930 and 151 political districts of 1921. They cover the Czech lands, with source geometry retained. A district boundary year is distinct from an observation year: a 1935 climate value can be calculated within a 1921 district polygon.

Use the stable `district_year_id`, plus `geography` where a table contains multiple spatial levels. Append the documented time keys for observations. Names are useful for display and lookup; they are not a substitute for stable IDs. Do not join a monthly, annual or snapshot table to polygons before selecting the intended time interval or accepting the resulting one-to-many structure.

Historical reported area and GIS polygon area are different quantities. The population-density preview uses the census's historical reported area. Žacléř, Napajedla and Zlín have differences exceeding both 10% and 5 km²; their territorial matches are flagged. This is not an instruction to replace their census population or to invalidate independent environmental calculations.

## 2. Historical census and electoral observations

Census fields retain their source dates, categories and denominators. Main-master field counts include IDs and diagnostics. The original 1930 master had 373 fields populated in all 330 rows, while 89 fields had at least one missing value. Do not interpret a repeated static census value in an annual table as a newly observed value every year.

Political-district census rows are reconstructed from judicial units. For 1930, 131 political units are whole-unit sums, 19 use area-weighted splits and one uses a near-exact overlay; 20 are marked as estimates. For 1921, 143 units are whole-unit sums and eight involve area-weighted splits. The political-1921 geometry omits approximately 41.538 km² present in the judicial geography. These are not direct official political-district transcriptions.

The 1921 judicial age-remapping flag occurs in 327 of 328 records, with raw source age fields preserved. Age shares and ratios concern the specified population age groups, not observed economic dependency. The occupational previews use economically active people with a known sector as their denominator. Vsetín and Vejprty have unresolved source economic records; curated economic maps withhold the affected values while keeping the underlying source counts and flags.

Electoral party shares use valid votes. Two Brno district records are withheld from the curated 1935 views pending an explicit reconciliation of electoral and judicial territories, giving 326 displayed observations. The judicial census population of Brno-město, 146,140, is distinct from the whole-city figure of 264,925; substituting the latter would silently change the unit. The conservative KSČ change between 1929 and 1935 uses 273 districts because the eligibility checks differ by date and measure. A change in vote share is expressed in **percentage points**. The raw analytical tables retain source values and separate publication flags.

These checks expose specific inconsistencies and preserve their evidence. They do not constitute a new archival verification of every census cell or election return.

## 3. Climate, 1901–1938

The project uses **CRU-TS v4.10**, a historical gridded climate reconstruction. Monthly variables are aggregated by district–grid intersection area. The 330 main districts draw on **60 cells at 0.5° resolution**; 82 districts lie within a single cell. Fine polygon boundaries do not create independent weather observations within the source grid.

The monthly table contains ten climate variables and station-support diagnostics. There are 150,480 district-month rows for the main geography and 437,760 across all four geographies. Annual/seasonal tables contain 12,540 and 36,480 district-years respectively. The project's anomaly reference period is **1901–1928**; it must be kept distinct from other CRU or climatological reference periods.

The 18 climate-normal fields are supplied in separate tables. Their values match the corresponding fields in the original research masters. The main contextual master therefore has 444 fields; joining the normals explicitly by stable district ID recovers 462.

A supported-area fraction of one means complete area-weight support, not one station in the district. Station-support diagnostics do not count stations physically inside each district. Ground frost frequency is derived empirically and is not a register of observed individual frost events. Monthly-mean temperature differences are not daily extreme temperatures. Seasonal precipitation deficits are relative to their stated project baseline; they do not automatically establish agricultural drought or crop losses.

Timing matters in empirical designs. For example, April–September 1935 includes months after the May election and must not be labelled wholly pre-election weather exposure. CRU-derived tables and normals remain a separate **ODbL 1.0 / Database Contents License** component.

## 4. Railway chronology and the 0.6.1 correction

Railway summaries reconstruct annual represented operating networks for 1901–1938 from Ondřej Bedrunka's Palacký University source. They include length, density, chronology, electrification and distances to track; interpretation is conditional on the source network's coverage.

The Horní Lideč–Púchov source record `UPOL2023-58` supplied an opening year of 1928. The [official ŽSR chronology](https://www.zsr.sk/o-nas/historia-zeleznic/1918-1939) gives **2 May 1937**. Edition 0.6.1 uses 1937, retains the original record in the audit evidence, and recomputes network states using the original clipping/union and nearest-track method. It does not simply subtract a length from an unrelated aggregate.

The correction changes 116 numeric cells in 40 district-year rows across the four geographies. It affects the relevant district in each geography and preserves endpoint controls in 1921 and 1938. The correction validation records 288 passed checks. Detailed evidence is in [RAIL_CORRECTION_V061.json](../audit/RAIL_CORRECTION_V061.json).

An opening is included in its calendar year's state; a 1937 state does not claim the route operated on every day of that year. Poříčany–Nymburk retains missing geometry in the inherited source, and nearby track outside the represented Czech network may be absent. This single correction is not a complete audit of upstream railway chronology.

## 5. Environmental and contextual layers

| Component | Reference and interpretation | Main qualification |
|---|---|---|
| Terrain | Modern Copernicus DEM GLO-90 summaries | Modern surface model; not a historical terrain survey |
| Rivers | Modern HydroRIVERS network and district summaries | Modelled discharge refers to 1971–2000, not interwar flow or navigability |
| Drainage basins | Modern HydroBASINS levels 6, 8 and 12 | Topographic subdivisions; no historical water-management reconstruction |
| Soils | SoilGrids 2.0 at 0–5, 5–15 and 15–30 cm, plus 0–30 cm summaries | Modern model; valid-area coverage and depth weighting remain relevant |
| Land use | LUCC snapshots for 1845, 1948, 1990 and 2000, allocated by overlap | No interpolated 1930 observation; changes cannot be assigned wholly to the interwar period |
| Geology | The 2007 geological map at 1:500,000 | Source scale, overlapping categories and coverage limit interpretation |
| Mineral register | Modern record snapshot retrieved 3 November 2026 | Does not establish which deposits or mines operated in the interwar years |
| State borders | CShapes snapshots on 1921-01-01, 1930-01-01, 1938-09-29, 1938-10-01 and 1938-12-31 | Generalised boundaries; choose the exact date |
| Gazetteer | Multitemporal CZ_RETRO locality references | Not a census of active municipalities in 1930 |
| Municipal reference | ČSÚ population and houses, fourteen censuses in 1869–2011 | Uses 2015 municipal boundaries; no unsupported historical district allocation |

The conservative soil-texture preview requires at least 90% coverage and retains 293 of the 330 main districts. The 115 soil coverage flags apply across all four geographies. Forest-share change between 1845 and 1948 is displayed for 328 main districts: Hlučín lacks 1845 coverage and Hranice lacks 1948 coverage. A percentage-point change in forest share is not a percentage growth rate.

District neighbour relations and distances are derived from the retained polygons. Consult the dictionary for rook/queen definitions, the one-metre rook threshold, distance construction and units. Spatial proximity alone establishes neither a transport connection nor a causal mechanism.

## 6. Publication flags and map treatment

The public flag table contains **453 rows**:

| Flag family | Rows | Public treatment |
|---|---:|---|
| 1921 age remapping | 327 | Keep raw fields and expose reconstruction warning |
| Soil texture coverage below 90% | 115 | Conservative previews filter insufficient coverage |
| Railway opening correction | 4 | Corrected analysis values with original-source evidence |
| Territorial area disagreement | 3 | Retain counts and document uncertain territorial equivalence |
| Economic counts awaiting verification | 2 | Withhold affected curated economic measures |
| Brno electoral territory unresolved | 2 | Withhold the relevant curated electoral comparisons |

Flag rows are not a count of globally unusable districts. A district can have more than one note, and a problem in one module need not invalidate another. Conversely, absence of a flag does not establish that every observation was independently verified.

The browser distinguishes missing values from zero and reports usable observation counts for each measure. Its 49 curated measures were compared with the actual public exports and corrected atlas values; all 16,170 district–measure values agreed within the six-decimal display rounding tolerance. Five annual climate series were compared for all 330 districts and 38 years, giving 62,700 matching browser values. These are presentation-consistency checks, not independent validation of the underlying scientific models.

## 7. File integrity and reproducibility

The final public GeoPackage is 376,324,096 bytes, registers 46 tables, and has SHA-256 `7e659df38835713b3835eb22976f7ccbd9c3e212946c599efc6bec0a7e663253`. Integrity and foreign-key checks pass; the closed destination was checked against the healthy source. All 50 gzip CSV exports were read through their end markers, with expected row counts for the previously repaired locality-link and judicial-1921 annual exports.

The original research GeoPackage remains unchanged with SHA-256 `2534ec6b277f68f0479b3b55baa3a1038e45f954a347f3afa134a11d5f7459da`. The public database retains four original district geometries and the CRU grid, while omitting fifteen provider geometry collections. It preserves the computed thematic tables and links needed to identify upstream inputs. Downloading public service geometry does not automatically confer a blanket redistribution licence.

The companion `histCzechia` 0.2.1 source archive pins the final public checksum. Its `R CMD check --no-manual` completed with status OK. The included test run reported 294 passed assertions, no failures, 19 runtime warnings and two skips: the unavailable v0.5 test input and the optional archive-import test input. The supplied public-database Semily example also ran successfully; the older GDAL runtime emitted a GeoPackage 1.4 compatibility notice. These observations should not be reported as a zero-warning test run.

After the final public ZIP was assembled, a separate integration check loaded that ZIP through `hc_use()`, verified the pinned public release checksum, and retrieved the Semily district and its 1930 climate values successfully. This confirms the installation example against the actual downloadable archive.

See [Source reconstruction](SOURCE_RECONSTRUCTION.md) for recovered scripts, upstream inputs and reproducibility limits. The original v0.6 scripts alone do not recreate every preceding climate/hydrology acquisition step or the later railway correction. Updated upstream services may also differ from archived source hashes.

## 8. Use and attribution

There is no single blanket data licence for this collection. Keep CRU climate, CShapes, LUCC, SoilGrids, historical GIS, HydroSHEDS, Copernicus and other provider terms attached to the relevant outputs. The [source register](SOURCES_AND_REUSE.md) records both the service and author statements where their precedence is unresolved, including CZ_RETRO. MIT applies to code where stated.

Cite the compilation and each original source used. In analysis, state the chosen boundary geography, observation dates, source versions, definitions, coverage filters and joins. Avoid treating modern contextual layers as direct historical observations or the repeated census attributes as annual measurements.
