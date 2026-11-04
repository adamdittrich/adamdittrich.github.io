#!/usr/bin/env python3
"""Publish real atlas PNGs, WebP previews and English gallery metadata.

Requires Pillow. Inputs are the corrected Atlas I folder and the original
Atlas II folder, each with its manifest and maps directory. This script does
not recalculate observations or redraw figures.

Example:
  python build_gallery.py --atlas1 /path/to/atlas_public --atlas2 /path/to/atlas2
"""
from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path

from PIL import Image


CENSUS = 'Historical GIS / URRlab, Charles University · Census 1930'
CLIMATE = 'Climatic Research Unit, University of East Anglia · CRU-TS v4.10'
ECONOMY_WARNING = 'Shares use economically active people with a known sector. Vsetín and Vejprty are withheld pending source checks.'
VOTE_WARNING = '326 districts shown. Praha-sever and Zlín are missing; both Brno districts are withheld because electoral and judicial territories may differ.'

# title, group, period, summary, source, warning
CAPTIONS = {
  'atlas1': {
    1: (
      'Czechoslovakia and the district study area',
      'Borders and territory', '1930 state and district boundaries',
      'The Czech lands form only the western part of interwar Czechoslovakia. Seeing Slovakia and Subcarpathian Ruthenia alongside the study area helps explain why eastern Moravia was not an international border region.',
      'CShapes 2.0 · Historical GIS / URRlab',
      'The district census collection covers the Czech lands; its findings do not automatically describe the whole republic.'
    ),
    2: (
      'Where people were concentrated',
      'People and society', '1930 census',
      'Population density reveals the contrast between sparsely settled uplands and compact urban districts. Prague recorded 4,932 inhabitants per km², while Hartmanice recorded 28. A large district on the map need not carry a large population.',
      CENSUS,
      'Uses the reported historical area and a logarithmic colour scale. Hatching marks three districts with unresolved territorial comparability.'
    ),
    3: (
      'Born in the municipality of residence',
      'People and society', '1930 census',
      'The share of residents born in their current municipality offers a view of local rootedness and lifetime mobility. It ranges from 77.6% in Strážnice to 25.3% in Praha-východ, suggesting very different migration histories.',
      CENSUS,
      'Municipal birthplace is not district birthplace. The measure does not isolate moves made during the First Republic.'
    ),
    4: (
      'Children and the geography of age',
      'People and society', '1930 census · ages 0–14',
      'Children made up 36.2% of residents in Rožnov pod Radhoštěm and 15.2% in Prague. These contrasting age structures imply different potential demands for schools and different sizes of future working-age cohorts.',
      CENSUS,
      'A population share is not a birth rate; migration and the size of other generations also matter.'
    ),
    5: (
      'Older residents across districts',
      'People and society', '1930 census · ages 65+',
      'Older people formed a much larger share in some northern districts than in fast-growing industrial centres. Read this alongside the children map to distinguish ageing districts from places with a large middle-aged population.',
      CENSUS,
      'The share aged 65 and over does not measure life expectancy or pension coverage.'
    ),
    6: (
      'German nationality in the census',
      'Identity and religion', '1930 census',
      'Vrchlabí and Semily were nearby industrial districts with sharply different census nationality profiles: 90.4% versus 1.6% German nationality. Their contrast shows why economic geography and national identification should be examined separately.',
      CENSUS,
      'Census nationality is a recorded historical category, not evidence of an individual resident’s political preferences.'
    ),
    7: (
      'Polish nationality and the Těšín region',
      'Identity and religion', '1930 census',
      'Polish nationality was strongly concentrated around Těšín. Jablunkov, with 67.1%, was the only district in this collection with a Polish majority, while Český Těšín and Fryštát also had substantial Polish populations.',
      CENSUS,
      'District averages conceal differences between municipalities and neighbourhoods.'
    ),
    8: (
      'Roman Catholic affiliation',
      'Identity and religion', '1930 census',
      'Roman Catholics formed a majority in 321 of the 330 districts, but that broad majority hid large local differences. High Catholic shares occurred in areas with different nationality profiles, so religion and nationality are not interchangeable measures.',
      CENSUS,
      'Recorded affiliation does not measure religious practice or personal belief.'
    ),
    9: (
      'Protestant regions',
      'Identity and religion', '1930 census',
      'Strong Protestant communities appeared at opposite ends of the Czech lands, including Aš and Jablunkov. Comparing Aš with predominantly Catholic Horní Planá illustrates religious diversity within districts reporting very high German nationality shares.',
      CENSUS,
      'Several historical Protestant denominations are combined in this figure.'
    ),
    10: (
      'The Czechoslovak Church',
      'Identity and religion', '1930 census',
      'The Czechoslovak Church had concentrated regional support: 45.4% of residents in Louny, 39.8% in Turnov and 26.8% in Semily. A single national average would obscure these distinctive local religious landscapes.',
      CENSUS,
      'Shares refer to the whole district population and census affiliation.'
    ),
    11: (
      'Residents reporting no religion',
      'Identity and religion', '1930 census',
      'Železný Brod, Kladno and Semily had substantial populations reporting no religious affiliation. Read this with the Czechoslovak Church map: a low Catholic share can reflect several different religious and secular configurations.',
      CENSUS,
      'The census category does not reveal the full range of personal beliefs.'
    ),
    12: (
      'Jewish religion and Jewish nationality',
      'Identity and religion', '1930 census · two maps',
      'Two maps use the same scale to distinguish religion from nationality. In Prague, 4.17% reported Jewish religion and 0.97% Jewish nationality. These census fields describe different population totals and should not be substituted for one another.',
      CENSUS,
      'District aggregates cannot reveal how individual people combined nationality and religion.'
    ),
    13: (
      'Districts centred on agricultural work',
      'Economy and work', '1930 census',
      'Agriculture employed 74.1% of economically active people with a known sector in Libáň and 68.1% in Mladá Vožice. This map identifies districts whose employment structure makes historical weather and harvest conditions especially relevant research questions.',
      CENSUS,
      ECONOMY_WARNING
    ),
    14: (
      'Industry and manufacturing crafts',
      'Economy and work', '1930 census',
      'Industrial employment was prominent in upland and mountain districts as well as cities. Semily and Vrchlabí recorded 70.8% and 62.9%, showing why elevation alone cannot describe an economy’s occupational structure.',
      CENSUS,
      'Industry includes manufacturing crafts but excludes construction. ' + ECONOMY_WARNING
    ),
    15: (
      'Services, cities and spa districts',
      'Economy and work', '1930 census',
      'The service sector was especially prominent in Prague, the historical Brno-město district and Mariánské Lázně. Similar service shares can represent quite different mixtures of administration, transport, commerce and specialised local activities.',
      CENSUS,
      'A service share is not a direct measure of income or prosperity. ' + ECONOMY_WARNING
    ),
    16: (
      'Transport employment and railway nodes',
      'Economy and work', '1930 census',
      'Břeclav, Přerov and Bohumín stand out for transport employment. Comparing their occupational shares with the railway network provides a useful starting point for investigating transport centres and local labour markets.',
      CENSUS,
      'Transport includes more than railway workers. ' + ECONOMY_WARNING
    ),
    17: (
      'Forestry, hunting and fishing livelihoods',
      'Economy and work', '1930 census',
      'Some upland economies had strong industrial employment; others relied more on forestry and related occupations. Horní Planá and Hartmanice illustrate the latter pattern and the diversity of mountain livelihoods.',
      CENSUS,
      'This is an employment share, not forest land cover. ' + ECONOMY_WARNING
    ),
    18: (
      'The railway network in 1930',
      'Transport', 'Reconstructed operating network · 1930',
      'The line map makes routes and junctions visible alongside district boundaries. It helps connect industrial districts, towns and rural areas without reducing the network to a single length or density value per district.',
      'Ondřej Bedrunka / Palacký University Olomouc, 2023 · project chronology checks',
      'Poříčany–Nymburk lacks source geometry. Horní Lideč–Púchov is excluded from 1930 after its 1937 opening was verified.'
    ),
    19: (
      'Railway additions after 1921',
      'Transport', '1921 baseline; openings 1922–1938 active in 1938',
      'Orange segments show recorded additions to the inherited network, including possible realignments. The source contains about 103.6 km of these routes across 19 districts, prompting questions about how infrastructure adapted to the new state.',
      'Ondřej Bedrunka / Palacký University Olomouc, 2023 · project chronology checks',
      'The orange length is not the net growth of the entire national railway system or a complete archival construction inventory.'
    ),
    20: (
      'Sudeten German Party vote share',
      'Elections', '1935 parliamentary election',
      'SdP support was geographically concentrated but far from uniform. Even among districts with at least 80% German nationality, its valid-vote share ranged from about 34% to 78%, illustrating variation within that broad census group.',
      'Inherited GIS election panel · selected historical ČSÚ source checks',
      VOTE_WARNING + ' Vote shares and nationality shares have different denominators.'
    ),
    21: (
      'Communist Party vote share',
      'Elections', '1935 parliamentary election',
      'KSČ support was strong in districts such as Slaný, Kladno and Slezská Ostrava. Its geography differs from both industrial employment and nationality alone, inviting closer investigation of industries and local social structures.',
      'Inherited GIS election panel · selected historical ČSÚ source checks',
      VOTE_WARNING + ' These two parties do not represent the full interwar party system.'
    ),
    22: (
      'Changing Communist Party support',
      'Elections', '1929–1935 parliamentary elections',
      'The change in KSČ vote share varied across districts: gains in some places coexisted with marked declines elsewhere. The figure uses the conservative set of 273 districts with usable paired observations and no retained comparability warning.',
      'Inherited GIS election panel · conservative comparison sample',
      '57 districts are not assigned a change. Differences are percentage points, not evidence that particular voters switched parties.'
    ),
    23: (
      'Mountains, lowlands and district elevation',
      'Landscape and environment', 'Modern Copernicus GLO-90 terrain reference',
      'Mean elevation provides geographical context for climate, agriculture and route placement. Vrchlabí averages roughly 824 m, Semily 464 m and Břeclav 172 m; comparing this map with employment avoids treating all upland economies alike.',
      'Copernicus GLO-90 / WorldDEM-90 · project district aggregation',
      'Modern surface-model averages describe district land, not the elevation of the district town or a historical survey.'
    ),
    24: (
      'River corridors as geographical context',
      'Landscape and environment', 'Modern HydroRIVERS network',
      'The larger river network offers a spatial reference for settlements, transport and production sites. Showing selected major corridors keeps the map legible while making clear why administrative districts and natural drainage systems are different geographies.',
      'HydroRIVERS v1.0 / HydroSHEDS · Strahler order ≥ 4',
      'This modern, filtered network does not show interwar flows, navigability or floods, and it omits many smaller streams.'
    ),
    25: (
      'Distance to Czechoslovakia’s international border',
      'Borders and territory', 'State-border snapshot · 1 January 1930',
      'Distances are measured to the outer border of the whole Czechoslovak state. Eastern Moravia therefore is not treated as a frontier merely because it adjoins Slovakia. Border proximity is one specific aspect of location, distinct from economic remoteness.',
      'CShapes 2.0 · project distances from interior district points',
      'Reference points are not necessarily district towns or population centres. Generalised borders make these approximate geographical distances.'
    ),
    26: (
      'Nationality and economic structure together',
      'Economy and work', '1930 census · descriptive classification',
      'Four categories combine a German-nationality majority with whether industrial employment exceeds agriculture. Semily and Vrchlabí occupy the industrial side of this comparison but different nationality categories, showing combinations that single-variable maps can hide.',
      CENSUS + ' · project classification',
      'Thresholds are descriptive, not a causal model or established social typology. Vsetín and Vejprty are withheld.'
    ),
    27: (
      'The territorial transformation of 1938',
      'Borders and territory', '1 January 1930 compared with 31 December 1938',
      'The comparison places territorial changes in the Czech lands alongside changes in Slovakia and Subcarpathian Ruthenia. Read with the industrial and railway maps, it raises questions about altered regional connections and infrastructure.',
      'CShapes 2.0 · generalised state polygons',
      'This overview does not calculate exact losses of population, production capacity or district area, or the day-by-day occupation sequence.'
    ),
  },
  'atlas2': {
    1: (
      'Agricultural employment meets the 1935 rainfall deficit',
      'Climate', 'Employment: 1930; rainfall: April–September 1935 vs 1901–1928',
      'Eighty-five districts combine at least 40% agricultural employment with a growing-season precipitation deficit of at least 20%. The same weather anomaly occurred in very different economic settings, making this a useful way to select districts for harvest or income research.',
      CENSUS + ' · ' + CLIMATE,
      'The thresholds are descriptive and do not measure crop losses or causal effects. Two economic observations are withheld.'
    ),
    2: (
      'Specialised and diversified employment',
      'Economy and work', '1930 census · eight occupational branches',
      'The effective number of sectors summarises how evenly employment is spread across eight broad branches. Both an industrial district such as Varnsdorf and an agricultural district such as Libáň can be concentrated despite very different economic structures.',
      CENSUS + ' · inverse concentration index',
      'The index does not count firms or establish wealth or crisis resilience. Vsetín and Vejprty are withheld; 328 districts are shown.'
    ),
    3: (
      'Religious diversity',
      'Identity and religion', '1930 census · ten affiliation categories',
      'The effective number of religious categories distinguishes relatively balanced mixtures from dominant affiliations. Semily and Vrchlabí differ sharply despite their proximity. The calculation includes the no-religion category, so diversity and secularisation are distinct concepts.',
      CENSUS + ' · inverse concentration index',
      'Other/unknown affiliation is excluded and shares are renormalised. Diversity alone does not establish tolerance or conflict.'
    ),
    4: (
      'Children and older people relative to ages 15–64',
      'People and society', '1930 census',
      'Prague had about 25.6 children and older residents per 100 people aged 15–64; Rožnov pod Radhoštěm had 69.9. This comparison describes the different age structures behind district populations and potential demands on schools and care.',
      CENSUS,
      'Age groups do not identify who was actually employed, dependent or supporting a household.'
    ),
    5: (
      'Women per 100 men',
      'People and society', '1930 census · all ages',
      'Women outnumbered men in 301 districts and men outnumbered women in 29. Contrasting places can be selected for research on employment, migration and age structure, but the census ratio alone cannot explain the balance.',
      CENSUS,
      'Uses the whole present population, including children. It does not isolate war losses or migration effects.'
    ),
    6: (
      'Widows and widowers on a shared scale',
      'People and society', '1930 census · two maps',
      'The two maps use an identical colour scale, revealing much higher widowhood shares among women than men across all 330 districts. They invite questions about age, longevity, remarriage and household livelihoods.',
      CENSUS,
      'Denominators include all women or all men, including children. These are not age-standardised rates or counts of war widows.'
    ),
    7: (
      'Electoral weight in numbers of votes',
      'Elections', '1935 parliamentary election · two maps',
      'Equal-scale circles show the numerical support behind SdP and KSČ vote shares. Liberec’s lower SdP percentage represented many more votes than Lázně Kynžvart’s higher percentage; similarly, Prague outweighed smaller districts with stronger KSČ shares.',
      'Inherited GIS election panel · vote counts reconstructed from exact shares and valid-vote totals',
      VOTE_WARNING + ' Circle area, not radius, represents votes. This is not a complete national vote total.'
    ),
    8: (
      'The temperature contrast between July and January',
      'Climate', 'Climate reference period · 1901–1928',
      'The seasonal contrast adds information that an annual mean temperature hides. July exceeded January by about 18.0°C in Horní Blatná and 20.4°C in Hustopeče, illustrating differences in the average annual temperature cycle.',
      CLIMATE,
      'Difference of monthly means, not temperature records. The underlying 0.5° grid cannot resolve every valley or elevation difference.'
    ),
    9: (
      'How much rain fell in summer?',
      'Climate', 'June–August share of annual precipitation · 1901–1928',
      'Summer accounted for about 41.2% of average annual precipitation in Písek and 29.5% in Semily. This map compares seasonal distribution, adding a different perspective from annual rainfall totals.',
      CLIMATE,
      'A ratio of mean seasonal and annual totals does not measure storm intensity, soil-water retention or consecutive dry days.'
    ),
    10: (
      'Ground frost in April and May',
      'Climate', 'Mean April–May ground-frost days · 1901–1928',
      'The average spring ground-frost frequency ranges from about 7.8 days in Hustopeče to 21.6 in Horní Blatná. It provides climatic context for comparing historical crop choices and growing conditions.',
      CLIMATE,
      'CRU FRS is an empirically derived ground-frost indicator, not direct local observations or the date of the last frost; it is not 2 m air frost.'
    ),
    11: (
      'A century of changing forest cover',
      'Landscape and environment', 'LUCC source snapshots · 1845–1948',
      'Forest shares increased in 201 of the 328 comparable districts and decreased in 127. Vsetín and Bohumín illustrate contrasting long-run changes around the interwar period, rather than a uniform national landscape trajectory.',
      'LUCC Czechia / Ivan Bičík and colleagues, Charles University · area allocation',
      'Changes are percentage points. The nominal 1845 source reflects c. 1826–1843 surveys; the interval is not exclusively interwar. Two districts lack comparable coverage.'
    ),
    12: (
      'Soil clay content as environmental context',
      'Landscape and environment', 'Modern SoilGrids 2.0 · depth 0–30 cm',
      'Modern predicted clay content provides one environmental characteristic for comparison with historical crop patterns. The map shows the proportion of clay in fine earth, aggregated across soil depths and district areas.',
      'ISRIC – World Soil Information · SoilGrids 2.0',
      'Not a 1930 observation or a measure of fertility. 293 districts meet 90% texture coverage; 37 are grey.'
    ),
  },
}


def rgb_on_white(image: Image.Image) -> Image.Image:
    rgba = image.convert('RGBA')
    background = Image.new('RGB', rgba.size, 'white')
    background.paste(rgba, mask=rgba.getchannel('A'))
    return background


def webp(source: Path, destination: Path, width: int, quality: int) -> None:
    with Image.open(source) as original:
        rendered = rgb_on_white(original)
        height = round(rendered.height * width / rendered.width)
        rendered = rendered.resize((width, height), Image.Resampling.LANCZOS)
        rendered.save(destination, 'WEBP', quality=quality, method=6)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--atlas1', type=Path, required=True)
    parser.add_argument('--atlas2', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--url-prefix', default='assets/files/datasets/historical-gis/maps')
    args = parser.parse_args()
    destination = args.output / 'maps'
    destination.mkdir(parents=True, exist_ok=True)
    gallery = []
    thematic_maps = 0
    for atlas_id, folder, manifest_name in (
        ('atlas1', args.atlas1, 'atlas_manifest.json'),
        ('atlas2', args.atlas2, 'atlas2_manifest.json'),
    ):
        manifest = json.loads((folder / manifest_name).read_text(encoding='utf-8'))
        expected = set(CAPTIONS[atlas_id])
        found = {item['number'] for item in manifest}
        if found != expected:
            raise ValueError(f'{atlas_id}: manifest/caption mismatch {found ^ expected}')
        for item in sorted(manifest, key=lambda value: value['number']):
            number = item['number']
            source_image = folder / item['file']
            name = f'{atlas_id}_{number:02d}'
            full = destination / f'{name}.png'
            thumbnail = destination / f'{name}_thumb.webp'
            shutil.copy2(source_image, full)
            webp(source_image, thumbnail, width=680, quality=88)
            title, group, period, summary, source, warning = CAPTIONS[atlas_id][number]
            prefix = args.url_prefix.rstrip('/')
            gallery.append({
                'id': name,
                'title': title,
                'group': group,
                'period': period,
                'summary': summary,
                'thumbnail': f'{prefix}/{thumbnail.name}',
                'image': f'{prefix}/{full.name}',
                'source': source,
                'warning': warning,
            })
            thematic_maps += int(item['maps'])
    if len(gallery) != 39 or thematic_maps != 42:
        raise ValueError(f'Unexpected atlas size: {len(gallery)} figures / {thematic_maps} maps')
    webp(destination / 'atlas1_02.png', destination / 'preview-population-density.webp', width=1400, quality=91)
    (args.output / 'gallery.json').write_text(json.dumps(gallery, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({
        'figures': len(gallery),
        'thematic_maps': thematic_maps,
        'groups': dict(Counter(item['group'] for item in gallery)),
        'thumbnail_total_bytes': sum(path.stat().st_size for path in destination.glob('*_thumb.webp')),
        'png_total_bytes': sum(path.stat().st_size for path in destination.glob('atlas*.png')),
        'preview': str(destination / 'preview-population-density.webp'),
    }, indent=2))


if __name__ == '__main__':
    main()
