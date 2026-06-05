# Adjusted-IHME constituency model — design & methodology

**Date:** 2026-06-05
**Status:** approved design, pending implementation
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

## Model (one formula)

For each baseline area *A* (an English LAD/county, or a whole devolved nation):

1. IHME gives area *A* a proportion `p_A` of children 0–19 with BLL ≥ 5, hence a
   case total `cases_A = p_A × childpop_A`.
2. Each constituency *i* in *A* carries the existing relative risk weight `r_i`
   from pre-1945 housing share (OR 1.92) and IMD (OR 1.44). The current
   `rate_per_1000` column is exactly `K · r_i` for a global constant `K`, so
   **within-area ratios of `rate_per_1000` recover `r_i` exactly** — we reuse it
   as the weight rather than re-deriving the (missing) original functional form.
3. Allocate `cases_A` across the constituencies of *A* in proportion to
   `r_i × childpop_i`, then
   `adj_prop_i = allocated_cases_i / childpop_i`.

By construction the child-population-weighted mean of `adj_prop_i` over *A*
equals `p_A` (re-allocation, not inflation — no double-counting of the level).
Net effect: **the existing model's within-area ordering is unchanged; only the
cross-area level is re-anchored to IHME.**

IHME age group: **0–19** (matches `child_pop_0_19`). Both measures from
`IHME_GBD_2021_LEAD_RISK_*PROP_ABOVE_5*.CSV`, `measure_name == "Proportion"`,
`age_group_name == "<20"`.

### Expected output (prototype)

Nation means (per 1,000): England **16.1**, Wales **47.1**, Scotland **32.3**,
NI **34.3**. England retains a 9–35 spread; its worst seats (Blackpool 34.8,
Hull, South Shields, Oldham, Barking) sit just below the devolved-nation band,
so 5 English seats remain in the worst-100 (Wales 31 / Scotland 47 / NI 17 /
England 5). Map and rankings now agree.

## Changes

- **`build_adjusted_ihme.py`** (new, committed): regenerates the figure from the
  IHME CSV + constituency→county mapping + `rate_per_1000` weights and writes the
  new columns. Restores reproducibility (the original `lead_exposure_model_FINAL.py`
  is not in the repo).
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

Re-deriving risk weights from primary inputs; changing housing/mines/topsoil
layers; the global and county/UA (`index.html`) maps.
