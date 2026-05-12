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

- Blood lead ≥ 5 µg/dL (IHME GBD 2021, county/UA proxy)
- Housing built pre-1900 / pre-1945 / pre-1972 / pre-1992 (VOA CTSOP 2023, England & Wales)
- Historic metal mines (Macklin et al. 2023 + EA Inventory of Closed Mining Waste Facilities 2014)

## Features

- Hover for summary statistics, click a constituency for a full profile (MP, demographics, lead-exposure estimate, housing age breakdown, mines)
- **Rankings** button opens a sortable, searchable table of all 650 constituencies with CSV export
- Age-group selector for IHME BLL estimates

## Data sources

See the [Sources & methods](https://lcrawfurd.github.io/lead-map/sources.html) page for full details and citations.
