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


def main():
    prop = load_ihme_props()
    c2c = load_constituency_to_county()

    with open("constituency_profile.csv", newline="") as f:
        reader = csv.DictReader(f)
        base_fields = [c for c in reader.fieldnames if c not in ADJ_COLS]
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

    for r in rows:
        for k in [k for k in r if k.startswith("_")]:
            del r[k]

    out_fields = base_fields + ADJ_COLS
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


if __name__ == "__main__":
    main()
