#!/usr/bin/env python3
"""Build the "adjusted IHME" constituency figure.

Best-data-per-area model. For each baseline area -- an English county/UA, or a
whole devolved nation (Wales/Scotland/NI have no sub-national IHME) -- take the
area's IHME GBD 2021 child blood-lead total and re-allocate it across the area's
constituencies in proportion to a modelled relative risk. Because each area's
total is preserved, this re-levels the within-area pattern onto IHME baselines
rather than inflating totals.

The within-area risk weight is a constituency's PREDICTED IHME blood-lead level
from a regression fitted on the England county/UA units:

    ihme_pct ~ pre1945_housing + imd_score

i.e. UK-fitted weights, not imported US odds ratios. Topsoil Pb and historic
mines were tested as predictors and left out of the headline figure: mines show
no positive signal, and soil predicts blood lead only outside London (its signal
collapses when London -- highest soil, average BLL -- is included) and would
extrapolate poorly to Wales/Scotland. Both remain as standalone map overlays.
See regress_ihme_predictors.py and docs/adjusted-ihme-methodology.md.

Reads:  IHME_*PROP_ABOVE_5*.CSV, constituency_to_county.json (run
        build_constituency_mapping.py first), constituency_profile.csv
Writes: constituency_profile.csv (adds adjusted columns; idempotent)
"""
import csv
import glob
import json
import sys
from collections import defaultdict

import numpy as np

AGE = "<20"
ADJ_COLS = ["adj_rate_per_1000", "adj_children", "adj_prop_pct",
            "baseline_area", "baseline_ihme_pct"]
NATIONS = ("England", "Wales", "Scotland", "Northern Ireland")
PREDICTORS = ("pre1945", "imd")

# --- Optional re-leveling to a newer GBD round (e.g. GBD 2023) ----------------
# The baselines above come from the GBD 2021 round -- the last round that resolved
# UK lead sub-nationally. A newer round (GBD 2023) gives lower *national* levels
# but no English sub-national detail. If a newer-round "proportion above 5 ug/dL"
# (= 50 ug/L) national CSV is dropped into this directory, re-level each area's
# 2021 baseline by the ratio new/2021 at the finest geography present in BOTH
# files (area -> nation -> UK). This shifts the level while preserving the 2021
# within-area pattern. Additive: writes adj2023_* columns and leaves adj_* as-is,
# so the live map is unchanged until the newer file is present and we rebuild.
SCALE_YEAR = "2023"
# The GBD 2023 download is one file per (year, sex); target the year+Both slice.
# (The 2021 baseline file carries "_2021_BOTH_", so it is never matched here.)
SCALE_GLOBS = (f"IHME_*PROP_ABOVE_*_{SCALE_YEAR}_BOTH_*.CSV",
               f"IHME_*PROP_ABOVE_*_{SCALE_YEAR}_BOTH_*.csv")
AGE_ALIASES = {"<20", "<20 years", "0 to 19", "0-19", "0 to 19 years",
               "0-19 years"}
ADJ2023_COLS = ["adj2023_prop_pct", "adj2023_rate_per_1000", "adj2023_children",
                "scale_factor", "scale_geo", "prop2023_pct"]

# How to re-level. GBD 2023 only resolves the UK to nation level, and those
# splits are erratic and barely identified -- in 2023, England reads 0.03% and
# Wales 21.0% above 5 ug/dL (Wales CI 5-48%), vs 1.58% / 4.71% in 2021. Treating
# them as a spatial signal would scale Wales UP 4.5x and England to ~zero. So we
# re-level by the UK NATIONAL decline only (a single factor, 1.06%/1.81% = 0.586)
# and keep the 2021 within-UK pattern -- which is exactly why the 2021 round is
# used sub-nationally in the first place. Flip to "best_geography" only if a
# future round publishes credible UK sub-national lead estimates.
SCALE_MODE = "uk_national"          # "uk_national" | "best_geography"
SCALE_ANCHOR = "United Kingdom"


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load_ihme_props():
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


def fit_weights(rows, prop, c2c):
    """OLS of IHME % on housing + IMD across England county/UA units.
    Returns intercept + slopes, applied as the within-area risk weight."""
    agg = defaultdict(lambda: {"cp": 0.0, "pre1945": 0.0, "imd": 0.0})
    for r in rows:
        if r["nation"] != "England":
            continue
        county = c2c.get(r["PCON24NM"])
        if county not in prop:
            continue
        cp = r["_cp"]
        a = agg[county]
        a["cp"] += cp
        if r["_pre1945"] is not None:
            a["pre1945"] += r["_pre1945"] * cp
        if r["_imd"] is not None:
            a["imd"] += r["_imd"] * cp
    y, X = [], []
    for county, a in agg.items():
        if a["cp"] == 0:
            continue
        y.append(prop[county] * 100)
        X.append([1.0, a["pre1945"] / a["cp"], a["imd"] / a["cp"]])
    y, X = np.array(y), np.array(X)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    ss_res = np.sum((y - X @ beta) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    return {"b0": beta[0], "pre1945": beta[1], "imd": beta[2],
            "r2": 1 - ss_res / ss_tot, "n": len(y)}


def load_scale_props():
    """Load a newer-round 'proportion above 5 ug/dL' national file, if present.

    Returns (props_by_location, filename): proportions (as fractions) for
    SCALE_YEAR, ages 0-19, sex Both. ({}, None) when no such file is in the dir.
    The 2021 baseline file is not matched (its name carries 2021, not 2023)."""
    matches = []
    for g in SCALE_GLOBS:
        matches += glob.glob(g)
    matches = sorted(dict.fromkeys(matches))   # latest release (Y-date) sorts last
    if not matches:
        return {}, None
    fn = matches[-1]
    props, ages_seen = {}, set()
    with open(fn, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r.get("measure_name") != "Proportion":
                continue
            if r.get("sex") not in (None, "", "Both"):
                continue
            if r.get("year_id") not in (None, "", SCALE_YEAR):
                continue
            ages_seen.add(r.get("age_group_name"))
            if r.get("age_group_name") not in AGE_ALIASES:
                continue
            v = fnum(r.get("mean"))
            if v is not None:
                props[r["location_name"]] = v
    if not props:
        print(f"WARNING: {fn} parsed 0 matching rows (year {SCALE_YEAR}, "
              f"ages 0-19, sex Both). Age labels present: "
              f"{sorted(a for a in ages_seen if a)} -- check the codebook and "
              f"extend AGE_ALIASES / SCALE_YEAR if the schema differs.")
    return props, fn


def main():
    prop = load_ihme_props()
    c2c = load_constituency_to_county()

    with open("constituency_profile.csv", newline="") as f:
        reader = csv.DictReader(f)
        base_fields = [c for c in reader.fieldnames
                       if c not in ADJ_COLS and c not in ADJ2023_COLS]
        rows = list(reader)

    for r in rows:
        name = r["PCON24NM"]
        r["_cp"] = fnum(r["child_pop_0_19"]) or 0.0
        r["_pre1945"] = fnum(r["pct_pre_1945"])
        r["_imd"] = fnum(r["imd_score"])
        area = c2c.get(name, r["nation"])
        if area not in prop:
            area = r["nation"] if r["nation"] in prop else "United Kingdom"
        r["_area"] = area
        r["_p"] = prop.get(area)

    # Impute missing predictors with area mean (cp-weighted), then nation, then global.
    def means_by(keyfn):
        num = defaultdict(lambda: defaultdict(float))
        den = defaultdict(lambda: defaultdict(float))
        for r in rows:
            for p in PREDICTORS:
                v = r["_" + p]
                if v is not None:
                    num[keyfn(r)][p] += v * r["_cp"]
                    den[keyfn(r)][p] += r["_cp"]
        return num, den
    area_num, area_den = means_by(lambda r: r["_area"])
    nat_num, nat_den = means_by(lambda r: r["nation"])
    g_num, g_den = defaultdict(float), defaultdict(float)
    for r in rows:
        for p in PREDICTORS:
            if r["_" + p] is not None:
                g_num[p] += r["_" + p] * r["_cp"]; g_den[p] += r["_cp"]

    def impute(r, p):
        if r["_" + p] is not None:
            return r["_" + p]
        for num, den, k in ((area_num, area_den, r["_area"]),
                            (nat_num, nat_den, r["nation"])):
            if den[k][p] > 0:
                return num[k][p] / den[k][p]
        return g_num[p] / g_den[p] if g_den[p] else 0.0

    coef = fit_weights(rows, prop, c2c)
    print(f"UK-fitted weights (England county/UA, n={coef['n']}, R2={coef['r2']:.3f}):")
    print(f"  intercept {coef['b0']:+.4f}  pre1945 {coef['pre1945']:+.5f}  "
          f"imd {coef['imd']:+.5f}\n")

    for r in rows:
        risk = (coef["b0"] + coef["pre1945"] * impute(r, "pre1945")
                + coef["imd"] * impute(r, "imd"))
        r["_risk"] = max(risk, 0.1)

    # Within each baseline area, allocate the area's IHME total ∝ risk × child pop.
    gnum, gden = defaultdict(float), defaultdict(float)
    for r in rows:
        if r["_p"] is not None and r["_cp"] > 0:
            gnum[r["_area"]] += r["_risk"] * r["_cp"]
            gden[r["_area"]] += r["_cp"]

    for r in rows:
        if r["_p"] is None or r["_cp"] <= 0 or gnum[r["_area"]] == 0:
            for c in ADJ_COLS:
                r[c] = ""
            continue
        wmean_risk = gnum[r["_area"]] / gden[r["_area"]]
        adj_pct = r["_p"] * 100 * (r["_risk"] / wmean_risk)   # percent
        r["adj_prop_pct"] = round(adj_pct, 2)
        r["adj_rate_per_1000"] = round(adj_pct * 10, 1)
        r["adj_children"] = int(round(adj_pct / 100 * r["_cp"]))
        r["baseline_area"] = r["_area"]
        r["baseline_ihme_pct"] = round(r["_p"] * 100, 2)

    # Optional: re-level the 2021 baselines to a newer GBD round, if a newer
    # national "proportion above 5" file is present. Scales each area by
    # new/2021 at the finest geography in both files; preserves within-area shape.
    scale_props, scale_fn = load_scale_props()
    scaled_any = False
    if scale_props:
        def area_factor(r):
            geos = ((SCALE_ANCHOR,) if SCALE_MODE == "uk_national"
                    else (r["_area"], r["nation"], "United Kingdom"))
            for geo in geos:
                p_new, p_old = scale_props.get(geo), prop.get(geo)
                if p_new is not None and p_old not in (None, 0):
                    return p_new / p_old, geo, p_new
            return None, None, None
        factors_by_geo = {}
        for r in rows:
            if r.get("adj_prop_pct") in (None, ""):
                for c in ADJ2023_COLS:
                    r[c] = ""
                continue
            f_, geo, p_new = area_factor(r)
            if f_ is None:
                for c in ADJ2023_COLS:
                    r[c] = ""
                continue
            ap = r["adj_prop_pct"] * f_
            r["adj2023_prop_pct"] = round(ap, 2)
            r["adj2023_rate_per_1000"] = round(ap * 10, 1)
            r["adj2023_children"] = int(round(ap / 100 * r["_cp"]))
            r["scale_factor"] = round(f_, 4)
            r["scale_geo"] = geo
            r["prop2023_pct"] = round(p_new * 100, 3)
            factors_by_geo[geo] = round(f_, 4)
            scaled_any = True
        print(f"\nRe-leveled to {SCALE_YEAR} from {scale_fn} "
              f"({len(scale_props)} locations).")
        print(f"  scale factors (new/2021) by geography: {factors_by_geo}")
    else:
        print(f"\nNo {SCALE_YEAR} 'proportion above 5' national file found "
              f"(looked for {SCALE_GLOBS[0]} etc.). adj2023_* not written -- the "
              f"map keeps the GBD-2021 levels. Drop the GBD {SCALE_YEAR} "
              f"'Proportion Above 50' national CSV in here and rerun to re-level.")

    for r in rows:
        for k in [k for k in r if k.startswith("_")]:
            del r[k]

    out_fields = base_fields + ADJ_COLS + (ADJ2023_COLS if scaled_any else [])
    with open("constituency_profile.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out_fields)
        w.writeheader()
        w.writerows(rows)

    _sanity(rows)


def _sanity(rows):
    from collections import Counter
    data = [r for r in rows if r.get("adj_rate_per_1000") not in (None, "")]
    print(f"Wrote adjusted columns for {len(data)}/{len(rows)} constituencies.\n")
    for nat in NATIONS:
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

    data23 = [r for r in rows if r.get("adj2023_rate_per_1000") not in (None, "")]
    if data23:
        print(f"\n  --- re-leveled to {SCALE_YEAR} (nation means per 1,000) ---")
        for nat in NATIONS:
            sub = [r for r in data23 if r["nation"] == nat]
            if not sub:
                continue
            den = sum(fnum(r["child_pop_0_19"]) for r in sub)
            new = sum(r["adj2023_rate_per_1000"] * fnum(r["child_pop_0_19"])
                      for r in sub) / den
            old = sum(r["adj_rate_per_1000"] * fnum(r["child_pop_0_19"])
                      for r in sub) / den
            print(f"  {nat:18} {new:5.1f}  (GBD-2021 level was {old:5.1f})")


if __name__ == "__main__":
    main()
