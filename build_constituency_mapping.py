#!/usr/bin/env python3
"""Regenerate the constituency -> county/UA mapping from CURRENT (2024) data.

The previous CONSTITUENCY_TO_COUNTY (inlined in constituencies.html) was keyed on
2019 constituency names; 236 of 650 names changed at the 2024 review, so those
seats silently fell through to a nation-average fallback on the map.

This rebuilds it from the seat's authoritative 2024 LAD (`la_name`, from
constituency_profile.csv), mapped to the IHME county/UA geography. Wales/Scotland/NI
go to the nation (IHME has no sub-national estimate there).

England: county = lookup(la_name), where
  - if la_name is itself an IHME county/UA (unitary, London borough, met district)
    -> use it directly;
  - if la_name is a two-tier shire district -> its parent county, found by which
    county polygon contains the district's interior point (districts nest cleanly
    inside counties, so this is exact). Recently-reorganised districts absent from
    uk_lads.json are handled by REORG_OVERRIDES;
  - otherwise (blank la_name) -> interior point of the constituency itself.

Using the LAD rather than the constituency polygon avoids area-overlap errors for
seats whose populated core and largest land area sit in different authorities
(e.g. Morecambe and Lunesdale: people in Lancashire, rural acreage in Cumbria).

Writes constituency_to_county.json: { "<2024 constituency name>": "<county|nation>" }
"""
import csv
import json

from shapely.geometry import shape
from shapely.strtree import STRtree

AGE = "<20"
NATIONS = ("England", "Wales", "Scotland", "Northern Ireland")

# Explicit LAD -> IHME county/UA, applied last so it wins over the spatial pass.
# Most are post-2018 reorganisations absent from uk_lads.json. City of London has
# no IHME estimate and its only seat (Cities of London and Westminster) is
# overwhelmingly Westminster. Bournemouth, Christchurch and Poole is deliberately
# omitted: IHME keeps Bournemouth/Poole/Dorset separate, so those seats resolve by
# constituency polygon instead.
LAD_OVERRIDES = {
    "Cumberland": "Cumbria",
    "Westmorland and Furness": "Cumbria",
    "North Northamptonshire": "Northamptonshire",
    "West Northamptonshire": "Northamptonshire",
    "East Suffolk": "Suffolk",
    "West Suffolk": "Suffolk",
    "Folkestone and Hythe": "Kent",
    "City of London": "Westminster",
}


def ihme_locations():
    locs = set()
    with open("IHME_GBD_2021_LEAD_RISK_1990_2021_PROP_ABOVE_5_2021_BOTH_Y2024M06D05.CSV",
              newline="") as f:
        for r in csv.DictReader(f):
            if r["measure_name"] == "Proportion" and r["age_group_name"] == AGE:
                locs.add(r["location_name"])
    return locs


def load_feats(path):
    gj = json.load(open(path))
    return gj["features"] if isinstance(gj, dict) else gj


def containing_county(geom, cy_names, cy_geoms, tree):
    """County whose polygon contains geom's interior point, else max land overlap."""
    rp = geom.representative_point()
    cand = list(tree.query(geom))
    hit = next((cy_names[i] for i in cand if cy_geoms[i].contains(rp)), None)
    if hit:
        return hit
    best, best_area = None, 0.0
    for i in cand:
        a = geom.intersection(cy_geoms[i]).area
        if a > best_area:
            best_area, best = a, cy_names[i]
    if best:
        return best
    return cy_names[min(range(len(cy_names)), key=lambda i: rp.distance(cy_geoms[i]))]


def main():
    ihme = ihme_locations()

    # IHME-backed county/UA polygons (drops City of London, Isles of Scilly).
    cy_names, cy_geoms = [], []
    for f in load_feats("uk_counties.json"):
        nm = f["properties"]["name"]
        if nm in ihme:
            cy_names.append(nm)
            cy_geoms.append(shape(f["geometry"]).buffer(0))
    tree = STRtree(cy_geoms)

    # district -> county, from LAD polygons (England districts only need it).
    lad_to_county = {}
    for f in load_feats("uk_lads.json"):
        if f["properties"].get("nation") != "England":
            continue
        nm = f["properties"]["name"]
        lad_to_county[nm] = nm if nm in ihme else \
            containing_county(shape(f["geometry"]).buffer(0), cy_names, cy_geoms, tree)
    lad_to_county.update(LAD_OVERRIDES)  # overrides win over the spatial pass

    cfeats = load_feats("uk_constituencies.json")
    la_by_seat = {r["PCON24NM"]: r["la_name"]
                  for r in csv.DictReader(open("constituency_profile.csv"))}

    mapping = {}
    via = {"nation": 0, "la_county": 0, "la_district": 0, "spatial": 0}
    for f in cfeats:
        name = f["properties"]["name"]
        nation = f["properties"]["nation"]
        if nation != "England":
            mapping[name] = nation
            via["nation"] += 1
            continue
        la = la_by_seat.get(name, "")
        if la in ihme:
            mapping[name] = la
            via["la_county"] += 1
        elif la in lad_to_county:
            mapping[name] = lad_to_county[la]
            via["la_district"] += 1
        else:
            mapping[name] = containing_county(shape(f["geometry"]).buffer(0),
                                              cy_names, cy_geoms, tree)
            via["spatial"] += 1

    json.dump(mapping, open("constituency_to_county.json", "w"),
              indent=0, sort_keys=True, ensure_ascii=False)
    print(f"Wrote constituency_to_county.json: {len(mapping)} constituencies")
    print("  resolved via:", via)
    bad = [k for k, v in mapping.items() if v not in NATIONS and v not in ihme]
    print("  England seats mapped to a non-IHME county (should be 0):", bad or "none")
    _validate(mapping)


def _validate(mapping):
    import re
    m = re.search(r"const CONSTITUENCY_TO_COUNTY = (\{.*?\});",
                  open("constituencies.html").read(), re.S)
    if not m:
        return
    old = json.loads(m.group(1))
    shared = [k for k in mapping if k in old]
    diff = [(k, old[k], mapping[k]) for k in shared if mapping[k] != old[k]]
    print(f"\n  vs old mapping on {len(shared)} unchanged-name seats: "
          f"agree {len(shared)-len(diff)}, differ {len(diff)}")
    for k, o, n in diff:
        print(f"      {k}: {o} -> {n}")


if __name__ == "__main__":
    main()
