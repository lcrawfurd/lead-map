# UK Lead Exposure Map

Interactive map of childhood lead exposure risk indicators across the UK, at both county/UA and parliamentary constituency level.

**Live site:** https://lcrawfurd.github.io/lead-map/constituencies.html

## Views

This repo hosts two independent maps that share the same IHME data source but otherwise operate standalone:

**Global lead exposure map** ([live](https://lcrawfurd.github.io/lead-map/global.html))
- World choropleth of IHME GBD 2021 BLL prevalence by country
- Click any of the 14 countries with IHME subnational estimates to drill in to ADM1/ADM2 boundaries: USA, UK, Japan, Kenya, Indonesia, Mexico, India, Iran, Brazil, Ethiopia, Norway, South Africa, Pakistan, Sweden

**UK detailed map** ([live](https://lcrawfurd.github.io/lead-map/constituencies.html))
- Per-constituency view with profile panel, indicator selector, and sortable rankings table — includes housing-age, mines, MP info etc.
- Or the county/UA view at [the root](https://lcrawfurd.github.io/lead-map/)

## Indicators

- **Adjusted IHME — modelled BLL ≥ 5** (default): each area's IHME GBD 2021 blood-lead total (England county/UA; Wales/Scotland/NI nation) re-allocated within-area by UK-fitted weights on housing age and IMD deprivation (regression on England county data; topsoil Pb and historic mines were tested and left as overlays — see methodology). The single figure used by the map, rankings and profile. See [docs/adjusted-ihme-methodology.md](docs/adjusted-ihme-methodology.md).
- Blood lead ≥ 5 µg/dL — raw IHME GBD 2021 (county/UA proxy; devolved nations flat), available as a toggle
- Housing built pre-1900 / pre-1945 / pre-1972 / pre-1992 (VOA CTSOP 2023, England & Wales)
- Historic metal mines (Macklin et al. 2023 + EA Inventory of Closed Mining Waste Facilities 2014)

## Rebuilding the data

```
python3 build_constituency_mapping.py   # constituency -> county/UA mapping (needs shapely)
python3 regress_ihme_predictors.py      # regression diagnostics (needs statsmodels/pandas)
python3 build_adjusted_ihme.py          # fits weights + writes adjusted columns (needs numpy)
```

## Features

- Hover for summary statistics, click a constituency for a full profile (MP, demographics, lead-exposure estimate, housing age breakdown, mines)
- **Rankings** button opens a sortable, searchable table of all 650 constituencies with CSV export
- Age-group selector for IHME BLL estimates

## Data sources

See the [Sources & methods](https://lcrawfurd.github.io/lead-map/sources.html) page for full details and citations.
