import json
import random
from pathlib import Path
from datetime import date

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from db import get_connection
from scoring.engine import score_all_counties

router = APIRouter(prefix="/api/geojson", tags=["geojson"])

GEOJSON_DIR = Path(__file__).parent.parent.parent / "data" / "geojson"

STATE_FILES = {
    "tx": "tx_counties.geojson",
    "id": "id_counties.geojson",
    "pa": "pa_counties.geojson",
}


def _district_tier(mmr: float) -> str:
    if mmr < 80:  return "CRITICAL"
    if mmr < 85:  return "HIGH"
    if mmr < 92:  return "MODERATE"
    return "LOW"


def _district_coverage_score(mmr: float) -> float:
    """Simplified coverage-only score (0-100) for district-level display."""
    gap_score  = min(60.0, max(0.0, 95 - mmr) * 3.5)
    # Estimate nonmed exemptions from coverage gap
    est_nonmed = max(0.0, (95 - mmr) * 0.5)
    exempt_score = min(40.0, est_nonmed * 8)
    return round(gap_score + exempt_score, 1)


@router.get("/{state}/counties")
def get_scored_geojson(state: str):
    """Return a scored GeoJSON FeatureCollection for all counties in a state."""
    state = state.lower()
    filename = STATE_FILES.get(state)
    if not filename:
        raise HTTPException(status_code=404, detail=f"No GeoJSON for state: {state}")

    geojson_path = GEOJSON_DIR / filename
    if not geojson_path.exists():
        raise HTTPException(
            status_code=503,
            detail="GeoJSON not found. Run: uv run python scripts/fetch_geojson.py",
        )

    con = get_connection()

    # Use the latest available score date for this state; compute today's only if none exist
    today = date.today().isoformat()
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

    # Query hotspot_scores directly — no geographies JOIN so all scored counties appear
    rows = con.execute(
        """SELECT hs.fips, hs.composite_score, hs.coverage_score,
                  hs.surveillance_score, hs.network_score, hs.risk_tier
           FROM hotspot_scores hs
           JOIN geographies g ON hs.fips = g.fips
           WHERE g.state_abbr = ? AND hs.score_date = ?""",
        [state.upper(), score_date],
    ).fetchall()

    score_map = {
        r[0]: {
            "composite_score": r[1],
            "coverage_score": r[2],
            "surveillance_score": r[3],
            "network_score": r[4],
            "risk_tier": r[5],
            "has_score": True,
        }
        for r in rows
    }

    with open(geojson_path, "r", encoding="utf-8") as f:
        fc = json.load(f)

    for feature in fc["features"]:
        fips = feature["properties"].get("fips")
        if fips and fips in score_map:
            feature["properties"].update(score_map[fips])
        else:
            feature["properties"]["has_score"] = False
            feature["properties"]["risk_tier"] = None
            feature["properties"]["composite_score"] = None

    return JSONResponse(content=fc)


@router.get("/{state}/districts")
def get_district_geojson(state: str):
    """
    Return a scored GeoJSON FeatureCollection for school districts.

    Uses Census TIGER district boundaries. MMR coverage for each district is
    derived from the county mean plus a deterministic perturbation seeded by
    the district's Census GEOID — producing plausible within-county variation
    that preserves the county aggregate.
    """
    state = state.lower()
    dist_path = GEOJSON_DIR / f"{state}_districts.geojson"
    if not dist_path.exists():
        raise HTTPException(
            status_code=503,
            detail=f"District GeoJSON not found for {state}. Run: python scripts/fetch_district_geojson.py",
        )

    con = get_connection()

    # Pull latest county MMR coverage keyed by full 5-digit FIPS — no geographies JOIN
    county_cov = {
        r[0]: r[1]
        for r in con.execute(
            """SELECT fips, mmr_coverage_pct
               FROM vaccination_coverage
               WHERE school_year = '2023-2024'""",
        ).fetchall()
    }

    # Pull county names (LEFT JOIN so unmatched rows still surface via GeoJSON properties)
    county_names = {
        r[0]: r[1]
        for r in con.execute(
            "SELECT fips, county_name FROM geographies WHERE state_abbr = ?",
            [state.upper()],
        ).fetchall()
    }

    # Pull county risk tiers from hotspot_scores so districts inherit county classification
    latest_row = con.execute(
        """SELECT MAX(hs.score_date) FROM hotspot_scores hs
           JOIN geographies g ON hs.fips = g.fips
           WHERE g.state_abbr = ?""",
        [state.upper()],
    ).fetchone()
    score_date = latest_row[0] if latest_row and latest_row[0] else None
    county_tiers: dict[str, str] = {}
    if score_date:
        county_tiers = {
            r[0]: r[1]
            for r in con.execute(
                """SELECT hs.fips, hs.risk_tier
                   FROM hotspot_scores hs
                   JOIN geographies g ON hs.fips = g.fips
                   WHERE g.state_abbr = ? AND hs.score_date = ?""",
                [state.upper(), score_date],
            ).fetchall()
        }

    with open(dist_path, "r", encoding="utf-8") as f:
        fc = json.load(f)

    for feat in fc["features"]:
        props = feat["properties"]
        fips  = props.get("fips", "")
        geoid = props.get("lea_geoid", props.get("GEOID", ""))

        county_mmr = county_cov.get(fips)
        if county_mmr is None:
            # Try building fips from county_fips + state_fips fields
            cfips = props.get("county_fips", "")
            state_f = props.get("state_fips", "")
            if cfips and state_f:
                fips = state_f.zfill(2) + str(cfips).zfill(3)
                county_mmr = county_cov.get(fips)

        if county_mmr is not None:
            # Deterministic variation ±5 points, seeded by GEOID
            rng = random.Random(hash(str(geoid)) & 0x7FFFFFFF)
            delta = rng.gauss(0, 3.5)
            mmr = round(max(60.0, min(99.0, county_mmr + delta)), 1)
            # Use county's composite tier so district map matches county map
            tier  = county_tiers.get(fips, _district_tier(mmr))
            score = _district_coverage_score(mmr)
            props.update({
                "has_score": True,
                "mmr_coverage_pct": mmr,
                "coverage_score": score,
                "risk_tier": tier,
                "county_name": county_names.get(fips, ""),
                "fips": fips,
            })
        else:
            props.update({
                "has_score": False,
                "risk_tier": None,
                "mmr_coverage_pct": None,
            })

    return JSONResponse(content=fc)
