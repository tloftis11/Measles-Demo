from fastapi import APIRouter, HTTPException
from db import get_connection

router = APIRouter(prefix="/api/districts", tags=["districts"])


@router.get("/{state}/{fips}")
def get_county_districts(state: str, fips: str):
    """Return school district breakdown for a county, sorted by MMR coverage asc."""
    con = get_connection()

    geo = con.execute(
        "SELECT county_name FROM geographies WHERE fips = ?", [fips]
    ).fetchone()
    if not geo:
        raise HTTPException(status_code=404, detail=f"County not found: {fips}")

    rows = con.execute(
        """
        SELECT lea_id, district_name, enrollment,
               mmr_coverage_pct, nonmedical_exempt_pct, medical_exempt_pct,
               school_year, source
        FROM school_districts
        WHERE fips = ? AND school_year = '2023-2024'
        ORDER BY mmr_coverage_pct ASC
        """,
        [fips],
    ).fetchall()

    cols = ["lea_id", "district_name", "enrollment",
            "mmr_coverage_pct", "nonmedical_exempt_pct", "medical_exempt_pct",
            "school_year", "source"]

    return {
        "fips": fips,
        "county_name": geo[0],
        "districts": [dict(zip(cols, r)) for r in rows],
    }


@router.get("/{state}/{fips}/history")
def get_county_score_history(state: str, fips: str):
    """Return composite score history for sparkline rendering."""
    con = get_connection()
    rows = con.execute(
        """
        SELECT score_date, composite_score, risk_tier
        FROM hotspot_scores
        WHERE fips = ?
        ORDER BY score_date ASC
        """,
        [fips],
    ).fetchall()
    return [{"date": r[0], "score": r[1], "tier": r[2]} for r in rows]
