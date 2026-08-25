import csv
import io
from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from db import get_connection
from scoring.engine import score_all_counties, score_county

router = APIRouter(prefix="/api/scores", tags=["scores"])


@router.get("/{state}")
def get_state_scores(state: str):
    """Return current hotspot scores for every county in a state."""
    con = get_connection()
    today = date.today().isoformat()

    # Use the latest available score date; compute today's only if nothing exists
    latest_row = con.execute(
        """SELECT MAX(hs.score_date) FROM hotspot_scores hs
           JOIN geographies g ON hs.fips = g.fips
           WHERE g.state_abbr = ?""",
        [state.upper()],
    ).fetchone()
    score_date = latest_row[0] if latest_row and latest_row[0] else None

    if not score_date:
        score_all_counties(state, con)
        score_date = today

    cached = con.execute(
        """
        SELECT hs.fips, g.county_name, g.full_name, g.population,
               hs.coverage_score, hs.surveillance_score, hs.network_score,
               hs.composite_score, hs.risk_tier
        FROM hotspot_scores hs
        JOIN geographies g ON hs.fips = g.fips
        WHERE g.state_abbr = ? AND hs.score_date = ?
        ORDER BY hs.composite_score DESC
        """,
        [state.upper(), score_date],
    ).fetchall()

    if not cached:
        raise HTTPException(status_code=404, detail=f"No data for state: {state}")

    columns = [
        "fips", "county_name", "full_name", "population",
        "coverage_score", "surveillance_score", "network_score",
        "composite_score", "risk_tier",
    ]
    return [dict(zip(columns, row)) for row in cached]


@router.get("/{state}/export/csv")
def export_scores_csv(state: str):
    """Download all county scores as a CSV file."""
    con = get_connection()
    today = date.today().isoformat()
    rows = con.execute(
        """
        SELECT g.fips, g.county_name, g.population,
               hs.composite_score, hs.risk_tier,
               hs.coverage_score, hs.surveillance_score, hs.network_score,
               vc.mmr_coverage_pct, vc.nonmedical_exempt_pct,
               s.confirmed_cases, s.wastewater_signal,
               hs.score_date
        FROM hotspot_scores hs
        JOIN geographies g ON hs.fips = g.fips
        LEFT JOIN vaccination_coverage vc ON vc.fips = g.fips
        LEFT JOIN surveillance s ON s.fips = g.fips
        WHERE g.state_abbr = ?
          AND hs.score_date = (SELECT MAX(score_date) FROM hotspot_scores WHERE fips = hs.fips)
          AND (vc.school_year IS NULL OR vc.school_year = '2023-2024')
          AND (s.report_date IS NULL OR s.report_date = (SELECT MAX(report_date) FROM surveillance WHERE fips = s.fips))
        ORDER BY hs.composite_score DESC
        """,
        [state.upper()],
    ).fetchall()

    cols = [
        "fips", "county_name", "population",
        "composite_score", "risk_tier",
        "coverage_score", "surveillance_score", "network_score",
        "mmr_coverage_pct", "nonmedical_exempt_pct",
        "confirmed_cases", "wastewater_signal",
        "score_date",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=cols)
    writer.writeheader()
    for row in rows:
        writer.writerow(dict(zip(cols, row)))

    filename = f"measles_hotspot_{state.lower()}_{today}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{state}/{fips}/breakdown")
def get_score_breakdown(state: str, fips: str):
    """Return full sub-score breakdown for a single county."""
    con = get_connection()

    geo = con.execute(
        "SELECT county_name, full_name, population FROM geographies WHERE fips = ?",
        [fips],
    ).fetchone()
    if not geo:
        raise HTTPException(status_code=404, detail=f"County not found: {fips}")

    sc = score_county(fips, con)
    if sc is None:
        raise HTTPException(status_code=404, detail=f"No scoring data for: {fips}")

    return {
        "fips": fips,
        "county_name": geo[0],
        "full_name": geo[1],
        "population": geo[2],
        **asdict(sc),
    }


@router.get("/{state}/{fips}/history")
def get_score_history(state: str, fips: str):
    """Return score time series for a county."""
    con = get_connection()
    rows = con.execute(
        """
        SELECT score_date, composite_score, coverage_score,
               surveillance_score, network_score, risk_tier
        FROM hotspot_scores
        WHERE fips = ?
        ORDER BY score_date ASC
        """,
        [fips],
    ).fetchall()

    cols = ["score_date", "composite_score", "coverage_score",
            "surveillance_score", "network_score", "risk_tier"]
    return [dict(zip(cols, r)) for r in rows]
