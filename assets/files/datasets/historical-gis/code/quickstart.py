"""Read the public GIS edition without extra Python dependencies.

Run from the extracted archive root:
    python code/quickstart.py
Optional argument: the path to the extracted archive.
"""
from pathlib import Path
import csv
import sqlite3
import sys

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]

def read_csv(name):
    with (root / "data" / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))

core = read_csv("gis_master_judicial_1930_public_v061.csv")
normals = read_csv("climate_normals_judicial_1930.csv")
normal_index = {row["district_year_id"]: row for row in normals}
normal_fields = [key for key in normals[0] if key.startswith("clim_normal_")]
assert len(core) == 330 and len(normal_index) == 330 and len(normal_fields) == 18
joined = [dict(row, **{key: normal_index[row["district_year_id"]][key]
                      for key in normal_fields}) for row in core]
assert len(joined[0]) == 462
semily = next(row for row in joined if row["district_year_id"] == "CZ1930-J-30102")
print("Explicit core + CRU-normal join:", len(joined), "districts,", len(semily), "fields")
print("Semily:", {key: semily[key] for key in
                  ("district_year_id", "NAZEV", "population", "mean_elevation_m")})

database = root / "outputs" / "historical_gis_czech_lands_v061.gpkg"
if database.exists():
    with sqlite3.connect("file:" + str(database.resolve()) + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        weather = db.execute(
            "SELECT calendar_year,temp_mean_c,precip_mm FROM gis_climate_annual "
            "WHERE geography=? AND district_year_id=? AND calendar_year=?",
            ("judicial_1930", "CZ1930-J-30102", 1930),
        ).fetchone()
        print("Semily climate, 1930:", dict(weather))
        flags = db.execute(
            "SELECT module,flag_code,note FROM publication_quality_flags "
            "WHERE geography=? AND district_year_id=?",
            ("judicial_1930", "CZ1930-J-30102"),
        ).fetchall()
        print("Publication flags:", [dict(row) for row in flags])

# With GeoPandas installed, read the spatial core as follows:
# import geopandas as gpd
# districts = gpd.read_file(database, layer="judicial_1930")
# districts.plot(column="population", legend=True)
#
# Consult docs/SOURCES_AND_REUSE.md before redistributing a joined table.
# CRU observations remain a separately licensed component of the collection.
