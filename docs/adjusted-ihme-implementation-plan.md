# Adjusted-IHME model — Implementation Plan

> Executed inline this session. Verification gates replace pytest TDD (no test
> framework in this static-site repo). Spec: `docs/adjusted-ihme-methodology.md`.

**Goal:** Replace the two contradictory blood-lead numbers with one
best-data-per-area "adjusted IHME" figure, used by the map, rankings and profile.

**Architecture:** A committed Python build script regenerates
`constituency_profile.csv` with adjusted columns; `constituencies.html` gains an
"Adjusted IHME" indicator that becomes the default and feeds rankings + profile,
with raw IHME kept as a toggle.

**Tech stack:** Python 3 stdlib (csv/json/re) for the build; vanilla JS +
Leaflet + PapaParse in `constituencies.html`.

---

### Task 1: Build script `build_adjusted_ihme.py`

**Files:** Create `build_adjusted_ihme.py`; reads `IHME_*PROP_ABOVE_5*.CSV`,
`constituencies.html` (for `CONSTITUENCY_TO_COUNTY`), `constituency_profile.csv`;
rewrites `constituency_profile.csv` in place.

Logic:
- Load IHME `Proportion`, `age_group_name=="<20"` → `prop[location_name]`.
- Extract `CONSTITUENCY_TO_COUNTY` JSON from `constituencies.html` via regex.
- For each profile row with numeric `rate_per_1000_bl_5plus` + `child_pop_0_19`:
  baseline area = `CONSTITUENCY_TO_COUNTY[name]` for England, else `nation`.
  `p_area = prop[area]` (fallback nation → United Kingdom; assert no England
  fallbacks).
- Per area, child-pop-weighted mean of `rate_per_1000`; then
  `adj_rate = p_area*1000 * rate/wmean`; `adj_children = round(adj_rate/1000*cp)`;
  `adj_prop_pct = adj_rate/10`.
- Write new columns: `adj_rate_per_1000`, `adj_children`, `adj_prop_pct`,
  `baseline_area`, `baseline_ihme_pct`. Preserve all existing columns/order.
- Print sanity block: nation means, top 10, worst-100 nation split, England spread.

**Verify (gate):** `python3 build_adjusted_ihme.py` prints England≈16.1,
Wales≈47.1, Scotland≈32.3, NI≈34.3 per 1,000; top seats Welsh (~50); England
spread ~9–35; worst-100 ≈ {Wales 31, Scotland 47, NI 17, England 5}; no England
baseline fallbacks. Re-running is idempotent (columns not duplicated).

- [ ] Write script · run · confirm sanity block · `git add` script + regenerated CSV · commit

---

### Task 2: New "Adjusted IHME" indicator + default (`constituencies.html`)

**Files:** Modify `constituencies.html` (INDICATORS map ~291; `selectedIndicator`
default ~286; `getDataForFeature` ~504; getColor/fmt ~352-368; age-selector
toggle ~962).

- Add `INDICATORS.bll_adj`: label "Adjusted IHME (modelled BLL ≥ 5)", legendTitle
  "% children BLL ≥ 5 (adjusted)", subtitle naming the method, colours/breaks =
  the existing `bll` ramp `[0,1,2,3,4,5]`, source "IHME GBD 2021 + VOA/IMD model".
- Relabel existing `bll` → "Blood lead ≥ 5 (raw IHME)" so the toggle reads clearly.
- `selectedIndicator = 'bll_adj'` default.
- In `getDataForFeature`, handle `bll_adj`: read `profileData[name].adj_prop_pct`
  → `{ data: { mean: pct }, source: 'constituency' }` (value already a %, so it
  must bypass the `* dataScale` path).
- `getColor`/`fmtVal`/`fmtPct`: treat `bll_adj` like a percentage already in %
  units (no `*dataScale`). Audit each `selectedIndicator === 'bll'` branch and
  decide whether `bll_adj` shares it.
- Age selector visibility (~962): show only for raw `bll`; hide for `bll_adj`.

**Verify (gate):** open `constituencies.html` locally; default layer is Adjusted
IHME; Wales uniformly higher band, England varied; hover %s match the CSV
(Blackpool South ≈3.5%, a Cardiff seat ≈5.0%); switching to "raw IHME" restores
the old flat-Wales view + age selector.

- [ ] Edit · verify in browser (screenshot) · commit

---

### Task 3: Rankings table + profile panel use the adjusted figure

**Files:** Modify `constituencies.html` rankings builder + profile panel +
table intro text (~241).

- Rankings: headline rate column = `adj_rate_per_1000` (label "Modelled rate /1,000,
  adjusted"); affected-children column = `adj_children`; default sort = adjusted
  rate desc. Keep CSV export including adjusted columns.
- Profile panel: show adjusted estimate + `baseline_ihme_pct` ("nation/LAD IHME
  baseline") so the provenance is visible.
- Update intro (~241) to describe the adjusted method.

**Verify (gate):** Rankings open sorted with Welsh/Scottish seats on top, Blackpool
mid-table; numbers equal the CSV; CSV export contains adjusted columns; clicking a
row still flies to the seat and the profile shows matching numbers.

- [ ] Edit · verify · commit

---

### Task 4: Docs — `sources.html` + `README.md`

**Files:** Modify `sources.html` (methodology block) + `README.md` (Indicators).

- Rewrite the "Modelled children with BLL ≥ 5" section for best-data-per-area:
  England LAD baselines, W/S/NI nation baselines, within-area housing+IMD
  re-allocation; restate the three caveats from the spec; reference
  `build_adjusted_ihme.py`.
- README: note Adjusted IHME is the default layer, raw IHME a toggle.

**Verify (gate):** sources page renders; text matches the implemented method; no
stale "national total (~352,000)" allocation wording remains as the live method.

- [ ] Edit · verify · commit

---

### Task 5: Final review & handoff

- [ ] Diff review vs spec; full walkthrough of the local page (default layer,
  toggle to raw IHME, age selector behaviour, rankings sort, profile, CSV export).
- [ ] Screenshot adjusted vs raw map for Lee.
- [ ] Summarise; **do not push to the live branch** — await Lee's go-ahead to
  open a PR / merge into `claude/interactive-uk-lead-map-hpBzB`.
