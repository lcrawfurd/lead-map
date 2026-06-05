#!/usr/bin/env python3
"""Build the "adjusted IHME" constituency figure.

Best-data-per-area model: take the finest IHME geography available for each area
as the baseline blood-lead prevalence, then re-allocate that area's child cases
across its constituencies in proportion to the existing housing-age + IMD risk
weights (carried by the `rate_per_1000_bl_5plus` column).

  - England  -> baseline = parent LAD/county IHME value (local variation kept)
  - Wales / Scotland / Northern Ireland -> baseline = nation IHME value
    (no sub-national IHME estimate exists)

Each area's child-population-weighted mean of the adjusted figure equals its IHME
baseline, so this re-levels the existing model onto IHME baselines without
inflating totals. See docs/adjusted-ihme-methodology.md.

Reads:  IHME_*PROP_ABOVE_5*.CSV, constituency_to_county.json (run
        build_constituency_mapping.py first), constituency_profile.csv
Writes: constituency_profile.csv (adds adjusted columns; idempotent)
"""
import csv
import glob
import json
import sys
from collections import defaultdict

AGE = "<20"  # IHME age group matching child_pop_0_19 (children 0-19)
ADJ_COLS = ["adj_rate_per_1000", "adj_children", "adj_prop_pct",
            "baseline_area", "baseline_ihme_pct"]


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load_ihme_props():
    """location_name -> proportion (0-1) of children 0-19 with BLL >= 5."""
    matches = glob.glob("IHME_*PROP_ABOVE_5*.CSV") + glob.glob("IHME_*PROP_ABOVE_5*.csv")
    if not matches:
        sys.exit("ERROR: IHME PROP_ABOVE_5 CSV not found in this directory.")
    prop = {}
    with open(matches[0], newline="") as f:
        for r in csv.DictReader(f):
            if r["measure_name"] == "Proportion" and r["age_group_name"] == AGE:
                prop[r["location_name"]] = float(r["mean"])
    return prop


def load_constituency_to_county():
    try:
        return json.load(open("constituency_to_county.json"))
    except FileNotFoundError:
        sys.exit("ERROR: constituency_to_county.json missing — run "
                 "build_constituency_mapping.py first.")


def main():
    prop = load_ihme_props()
    c2c = load_constituency_to_county()

    with open("constituency_profile.csv", newline="") as f:
        reader = csv.DictReader(f)
        base_fields = [c for c in reader.fieldnames if c not in ADJ_COLS]
        rows = list(reader)

    # Resolve each row's baseline area + IHME proportion. constituency_to_county.json
    # already encodes the county for England seats and the nation for W/S/NI.
    fallbacks = []
    for r in rows:
        name, nation = r["PCON24NM"], r["nation"]
        area = c2c.get(name, nation)
        p_area = None
        for key in (area, nation, "United Kingdom"):
            if key in prop:
                p_area = prop[key]
                if key != area:
                    fallbacks.append(name)
                area = key
                break
        r["_area"] = area
        r["_p"] = p_area

    if fallbacks:
        print(f"WARNING: {len(fallbacks)} seats fell back off their mapped area:",
              fallbacks[:10])

    # Child-pop-weighted mean of the risk weight (rate_per_1000) per baseline area.
    grp_num, grp_den = defaultdict(float), defaultdict(float)
    for r in rows:
        rate, cp = fnum(r["rate_per_1000_bl_5plus"]), fnum(r["child_pop_0_19"])
        if rate is None or cp is None or r["_p"] is None:
            continue
        grp_num[r["_area"]] += rate * cp
        grp_den[r["_area"]] += cp

    # Adjusted figure: re-level within area to the IHME baseline.
    for r in rows:
        rate, cp = fnum(r["rate_per_1000_bl_5plus"]), fnum(r["child_pop_0_19"])
        if rate is None or cp is None or r["_p"] is None or grp_den[r["_area"]] == 0:
            for c in ADJ_COLS:
                r[c] = ""
            continue
        wmean = grp_num[r["_area"]] / grp_den[r["_area"]]
        adj_rate = r["_p"] * 1000 * (rate / wmean)  # per 1,000
        r["adj_rate_per_1000"] = round(adj_rate, 1)
        r["adj_children"] = int(round(adj_rate / 1000 * cp))
        r["adj_prop_pct"] = round(adj_rate / 10, 2)  # percent
        r["baseline_area"] = r["_area"]
        r["baseline_ihme_pct"] = round(r["_p"] * 100, 2)

    for r in rows:
        r.pop("_area", None)
        r.pop("_p", None)

    out_fields = base_fields + ADJ_COLS
    with open("constituency_profile.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out_fields)
        w.writeheader()
        w.writerows(rows)

    _sanity(rows)


def _sanity(rows):
    from collections import Counter
    data = [r for r in rows if r.get("adj_rate_per_1000") not in (None, "")]
    print(f"\nWrote adjusted columns for {len(data)}/{len(rows)} constituencies.\n")
    for nat in ["England", "Wales", "Scotland", "Northern Ireland"]:
        sub = [r for r in data if r["nation"] == nat]
        if not sub:
            continue
        num = sum(r["adj_rate_per_1000"] * fnum(r["child_pop_0_19"]) for r in sub)
        den = sum(fnum(r["child_pop_0_19"]) for r in sub)
        lo = min(r["adj_rate_per_1000"] for r in sub)
        hi = max(r["adj_rate_per_1000"] for r in sub)
        print(f"  {nat:18} mean={num/den:5.1f}/1000  range {lo:.1f}-{hi:.1f}  (n={len(sub)})")
    top = sorted(data, key=lambda r: -r["adj_rate_per_1000"])[:10]
    print("\n  Top 10:")
    for r in top:
        print(f"    {r['adj_rate_per_1000']:5.1f}  {r['nation']:8} {r['PCON24NM']}")
    worst100 = sorted(data, key=lambda r: -r["adj_rate_per_1000"])[:100]
    print("\n  Worst-100 nation split:", dict(Counter(r["nation"] for r in worst100)))


if __name__ == "__main__":
    main()
