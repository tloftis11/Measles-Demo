"""
Seed synthetic school district data for all 254 TX counties.

Each county gets 1–30 districts depending on population. District-level coverage
is drawn from a distribution centered on the county mean — ensuring the county
aggregate reproduces. High-risk counties get at least one district with very low
coverage to surface a clear drill-down story.

Run from repo root:
    uv run --project backend python scripts/seed_districts.py
"""
from __future__ import annotations
import os, sys, random
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))
os.environ.setdefault("DB_PATH", str(REPO_ROOT / "data" / "measles.duckdb"))

from db import get_connection  # noqa: E402

SCHOOL_YEAR = "2023-2024"

# Representative TX school district name suffixes by size
ISD_SUFFIXES = ["ISD", "ISD", "ISD", "CISD", "CISD", "GISD"]

# Town-name fragments used to build plausible district names
PREFIXES = [
    "West", "East", "North", "South", "Central", "Lake", "Valley",
    "Prairie", "Rim", "Mesa", "Ridge", "Creek", "River", "Plains",
    "Spring", "Flat", "Alto", "Del", "San", "New", "Old", "Fort",
]


def district_count(population: int) -> int:
    if population < 3_000:    return 1
    if population < 10_000:   return random.randint(1, 2)
    if population < 30_000:   return random.randint(2, 4)
    if population < 100_000:  return random.randint(4, 8)
    if population < 500_000:  return random.randint(8, 18)
    return random.randint(18, 35)


def make_district_name(county_name: str, idx: int, rng: random.Random) -> str:
    if idx == 0:
        return f"{county_name} {rng.choice(ISD_SUFFIXES)}"
    prefix = rng.choice(PREFIXES)
    return f"{prefix} {county_name} {rng.choice(ISD_SUFFIXES)}"


def generate_districts(
    fips: str,
    county_name: str,
    population: int,
    county_mmr: float,
    county_nonmed: float,
    county_enrollment: int,
    is_high_risk: bool,
    rng: random.Random,
) -> list[dict]:
    n = district_count(population)
    rng.seed(int(fips) * 99991 + 7)  # deterministic from fips

    districts = []
    remaining_enrollment = county_enrollment

    for i in range(n):
        is_last = i == n - 1
        # Distribute enrollment roughly evenly with noise
        if is_last:
            enroll = max(30, remaining_enrollment)
        else:
            share = rng.uniform(0.5 / n, 2.0 / n)
            enroll = max(30, int(county_enrollment * share))
            remaining_enrollment -= enroll

        # Coverage — distributed around county mean
        # High-risk counties: one anchor district significantly below county mean
        if is_high_risk and i == 0:
            mmr = round(rng.gauss(county_mmr - 8, 2.5), 1)
        elif is_high_risk and i == 1 and n > 2:
            mmr = round(rng.gauss(county_mmr - 4, 2.0), 1)
        else:
            mmr = round(rng.gauss(county_mmr + rng.uniform(-3, 5), 2.5), 1)
        mmr = max(55.0, min(99.5, mmr))

        # Non-medical exemptions inversely correlated with coverage
        gap = max(0, 95 - mmr)
        nonmed = round(rng.gauss(gap * 0.5, 1.0), 2)
        nonmed = max(0.1, min(20.0, nonmed))

        med = round(rng.uniform(0.1, 0.8), 2)

        lea_id = f"TX-{fips}-{i:02d}"
        name = make_district_name(county_name, i, rng)

        districts.append({
            "lea_id": lea_id,
            "fips": fips,
            "state_abbr": "TX",
            "district_name": name,
            "enrollment": enroll,
            "mmr_coverage_pct": mmr,
            "nonmedical_exempt_pct": nonmed,
            "medical_exempt_pct": med,
            "school_year": SCHOOL_YEAR,
            "source": "TX-synthetic",
        })

    return districts


def main():
    con = get_connection()

    # Get all counties with their coverage stats
    rows = con.execute("""
        SELECT g.fips, g.county_name, g.population,
               vc.mmr_coverage_pct, vc.nonmedical_exempt_pct, vc.enrolled,
               hs.risk_tier
        FROM geographies g
        LEFT JOIN vaccination_coverage vc
            ON vc.fips = g.fips AND vc.school_year = '2023-2024'
        LEFT JOIN hotspot_scores hs
            ON hs.fips = g.fips
            AND hs.score_date = (SELECT MAX(score_date) FROM hotspot_scores WHERE fips = g.fips)
        WHERE g.state_abbr = 'TX'
        ORDER BY g.fips
    """).fetchall()

    print(f"Generating districts for {len(rows)} counties…")

    existing_leas = {r[0] for r in con.execute("SELECT lea_id FROM school_districts").fetchall()}

    all_districts: list[dict] = []
    rng = random.Random(42)

    for fips, county_name, population, mmr, nonmed, enrolled, tier in rows:
        mmr     = mmr     or 91.0
        nonmed  = nonmed  or 2.5
        enrolled = enrolled or max(50, int((population or 5000) * 0.15))
        is_high = tier in ("CRITICAL", "HIGH")

        dists = generate_districts(fips, county_name, population or 5000,
                                   mmr, nonmed, enrolled, is_high, rng)
        for d in dists:
            if d["lea_id"] not in existing_leas:
                all_districts.append(d)

    print(f"Inserting {len(all_districts)} new district rows…")
    con.executemany(
        """INSERT OR IGNORE INTO school_districts
           (lea_id, fips, state_abbr, district_name, enrollment,
            mmr_coverage_pct, nonmedical_exempt_pct, medical_exempt_pct,
            school_year, source)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        [
            (d["lea_id"], d["fips"], d["state_abbr"], d["district_name"],
             d["enrollment"], d["mmr_coverage_pct"], d["nonmedical_exempt_pct"],
             d["medical_exempt_pct"], d["school_year"], d["source"])
            for d in all_districts
        ],
    )

    total = con.execute("SELECT COUNT(*) FROM school_districts").fetchone()[0]
    print(f"Total districts in DB: {total}")

    # Quick sanity check on Gaines County
    gaines = con.execute("""
        SELECT district_name, mmr_coverage_pct, enrollment
        FROM school_districts WHERE fips='48169' ORDER BY mmr_coverage_pct
    """).fetchall()
    print(f"\nGaines County districts ({len(gaines)} total):")
    for name, mmr, enroll in gaines:
        flag = " ← FLAGGED" if mmr < 75 else ""
        print(f"  {name:40s} {mmr:.1f}%  ({enroll} enrolled){flag}")


if __name__ == "__main__":
    main()
