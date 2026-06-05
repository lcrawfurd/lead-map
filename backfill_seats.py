#!/usr/bin/env python3
"""Back-fill three 2024 seats the upstream name-based join missed.

Montgomeryshire and Glyndwr, Bridlington and The Wolds, and South Holland and The
Deepings came through the original profile build as near-empty stubs (only the
spatially-joined mines columns populated) because their newly-drawn 2024 names did
not match the population/IMD/MP source tables. The universal casualty was child
population, which drops a seat from the adjusted-IHME model entirely.

This fills the fields needed to put them back on the map. child_pop_0_19 is an
ESTIMATE: 0-19 ≈ (share_0_15 + 4/9 × share_16_24) × total population, using the
age bands published by the Local Intelligence Hub / House of Commons Library
(mySociety; May 2024) — the same family of source as the project's IMD. It is
within a few percent and clearly flagged here. IMD and housing are left blank and
imputed to the area/nation mean by build_adjusted_ihme.py.

Run BEFORE build_adjusted_ihme.py. Only fills blank cells; idempotent.
"""
import csv

# PCON24NM -> fields to fill. child_pop_0_19 estimated as described above.
BACKFILL = {
    "Montgomeryshire and Glyndwr": {        # total 97,800; 0-15 17.1%, 16-24 8.9%
        "child_pop_0_19": "20600.0",
        "la_name": "Powys",
        "mp_name": "Steve Witherden",
        "mp_party": "Labour",
    },
    "Bridlington and The Wolds": {           # total 92,600; 0-15 15.0%, 16-24 7.5%
        "child_pop_0_19": "17000.0",
        "la_name": "East Riding of Yorkshire",
    },
    "South Holland and The Deepings": {      # total 109,000; 0-15 17.0%, 16-24 8.5%
        "child_pop_0_19": "22600.0",
        "la_name": "South Holland",
    },
}


def main():
    path = "constituency_profile.csv"
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)

    filled = 0
    for r in rows:
        ov = BACKFILL.get(r["PCON24NM"])
        if not ov:
            continue
        for k, v in ov.items():
            if r.get(k, "") in ("", None):   # only fill blanks
                r[k] = v
                filled += 1

    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"Back-filled {filled} cells across {len(BACKFILL)} seats "
          "(child_pop_0_19 is an estimate — see module docstring).")


if __name__ == "__main__":
    main()
