import sys
sys.path.insert(0, '.')

from db import get_connection
con = get_connection()

r = con.execute("SELECT COUNT(*) FROM geographies").fetchone()
print(f"geographies: {r[0]} rows")
r = con.execute("SELECT COUNT(*) FROM vaccination_coverage").fetchone()
print(f"vaccination_coverage: {r[0]} rows")

from scoring.engine import score_all_counties
scores = score_all_counties('TX', con)
print(f"Scored {len(scores)} TX counties")

top3 = sorted(scores, key=lambda x: -x['composite_score'])[:3]
for s in top3:
    print(f"  fips={s['fips']}  composite={s['composite_score']:5.1f}  tier={s['risk_tier']}")
