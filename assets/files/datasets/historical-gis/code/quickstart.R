# Run from the extracted public archive root: Rscript code/quickstart.R
# Base R is sufficient for this first example.
core <- read.csv("data/gis_master_judicial_1930_public_v061.csv",
                 check.names = FALSE)
climate <- read.csv("data/climate_normals_judicial_1930.csv",
                    check.names = FALSE)
fields <- grep("^clim_normal_", names(climate), value = TRUE)
idx <- match(core$district_year_id, climate$district_year_id)
stopifnot(nrow(core) == 330L, ncol(core) == 444L,
          length(fields) == 18L, !anyNA(idx),
          !anyDuplicated(climate$district_year_id))
districts <- cbind(core, climate[idx, fields, drop = FALSE])
stopifnot(ncol(districts) == 462L)
semily <- subset(districts, district_year_id == "CZ1930-J-30102")
print(semily[c("NAZEV", "population", "mean_elevation_m", "river_length_km")])

# Optional package workflow, after installing its dependencies and source tar:
# install.packages(c("sf", "DBI", "RSQLite", "digest"))
# install.packages("r_package/histCzechia_0.2.1.tar.gz",
#                  repos = NULL, type = "source")
# library(histCzechia)
# hc_use("outputs/historical_gis_czech_lands_v061.gpkg")
# hc_districts(district = "Semily")
# hc_climate(years = 1930, district = "Semily")
# hc_railways(years = 1930, district = "Semily")
# hc_quality_flags(district = "Semily")
# hc_profile("Semily", climate_years = 1930)
#
# hc_districts() returns the public core. hc_climate_normals() supplies
# the separate 18 CRU-normal fields; see the package README for an explicit join.
# Read docs/SOURCES_AND_REUSE.md before redistributing data.
