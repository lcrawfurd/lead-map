# Adjusted-IHME constituency model — design & methodology

**Date:** 2026-06-05
**Status:** implemented and live
**Author:** Lee Crawfurd (with Claude Code)

## Problem

The constituency map currently shows two different blood-lead numbers that tell
contradictory stories, which is hard to communicate:

1. **Map default layer ("Blood lead ≥ 5") = raw IHME GBD 2021.** IHME only
   resolves to LAD level in England (~1.6% of children, with real local
   variation). Wales, Scotland and Northern Ireland have **no sub-national
   estimate**, so every constituency is painted the single *nation* figure —
   Wales 4.7%, NI 3.4%, Scotland 3.2% vs England 1.6%. Result: all of Wales is
   one flat dark-red block → "Wales looks worst."
2. **Rankings table = the modelled `rate_per_1000`.** The old model took the
   single **UK total** (~352,000 children 0–19) and redistributed it by pre-1945
   housing share and IMD. This **discards the country baselines**, so Wales comes
   out ≈ England (~22/1,000) and deprived English cities (Blackpool, Bradford;
   Barking/East Ham by count) top the table → "English cities / London worst."

The two views use different data and disagree about Wales. We consolidate to a
single "adjusted IHME" figure used by **both** the map and the rankings.

## Decision

**Best data per area.** Use the finest IHME geography available for each area as
the baseline, then redistribute *within* that area by the existing housing-age +
IMD risk weights:

- **England:** baseline = the constituency's parent **LAD/county** IHME value
  (preserves England's genuine local variation).
- **Wales / Scotland / Northern Ireland:** baseline = the **nation** IHME value
  (no sub-national data exists).

Rejected alternatives: (A) nation baselines for all four nations — flattens
England into one colour; (C) keep the old housing+IMD model on the map and
downplay IHME — not an "adjusted IHME" figure, and ignores the genuine Welsh
signal.

## Model

**Within-area risk weight — UK-fitted regression.** Rather than import US odds
ratios, the weight is each constituency's *predicted* IHME blood-lead level from an
OLS fitted on the England county/UA units:

```
ihme_pct ~ pre1945_housing + imd_score          (n = 150, R² ≈ 0.16)
```

Fitted: pre-1945 housing **+0.0079**, IMD score **+0.0179** — both positive. Missing
predictors are imputed to the area/nation mean; predicted risk is floored at 0.1.

**Predictors tested and excluded** (see `regress_ihme_predictors.py`): *historic
mines* — the raw negative coefficient is a pure rurality confound (it vanishes to
≈0, p≈0.95, once population density is controlled), and mining seats do not even
have higher topsoil Pb (lower in Wales) — mine contamination is too hyper-local to
register at constituency scale;
*topsoil Pb* — predicts blood lead across England only **once London is dropped**
from the fit (r = +0.42 ex-London vs ≈0 pooled: London has the highest soil Pb but
average modelled BLL), and applying that slope extrapolates poorly to Wales/Scotland
(e.g. it pushed Swansea West to 6.5% off one coarse topsoil mean). Both stay as
standalone overlay layers instead.

**Allocation (preserves area totals).** For each baseline area *A* — an English
county/UA, or a whole devolved nation — with IHME proportion `p_A`:

1. each constituency *i* gets `risk_i` = predicted BLL%;
2. allocate *A*'s child total proportionally:
   `adj_prop_i = p_A × risk_i / Σ_w(risk over A)`, child-population-weighted.

So the child-population-weighted mean of `adj_prop_i` over *A* equals `p_A` — this
**re-levels** the model onto IHME baselines rather than inflating it. The cross-area
level is IHME; the within-area distribution is the fitted risk.

IHME age group: **0–19** (`age_group_name == "<20"`, `measure_name == "Proportion"`).

### Expected output

Nation means (per 1,000): England **16.7**, Wales **47.1**, Scotland **32.3**,
NI **34.3** (IHME-anchored, so stable). Within-nation spread is coherent (Wales
42–50, Scotland 28–41); top seats are deprived Welsh valleys/cities (Cardiff West,
Llanelli, Blaenau Gwent, Pontypridd, Merthyr). Worst-100 split ≈ Wales 31 /
Scotland 47 / NI 15 / England 7.
Map and rankings agree.

## Changes

- **`build_adjusted_ihme.py`** (new, committed): fits the UK regression weights
  (housing + IMD) and writes the new columns from the IHME CSV + constituency→county
  mapping. **`regress_ihme_predictors.py`**: standalone regression diagnostics
  (statsmodels) that justify the predictor choice (incl. testing soil & mines).
  Restores reproducibility (the original `lead_exposure_model_FINAL.py` is not in
  the repo).
- **`constituency_profile.csv`**: add `adj_rate_per_1000`, `adj_children`,
  `adj_prop_pct`, `baseline_area`, `baseline_ihme_pct`.
- **`constituencies.html`**:
  - New **"Adjusted IHME (modelled)"** indicator becomes the **map default**,
    the **rankings** number, and the **profile-panel** number — the single
    consolidated figure.
  - **Raw IHME kept as a selectable layer** for transparency.
  - The old uniform-baseline `rate_per_1000` is retired from the UI (it is the
    duplicate that caused the confusion); the column stays in the CSV.
  - Adjusted layer is fixed to ages 0–19, so the age selector hides for it (as
    the housing layers already do). Raw-IHME layer keeps the age selector.
  - Display: **%** on the map (reuse the 0–5% colour ramp; values land
    ~0.9–5.1%); **per-1,000 + absolute children** in rankings/profile; default
    table sort = adjusted rate.
- **`sources.html`** + **`README.md`**: methodology text updated.

## Caveats to print on the page

- Wales/Scotland/NI have **no sub-national IHME**, so their *within-nation*
  variation comes only from housing/IMD — those nations will still look fairly
  even on the map, but now at the correct level.
- The **cross-nation gradient inherits IHME's uncertainty**: the headline that
  Wales ≈ 3× England rests on IHME's modelled nation estimate from sparse UK
  blood-lead data. The figure is illustrative, not a clinical estimate.
- Scotland has only pre-1945 housing (SHCS, LA-level) and NI applies housing
  uniformly, so within-nation redistribution there is driven mainly by IMD.

## Out of scope

Changing the standalone housing/mines/topsoil overlay layers; the global and
county/UA (`index.html`) maps.

## Known data gaps

Three newly-drawn 2024 seats came through the upstream profile build as near-empty
stubs (the name-based join to population/IMD/MP tables missed them; only the
spatially-joined mines attached): **Montgomeryshire and Glyndwr**, **Bridlington and
The Wolds**, **South Holland and The Deepings**. `backfill_seats.py` restores them —
child population is **estimated** from Local Intelligence Hub / House of Commons
Library age bands × total population (within a few %); IMD and housing remain blank
and are imputed to the area/nation mean. A code-based (GSS) join upstream would
remove the need for this.

## Re-leveling to GBD 2023 (2026-06-12)

GBD 2023 (released Oct 2025) lowered UK childhood lead, but it no longer resolves
the UK sub-nationally in a usable way, so the 2021 round still supplies the
**pattern** and only the **level** is updated.

- **Why not per-nation.** GBD 2023's UK nation splits are erratic and barely
  identified: ages 0–19 above 5 µg/dL read **England 0.03%** and **Wales 21.0%**
  (Wales CI 5–48%), against 1.58% / 4.71% in 2021. Re-leveling per-nation would
  scale Wales *up* 4.5× and England to ≈0 — not a credible spatial signal.
- **What we do.** Scale every area by the single **UK national** ratio
  `GBD 2023 / GBD 2021 = 1.0615% / 1.8112% = 0.5861`. This lowers the whole map
  ~41% and preserves the entire 2021 within-UK pattern (England county variation
  and the cross-nation gradient). Nation means fall to (per 1,000): England 9.8,
  Wales 27.6, Scotland 18.9, NI 20.1 (from 16.7 / 47.1 / 32.3 / 34.3). The top of
  the table is unchanged (deprived Welsh seats), now ≤ 2.94% rather than ≤ 5.0%.
- **Mechanism.** `build_adjusted_ihme.py` reads the GBD 2023 "Proportion Above 50"
  national CSV (`IHME_*PROP_ABOVE_*_2023_BOTH_*.CSV`) and writes additive
  `adj2023_*` columns plus `scale_factor` / `scale_geo`; the original GBD-2021
  `adj_*` columns are left intact. `SCALE_MODE` (`uk_national` | `best_geography`)
  controls whether the factor is UK-wide or per-area — set to `uk_national` for the
  reason above. `constituencies.html` reads `adj2023_*` when present (falling back
  to `adj_*`) and keeps the GBD-2021 figures under `adj2021_*`. Drop a future
  round's file in and rerun to re-level again.

Source: IHME GBD 2023 — Lead Exposure Estimates 1990–2023, Proportion above
50 µg/L, ages 0–19, year 2023, sex Both.

## Update log

- 2026-06-12: re-leveled the headline figure to GBD 2023 by the UK national ratio
  (×0.586); kept the 2021 sub-national pattern because GBD 2023's UK nation splits
  are not usable (England 0.03%, Wales 21%). See the section above and
  `build_adjusted_ihme.py` (`SCALE_MODE`, `adj2023_*` columns).
- 2026-06-05: within-area weights switched from imported US odds ratios to a
  UK-fitted regression on IHME (housing + IMD). Topsoil Pb and historic mines were
  tested as predictors and excluded — mines no signal; soil predicts BLL only
  ex-London and extrapolates poorly (Swansea West outlier). Both kept as overlays.
  See `regress_ihme_predictors.py`.
