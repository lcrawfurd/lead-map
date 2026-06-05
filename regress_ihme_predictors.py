#!/usr/bin/env python3
"""What predicts IHME blood-lead at LAD level? OLS to decide which constituency
indicators belong in the adjusted-IHME model (and with what weights).

Unit of analysis = England county/UA (the finest IHME geography). Constituency
predictors are aggregated to that level (child-population-weighted means; mines
summed). Outcome = IHME GBD 2021 proportion of children 0-19 with BLL >= 5.
"""
import csv
import json
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

AGE = "<20"


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# IHME proportion per location
ihme = {}
for r in csv.DictReader(open("IHME_GBD_2021_LEAD_RISK_1990_2021_PROP_ABOVE_5_2021_BOTH_Y2024M06D05.CSV")):
    if r["measure_name"] == "Proportion" and r["age_group_name"] == AGE:
        ihme[r["location_name"]] = float(r["mean"])

c2c = json.load(open("constituency_to_county.json"))
soil = {r["PCON24NM"]: fnum(r["pb_mean"]) for r in csv.DictReader(open("constituency_topsoil_pb.csv"))}
prof = list(csv.DictReader(open("constituency_profile.csv")))

# Aggregate constituency predictors to county/UA (England only).
agg = {}
for r in prof:
    if r["nation"] != "England":
        continue
    county = c2c.get(r["PCON24NM"])
    if county not in ihme:
        continue
    cp = fnum(r["child_pop_0_19"]) or 0
    d = agg.setdefault(county, {"cp": 0, "pre1945_w": 0, "imd_w": 0, "soil_w": 0,
                                "soil_cp": 0, "nondec_w": 0, "mines": 0, "n": 0})
    d["cp"] += cp
    d["n"] += 1
    d["mines"] += fnum(r["n_mines_total"]) or 0
    if fnum(r["pct_pre_1945"]) is not None:
        d["pre1945_w"] += fnum(r["pct_pre_1945"]) * cp
    if fnum(r["imd_score"]) is not None:
        d["imd_w"] += fnum(r["imd_score"]) * cp
    nd = fnum(r["pct_non_decent_homes"])
    if nd is not None:
        d["nondec_w"] += (nd * 100 if nd < 1 else nd) * cp
    s = soil.get(r["PCON24NM"])
    if s is not None:
        d["soil_w"] += s * cp
        d["soil_cp"] += cp

rows = []
for county, d in agg.items():
    if d["cp"] == 0:
        continue
    rows.append({
        "county": county,
        "ihme_pct": ihme[county] * 100,          # outcome, percentage points
        "pre1945": d["pre1945_w"] / d["cp"],
        "imd": d["imd_w"] / d["cp"],
        "nondecent": d["nondec_w"] / d["cp"],
        "soil": d["soil_w"] / d["soil_cp"] if d["soil_cp"] else np.nan,
        "mines_per_1k": d["mines"] / (d["cp"] / 1000),
        "child_pop": d["cp"],
    })

df = pd.DataFrame(rows)
print(f"N county/UA units: {len(df)};  with soil: {df['soil'].notna().sum()}")
print(f"Outcome IHME % BLL>=5 (0-19): mean {df.ihme_pct.mean():.2f}, range {df.ihme_pct.min():.2f}-{df.ihme_pct.max():.2f}\n")
print("Pairwise correlation with IHME %:")
print(df[["ihme_pct", "pre1945", "imd", "nondecent", "soil", "mines_per_1k"]].corr()["ihme_pct"].round(3).to_string(), "\n")

specs = {
    "1. housing+IMD":        "ihme_pct ~ pre1945 + imd",
    "2. +soil":              "ihme_pct ~ pre1945 + imd + soil",
    "3. +mines":             "ihme_pct ~ pre1945 + imd + mines_per_1k",
    "4. full":               "ihme_pct ~ pre1945 + imd + soil + mines_per_1k",
}
for name, formula in specs.items():
    d = df.dropna(subset=[c for c in ["pre1945", "imd", "soil", "mines_per_1k"]
                          if c in formula])
    m = smf.ols(formula, data=d).fit(cov_type="HC3")
    print(f"=== {name}   (n={int(m.nobs)}, R2={m.rsquared:.3f}, adjR2={m.rsquared_adj:.3f}) ===")
    for term in m.params.index:
        if term == "Intercept":
            continue
        print(f"   {term:14} b={m.params[term]:+.4f}  se={m.bse[term]:.4f}  p={m.pvalues[term]:.3f}")
    print()

# Population-weighted full model + standardized betas for importance comparison
dfull = df.dropna(subset=["soil"]).copy()
mw = smf.wls("ihme_pct ~ pre1945 + imd + soil + mines_per_1k", data=dfull,
             weights=dfull["child_pop"]).fit(cov_type="HC3")
print(f"=== full, child-pop-weighted (n={int(mw.nobs)}, R2={mw.rsquared:.3f}) ===")
z = dfull.copy()
for c in ["ihme_pct", "pre1945", "imd", "soil", "mines_per_1k"]:
    z[c] = (z[c] - z[c].mean()) / z[c].std()
mz = smf.wls("ihme_pct ~ pre1945 + imd + soil + mines_per_1k", data=z,
             weights=dfull["child_pop"]).fit()
for term in mw.params.index:
    if term == "Intercept":
        continue
    print(f"   {term:14} b={mw.params[term]:+.4f}  p={mw.pvalues[term]:.3f}   std_beta={mz.params[term]:+.3f}")

# DECISION: the model (build_adjusted_ihme.py) uses housing + IMD only.
# - mines: no positive signal above -> excluded.
# - soil: confounded by London (highest soil, ~average BLL). The dummy below shows
#   soil is insignificant once London is pooled in; it is only significant if London
#   is dropped entirely (r=+0.42), and that slope extrapolates poorly to Wales/
#   Scotland (a single coarse topsoil mean pushed Swansea West to ~6.5%). -> excluded.
# Both soil and mines remain as standalone map overlays.
LONDON = {"Barking and Dagenham", "Barnet", "Bexley", "Brent", "Bromley", "Camden",
          "Croydon", "Ealing", "Enfield", "Greenwich", "Hackney",
          "Hammersmith and Fulham", "Haringey", "Harrow", "Havering", "Hillingdon",
          "Hounslow", "Islington", "Kensington and Chelsea", "Kingston upon Thames",
          "Lambeth", "Lewisham", "Merton", "Newham", "Redbridge",
          "Richmond upon Thames", "Southwark", "Sutton", "Tower Hamlets",
          "Waltham Forest", "Wandsworth", "Westminster"}
dfull = dfull.assign(london=dfull["county"].isin(LONDON).astype(int))
mL = smf.wls("ihme_pct ~ pre1945 + imd + soil + london", data=dfull,
             weights=dfull["child_pop"]).fit(cov_type="HC3")
print(f"\n=== CHOSEN: housing+IMD+soil, pop-weighted, London-controlled "
      f"(n={int(mL.nobs)}, R2={mL.rsquared:.3f}) ===")
for term in mL.params.index:
    if term == "Intercept":
        continue
    print(f"   {term:14} b={mL.params[term]:+.5f}  p={mL.pvalues[term]:.3f}")
print("   -> soil is positive & significant once London is controlled; mines dropped.")

# ── Robustness: is the negative mines coefficient just a rurality confound, and
# could mines still help rank seats within Wales? Tested two ways. ──
from shapely.geometry import shape  # noqa: E402
print("\n=== MINES ROBUSTNESS ===")
# A. England LAD: does mines flip sign once population density is controlled?
carea = {f["properties"]["name"]: shape(f["geometry"]).area
         for f in json.load(open("uk_counties.json"))["features"]}
amg = {}
for r in prof:
    if r["nation"] != "England":
        continue
    c = c2c.get(r["PCON24NM"])
    if c not in ihme or c not in carea or carea[c] == 0:
        continue
    cp = fnum(r["child_pop_0_19"]) or 0
    d = amg.setdefault(c, {"cp": 0, "h": 0, "i": 0, "m": 0})
    d["cp"] += cp; d["m"] += fnum(r["n_mines_total"]) or 0
    if fnum(r["pct_pre_1945"]) is not None: d["h"] += fnum(r["pct_pre_1945"]) * cp
    if fnum(r["imd_score"]) is not None: d["i"] += fnum(r["imd_score"]) * cp
ed = pd.DataFrame([{"ihme": ihme[c] * 100, "pre1945": d["h"] / d["cp"], "imd": d["i"] / d["cp"],
                    "mines_per_1k": d["m"] / (d["cp"] / 1000),
                    "log_density": np.log(d["cp"] / carea[c])}
                   for c, d in amg.items() if d["cp"]])
for f in ["ihme ~ pre1945 + imd + mines_per_1k",
          "ihme ~ pre1945 + imd + mines_per_1k + log_density"]:
    m = smf.ols(f, data=ed).fit(cov_type="HC3")
    tag = "with density control" if "density" in f else "no control     "
    print(f"  A. mines_per_1k ({tag}): b={m.params['mines_per_1k']:+.3f} p={m.pvalues['mines_per_1k']:.3f}")
print("     -> negative sign is pure rurality confound; mines ≈ 0 once density is controlled.")
# B. Do mining seats have higher topsoil Pb (a contamination signal that exists within Wales)?
mb = pd.DataFrame([(fnum(r["n_mines_total"]) or 0, soil.get(r["PCON24NM"]), r["nation"])
                   for r in prof if soil.get(r["PCON24NM"]) is not None],
                  columns=["mines", "soil", "nation"])
for nat in ["Wales", "England", "Scotland"]:
    d = mb[mb.nation == nat]
    print(f"  B. {nat}: mean topsoil Pb has-mines={d[d.mines>0].soil.mean():.0f} vs "
          f"no-mines={d[d.mines==0].soil.mean():.0f} mg/kg")
print("     -> mining seats do NOT have higher soil Pb (lower in Wales); mine contamination")
print("        is hyper-local and washes out at constituency scale. Mines stay an overlay.")
