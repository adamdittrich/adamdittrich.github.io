#!/usr/bin/env python3
"""Write the release overview from the verified integrated inventory."""
from pathlib import Path
import json
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]

def main():
 m=json.loads((ROOT/'outputs/integrated_v06_manifest.json').read_text())
 f=json.loads((ROOT/'audit/v06_key_findings.json').read_text())
 audits=pd.read_csv(ROOT/'audit/V06_AUDIT_SUMMARY.csv')
 sem=f['semily'];rows=m['table_counts']
 n=f['main_columns'];new=m['layers'][0]['new_columns']
 population_text=format(int(sem['population']),',').replace(',',' ')
 dictionary=pd.read_csv(ROOT/'outputs/GIS_V06_DATA_DICTIONARY.csv')
 focused=dictionary[dictionary.table.eq('judicial_1930')].copy()
 old=pd.read_csv(ROOT/'inputs/v05_variable_dictionary.csv')
 original=set(old.loc[old.table.eq('judicial_1930'),'variable'])
 focused['added_in_v06']=~focused.variable.isin(original)
 assert len(focused)==n and int(focused.added_in_v06.sum())==new
 focused.to_csv(ROOT/'outputs/GIS_V06_DICTIONARY_judicial_1930.csv',index=False,encoding='utf-8-sig')
 auditlines='\n'.join('| '+str(r.file)+' | '+str(r.PASS)+' | '+str(r.WARN)+' | '+str(r.FAIL)+' |' for r in audits.itertuples())
 text=f'''# Historický GIS českých zemí — vydání 0.6

## Hotové propojení existujících databází

Toto vydání obsahuje skutečně stažené a zpracované zdroje. Navazuje na dokončené vydání 0.5 s censusy, terénem, CRU-TS a HydroRIVERS. Hlavní geografie má **330 soudních okresů roku 1930**, hlavní CSV **{n} sloupců**, z toho **{new} přidaných ve vydání 0.6**. Nové sloupce zahrnují měřené či modelované charakteristiky, plošné odhady, časové řezy, pokrytí a diagnostické příznaky; počet sloupců není počet nezávislých pozorování.

České země nejsou celé meziválečné Československo. Alternativně jsou přiloženy soudní okresy 1921 (328), politické okresy 1930 (151) a politické okresy 1921 (151). Všechny moduly jsou připojené ke všem čtyřem vrstvám, dohromady k 960 okresním polygonům. Tyto vrstvy se prostorově překrývají a nejsou 960 nezávislými územími.

## Který soubor otevřít

Distribuce má dva ZIPy, které se rozbalují do stejné složky `GIS_Czech_Lands_v0_6`:

- **GIS_Czech_Lands_v0_6.zip** obsahuje hotový GeoPackage, hlavní CSV, slovníky, dokumentaci, kontroly, skripty a R balíček. K analýze v QGIS nebo R stačí tento soubor.
- **GIS_Czech_Lands_v0_6_sources.zip** přidává vstup v0.5, jednotlivé moduly, regionální zdroje a podklady historie projektu. Pro zopakování níže uvedených výpočtů rozbalte oba ZIPy vedle sebe tak, aby jejich společná složka splynula.

| Soubor | Použití |
|---|---|
| `outputs/historical_gis_czech_lands_v06.gpkg` | Úplný GIS: čtyři okresní vrstvy s připojenými statickými atributy, časové tabulky, zdrojové geometrie, váhy a metadata. Otevřete v QGIS nebo pomocí R/sf. |
| `outputs/gis_master_judicial_1930_v06.csv` | 330 řádků × {n} sloupců bez geometrie. Jeden řádek na soudní okres 1930. |
| `outputs/gis_annual_judicial_1930_1901_1938_v06.csv.gz` | 12 540 řádků okres–rok: skutečné roční klima a železnice, s opakovanými statickými údaji. |
| `outputs/GIS_V06_DATA_DICTIONARY.csv` | Definice, jednotky, období, zdroje a interpretační poznámky jednotlivých polí. |
| `outputs/GIS_V06_DICTIONARY_judicial_1930.csv` | Samostatný slovník všech {n} hlavních polí, s příznakem {new} nových sloupců. |
| `outputs/GIS_V06_TABLE_INVENTORY.csv` | Úplný seznam skutečných tabulek, vrstev a jejich rozměrů. |
| `outputs/GIS_V06_SOURCE_CATALOG.csv` a `GIS_V06_SOURCE_FILES.csv` | Zdrojové manifesty, původní adresy a kontrolní součty nově získaných souborů. Původních 41 záznamů zůstává v `gis_source_catalog`. |
| `outputs/Semily_1930_profile_v06.csv` | Úplný jeden řádek Semil, vybraný přímo z integrované databáze. |
| `outputs/figures/GIS_v06_new_layers_judicial_1930.png` / `.pdf` | Čtyři mapy skutečných připojených ukazatelů. |
| `modules/` | Oddělené tematické výsledky, podrobné váhy a manifesty. |
| `docs/` a `audit/` | Metodiky, zachovaná omezení, výsledky kontrol a protokoly. |

Obdobné hlavní a roční CSV jsou dostupné pro další tři správní vrstvy. `.csv.gz` je obyčejné CSV komprimované gzip; R i pandas je umějí načíst přímo.

## Co přibylo a jaké období to představuje

| Modul / tabulka | Připojené údaje | Časový význam |
|---|---|---|
| Železnice — `gis_rail_annual` | Délka a hustota provozované sítě uvnitř okresu, elektrifikace, první doložené otevření, vzdálenosti k trati, chybějící geometrie a okrajová omezení. | Každý rok 1901–1938; ve statické vrstvě zvlášť 1921, 1930 a 1938. |
| Využití půdy — `gis_landuse` | Osm základních kategorií: orná půda, trvalé kultury, louky, pastviny, lesy, vody, zastavěné a ostatní plochy; navíc součet zemědělské půdy. Podíly, přidělené hektary a pokrytí. | Zdrojové řezy 1845, 1948, 1990 a 2000; rok 1930 nebyl interpolován. |
| Půda — `gis_soil`, `gis_soil_by_depth` | Jíl, písek, prach, hrubé úlomky, pH ve vodě, organický uhlík; průměr, prostorová variabilita a pokrytí. | Moderní SoilGrids 2.0, mřížka 250 m; hloubky 0–5, 5–15, 15–30 a souhrn 0–30 cm. |
| Geologie — `gis_geology`, `gis_geology_composition` | Původní mapové kategorie a horninové popisy, plošné zastoupení, dominantní kategorie, nepokrytá a překryvná plocha. | Geologická mapa ČGS 1 : 500 000, vydání 2007; geologický podklad, nikoli měření 1930. |
| Povodí — `gis_basins` | Průniky s povodími úrovní 6, 8 a 12, převládající povodí, podíly plochy a návaznost sítě. | Moderní topografický model HydroBASINS v1c; nejde o roční srážky či průtoky. |
| Ložiska — `gis_minerals`, `gis_minerals_categories` | Počty unikátních evidovaných ložisek/zdrojů, původní surovinové kategorie, plocha polygonů v okrese a vzdálenosti k nim. | Aktuální evidence ČGS B/D/P/R, stav zdroje při stažení 2026-11-03. Neurčuje činnost dolů v roce 1930. |
| Státní hranice — `gis_borders` | Vzdálenost od centroidu i vnitřního bodu k vnější hranici ČSR; příznak polohy bodu uvnitř tehdejšího státu. | Pět dat: 1921-01-01, 1930-01-01, 1938-09-29, 1938-10-01 a 1938-12-31. |
| Prostorové vztahy — `gis_neighbors`, `gis_district_distances` | Sousednost hranou i bodem, délka společné hranice, standardizované váhy, vzdálenosti mezi referenčními body. | Vždy pevná okresní geometrie 1921 nebo 1930. |
| Místopis — `gis_gazetteer_reference`, `gazetteer_district_links` | Vazby na skutečné referenční lokality CZ_RETRO, názvy, identifikátory a původní atributy bodů. | Časově smíšený historický místopis; nikoli seznam obcí existujících v jediném roce. |
| Obyvatelstvo a domy ČSÚ — `csu_population_houses_reference` | Získaná obecní referenční tabulka, 175 081 původních záznamů pro 14 sčítání. | 1869–2011 na hranicích obcí 2015. Zůstává samostatná, bez nedoloženého přepočtu na okresy 1930. |

Původní censusy, volební údaje, terénní charakteristiky, měsíční a roční CRU-TS 1901–1938 i ukazatele HydroRIVERS zůstávají zachované. Klima se nezjednodušilo na samotné průměry; úplné měsíční tabulky jsou nadále uvnitř GeoPackage.

## Jak tabulky správně spojovat

Identifikátorem okresu je `district_year_id`, například Semily `CZ1930-J-30102`. `geography` rozlišuje správní vrstvu, `boundary_year` rok hranic a `calendar_year` rok tematického údaje. Při spojení ročních tabulek použijte **geography + district_year_id + calendar_year**. Pro měsíční klima přidejte `month`.

Hranice mají klíč **geography + district_year_id + snapshot_id**: samotný rok 1938 nestačí, protože má tři odlišná data. Povodí navíc rozlišují `hybas_level`, půda vlastnost a hloubku. Železniční sítě lze filtrovat podle roku, ale nedokládají přesný den změny provozu ani dobový jízdní řád.

Ve spojeném ročním CSV se statické hodnoty opakují. **Tím se z censusů 1930, lesů 1948, moderní půdy nebo dnešní evidence ložisek nestávají roční pozorování 1901–1938.** Pro vysvětlování událostí před rokem 1930 nepoužívejte pozdější stav automaticky jako předchozí podmínku.

## Příklad: Semily v hranicích roku 1930

- Zachovaná populace z censu 1930: {population_text} osob.
- Provozovaná železnice uvnitř okresu v roce 1930: {sem['rail_operating_length_km_1930']:.5f} km; hustota {sem['rail_operating_density_km_per_100km2_1930']:.5f} km / 100 km².
- Lesy v řezu 1845: plošně přidělený podíl {sem['landuse_forest_1845_area_allocated_share']*100:.4f} %; orná půda {sem['landuse_arable_1845_area_allocated_share']*100:.4f} %.
- Moderní půdní model pro 0–30 cm: jíl {sem['soil_clay_pct_0_30cm']:.3f} %, pH ve vodě {sem['soil_ph_water_0_30cm']:.3f}; minimální pokrytí vlastností {sem['soil_min_coverage_fraction']*100:.2f} % plochy okresu.
- Centroid je v modelu CShapes pro rok 1930 vzdálen {sem['border_dist_centroid_km_1930']:.3f} km od vnější státní hranice ČSR.
- CZ_RETRO má {int(sem['gazetteer_reference_record_count'])} referenčních záznamů lokalit přiřazených do polygonu; nejde o počet obcí 1930.

Úplný řádek se všemi dalšími poli je v uvedeném CSV profilu. Centroid ani vnitřní bod není automaticky poloha okresního města nebo těžiště obyvatelstva.

## Výsledky kontrol

Původní hodnoty ve všech původních tabulkách a binární geometrie byly porovnány přímo s v0.5. Stejné jsou i původní prostorové indexy. Kontrolní součet vstupu je beze změny. Kontroly rozšíření mají **{f['audit_totals']['PASS']} PASS, {f['audit_totals']['WARN']} WARN a {f['audit_totals']['FAIL']} FAIL**; podrobná čísla jsou níže a v `audit/V06_AUDIT_SUMMARY.csv`.

| Protokol | PASS | WARN | FAIL |
|---|---:|---:|---:|
{auditlines}

Kontroly zahrnují úplnost stažení podle skutečných ID zdrojových služeb, integritu databází, klíče a napojení, časové řezy, plošné jmenovatele, chybějící hodnoty, přímý nezávislý výpočet půdního průměru přes průniky pixelů a zachování starých dat. Počet kontrol sám o sobě není odhadem přesnosti zdrojů.

**Nejde o nové ověření všech historických censusových či volebních hodnot proti dobovým tiskům.** Přetrvávají dříve popsaná omezení věkového přiřazení 1921, brněnských zdrojových nesrovnalostí, odhadů politických censusů a neúplné geometrie politických okresů 1921. Starší ekonomické podíly mohou mít různé jmenovatele; jednoznačně pojmenované varianty zůstávají zachované.

## Praktické interpretační limity

1. **Železnice:** původní databáze má jeden záznam bez geometrie, Poříčany–Nymburk. Nic se nedokreslovalo. Místní možné dopady a vzdálenosti omezené českým rozsahem sítě mají vlastní příznaky. Délky vycházejí z geometrického sjednocení aktivních tras, nikoli ze součtu duplicitních historických záznamů. Vzdálenost je k trati, nikoli k nádraží.
2. **LUCC:** podíl se odvozuje z kategoriálních hektarů ZÚJ, jejichž vnitřní rozmístění neznáme. Přesahující jednotky jsou přiděleny plošnou vahou. Označení 1845 vychází ze stabilního katastru zhruba 1826–1843. Zdrojová harmonizace vodních ploch 1948 je zachovaná. Po vyřazení doloženě vadných jednotek–roků jsou hlavní podíly dostupné u 329/330 okresů ve třech starších řezech a 330/330 v roce 2000; pod 95 % platného pokrytí zůstávají NA.
3. **SoilGrids:** u {f['soil_main_districts_low_coverage']} soudních okresů 1930 je pokrytí alespoň jedné vlastnosti pod 90 %. Průměr popisuje platnou půdní plochu. Zastavěná či vodní místa bez predikce nejsou doplněna nulou. Prostorová směrodatná odchylka není nejistota modelu. Souhrn 0–30 cm váží hloubky tloušťkou; pH je popisný aritmetický průměr.
4. **Geologie:** nezaměňujte měřítko 1 : 500 000 za parcelní přesnost. Originální legendové kategorie a jejich smíšené horninové popisy se svévolně nepřeklasifikují. Jednoznačně přiřazená, překryvná a nepokrytá plocha jsou rozlišené, bez nuceného dopočtu neznámých ploch do 100 %.
5. **Hranice:** CShapes je generalizovaný model vnější hranice celého Československa. Datování modelu není přesný harmonogram skutečného záboru v terénu. Přesný podíl odstoupené plochy či obyvatelstva okresu nebyl odvozen.
6. **Místopis a populace:** CZ_RETRO není sčítací seznam aktivních sídel 1930. ČSÚ poskytuje historické hodnoty na obecní struktuře 2015; jejich připojení ke starým okresům vyžaduje zvlášť ověřený územní převod. Současná integrace takový převod nepředstírá.
7. **Přírodní charakteristiky:** současné povodí, geologický podklad a moderní model půdy mohou sloužit jako environmentální charakteristiky s uvedenými limity. Dnešní ložisková evidence ani modelový průtok HydroRIVERS 1971–2000 nedokládají těžbu či průtok v první republice.

## R: histCzechia 0.2.0

K dispozici je zdrojový R balíček se samostatnými tematickými funkcemi. Není publikovaný na CRAN. Data zůstávají v samostatném GeoPackage; balíček je čte a ověřuje jeho SHA-256. Zachovává podporu v0.5. Přiložený README balíčku obsahuje úplnou dokumentaci instalace a API.

Finální balíček prošel `R CMD check --no-manual` se stavem **OK**, 253 testy bez selhání, varování nebo přeskočení. Ověřen byl skutečný v0.6, původní v0.5, načtení ZIPu, čistá instalace i spustitelný příklad Semil. Tyto R kontroly jsou vykázané samostatně od datového auditu výše.

```r
install.packages(c("sf", "DBI", "RSQLite", "digest"))
install.packages("histCzechia_0.2.0.tar.gz", repos = NULL, type = "source")
library(histCzechia)
hc_use("outputs/historical_gis_czech_lands_v06.gpkg")
hc_districts(district = "Semily")
hc_railways(1930, district = "Semily")
hc_landuse(c(1845, 1948), district = "Semily")
hc_soil(district = "Semily")
hc_minerals(district = "Semily")
hc_geology(district = "Semily", detail = "composition")
hc_basins(district = "Semily", basin_level = c(6, 8, 12))
hc_borders(district = "Semily", dates = "1938-10-01")
hc_dictionary()
```

V QGIS stačí načíst GeoPackage a vybrat `judicial_1930`. Pro časovou tabulku nejprve vyberte rok či konkrétní datum a poté připojte přes identifikátor. Celá dlouhá tabulka se nemá spojovat s jedním okresním řádkem bez vymezení období.

## Reprodukce a obsah zdrojového archivu

`inputs/base_v05_inputs.gpkg` je nezměněný vstup v0.5. Má původní SHA-256 `{m['base_sha256']}`. Nové výstupy se zapisují zvlášť. Archivované regionální půdní pixely zachovávají původní mřížku, jednotky i nodata; kompletní evropský ZIP HydroBASINS není zdvojen, místo něj jsou uchovány původní regionální polygony a evropská topologie vybraných úrovní, adresa a kontrolní součet.

Rychlé znovuspojení hotových modulů:

```bash
python -m pip install -r requirements.txt
python scripts/integrate_v06.py
python scripts/validate_release.py
python scripts/plot_release.py
python scripts/write_release_docs.py
```

Nové vytvoření jednotlivých modulů používá `scripts/build_rail.py`, `build_soil.py`, `build_basins.py`, `build_geology.py`, `build_minerals.py`, `build_borders.py`, `build_settlements.py --stage all`, `build_landuse.py --min-coverage 0.95` a `build_spatial.py`. Dostupné přepínače ukáže `--help`; podrobnosti jsou v tematických metodikách. Některé zdroje se při kompletní obnově znovu stahují. Reprodukce analýzy z archivovaných dat nemusí být binárně totožná s vydáním: záznamy času a různé verze GIS knihoven mohou změnit kontrolní součet nového exportu. Přiložený R katalog ověřuje přesně toto distribuované vydání; původní soubor si ponechte.

Původní metodiky, výpočetní skripty, historické vstupy a dostupné regionální klimaticko-hydrologické podklady jsou v `history_v05/`. Jeho starší dokumentace a přípravné příznaky se vztahují k tehdejším vydáním; pro nynější analýzu používejte hlavní výstupy v `outputs/`.

## Zdroje, citace a použití

Každý modul má svůj manifest, slovník a vlastní metodiku. Základní odkazy:

- Železnice: Ondřej Bedrunka, PřF UPOL, diplomová práce 2023, https://dprace.geoinf.upol.cz/dprace/magisterske/bedrunka23/ .
- LUCC Czechia: Ivan Bičík a kolektiv, PřF UK, archiv a metodika https://web.natur.cuni.cz/ksgrrsek/lucc/ .
- SoilGrids: ISRIC World Soil Information, https://docs.isric.org/globaldata/soilgrids/ .
- HydroBASINS: HydroSHEDS, https://www.hydrosheds.org/products/hydrobasins .
- Geologie a ložiska: Česká geologická služba, https://cgs.gov.cz/en/maps-and-data/provision-of-data .
- CShapes 2.0: Schvitz et al., https://icr.ethz.ch/data/cshapes/ .
- CZ_RETRO: Karel Kuča / SOVAMM, zveřejnění přes NPÚ, https://geoportal.npu.cz/arcgis/rest/services/CZ_RETRO/CP_CZ_Retro_LS/MapServer .
- ČSÚ 170240-17: https://csu.gov.cz/obyvatelstvo-a-domy-v-obcich-podle-vysledku-scitani-od-roku-1869 .

Licence kódu R balíčku nepřelicencovává zdrojová data. SoilGrids používá CC BY 4.0; HydroBASINS vlastní podmínky HydroSHEDS; CShapes CC BY-NC-SA 4.0. LUCC stanoví studijní a akademické nekomerční použití s citací. U železničního archivu nebyla nalezena jednoznačná licence k veřejné redistribuci; u CZ_RETRO se liší licenční prohlášení služby a autorské stránky. Tato prohlášení zůstávají v manifestu. Jde o soukromé výzkumné předání; veřejné datové vydání R balíčku vyžaduje vyjasnit příslušné podmínky. Žádná data nebyla tímto krokem veřejně publikována.
'''
 (ROOT/'README_CZ.md').write_text(text,encoding='utf-8')
 (ROOT/'outputs/GIS_v06_README_CZ.md').write_text(text,encoding='utf-8')
 print('README_CZ.md written from verified inventory',flush=True)

if __name__=='__main__':main()
