# Historical GIS publication input

`historical_gis_czech_lands_v061.gpkg.xz.part01` through `.part08` are consecutive
parts of the losslessly compressed, validated public GeoPackage. `parts.json`
records each part's size and SHA-256 and the checksum of their concatenation.
Splitting keeps individual repository transfers manageable and changes no data.
The `tables/` directory similarly stores parts of three large monthly CSV.GZ
files. The same manifest pins those files; the build restores their original
bytes and normal public filenames before packaging. Each part is at most 10 MB.
The expanded GeoPackage SHA-256 is recorded in the public
`assets/files/datasets/historical-gis/release_manifest.json` and in the
histCzechia 0.2.1 release catalogue.

`python3 scripts/prepare_historical_gis.py` joins the parts, checks all checksums and database
integrity, then generates the public GeoPackage ZIP, tabular ZIP and map ZIP.
Quarto runs this preparation before rendering the site. The generated archives
are served by GitHub Pages; their duplicate bytes are not committed to Git.

The public database contains independently sourced components under their
respective terms. See the published source and reuse statement. Original
provider geometry layers listed in the release manifest are omitted.
