"""
Seed 10 weeks of historical hotspot scores for trend sparklines.

Strategy:
  - Goes back 10 weeks from today in weekly steps.
  - Most counties: small random walk (±2 points) around current score.
  - West TX high-risk cluster: scores trend upward 1-2 points/week
    (simulating a deteriorating situation leading to the current CRITICAL reading).
  - Gaines County: starts as HIGH ~60, climbs to CRITICAL 80.5 over the period.

Run from repo root:
    uv run --project backend python scripts/seed_history.py
"""
from __future__ import annotations
import os, sys, random
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))
os.environ.setdefault("DB_PATH", str(REPO_ROOT / "data" / "measles.duckdb"))

from db import get_connection  # noqa: E402

WEEKS = 10

# Counties in the West TX cluster that trend upward
TRENDING_UP = {
    "48169",  # Gaines — most dramatic rise
    "48501",  # Yoakum
    "48079",  # Cochran
    "48445",  # Terry
    "48317",  # Martin
    "48003",  # Andrews
}


def tier(score: float) -> str:
    if score >= 75: return "CRITICAL"
    if score >= 50: return "HIGH"
    if score >= 25: return "MODERATE"
    return "LOW"


def main():
    con = get_connection()
    today = date.today()

    # Get current scores
    current_scores = {
        r[0]: {"composite": r[1], "coverage": r[2], "surveillance": r[3], "network": r[4], "components": r[5]}
        for r in con.execute(
            """SELECT fips, composite_score, coverage_score, surveillance_score,
                      network_score, score_components
               FROM hotspot_scores
               WHERE score_date = (SELECT MAX(score_date) FROM hotspot_scores WHERE fips = hotspot_scores.fips)"""
        ).fetchall()
    }

    print(f"Seeding history for {len(current_scores)} counties over {WEEKS} weeks…")

    rows_inserted = 0
    rng = random.Random(20240101)

    for week in range(WEEKS, 0, -1):  # week 10 = oldest, week 1 = most recent
        score_date = (today - timedelta(weeks=week)).isoformat()

        for fips, cur in current_scores.items():
            # Check if history row already exists
            exists = con.execute(
                "SELECT 1 FROM hotspot_scores WHERE fips=? AND score_date=?",
                [fips, score_date]
            ).fetchone()
            if exists:
                continue

            c = cur["composite"]

            if fips in TRENDING_UP:
                # Travel back in time: subtract growth
                if fips == "48169":
                    # Gaines: started at ~58 (HIGH), ended at 80.5 (CRITICAL)
                    weeks_ago = week
                    c = max(55.0, c - weeks_ago * 2.2 + rng.gauss(0, 1.5))
                else:
                    c = max(40.0, c - week * 1.4 + rng.gauss(0, 1.2))
            else:
                # Normal random walk: ±2 points from current
                c = c + rng.gauss(0, 1.8)

            c = max(0.0, min(100.0, c))

            # Sub-scores: perturb proportionally
            cov  = max(0.0, min(100.0, cur["coverage"]    + rng.gauss(0, 2.0)))
            surv = max(0.0, min(100.0, cur["surveillance"] + rng.gauss(0, 2.0)))
            net  = max(0.0, min(100.0, cur["network"]      + rng.gauss(0, 1.5)))

            con.execute(
                """INSERT OR IGNORE INTO hotspot_scores
                   (fips, score_date, coverage_score, surveillance_score,
                    network_score, composite_score, risk_tier, score_components)
                   VALUES (?,?,?,?,?,?,?,?)""",
                [fips, score_date, round(cov,1), round(surv,1),
                 round(net,1), round(c,1), tier(c), cur["components"]]
            )
            rows_inserted += 1

    print(f"Inserted {rows_inserted} historical score rows.")

    # Verify Gaines trend
    gaines = con.execute(
        """SELECT score_date, composite_score, risk_tier
           FROM hotspot_scores WHERE fips='48169'
           ORDER BY score_date"""
    ).fetchall()
    print("\nGaines County score trend:")
    for d, score, t in gaines:
        bar = "█" * int(score / 5)
        print(f"  {d}  {score:5.1f}  {t:8s}  {bar}")


if __name__ == "__main__":
    main()
