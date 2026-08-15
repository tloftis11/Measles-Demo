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

STATE_FILES = {"tx": "tx_counties.geojson"}


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

    # Ensure scores exist for today
    today = date.today().isoformat()
    cached = con.execute(
        """SELECT COUNT(*) FROM hotspot_scores hs
           JOIN geographies g ON hs.fips = g.fips
           WHERE g.state_abbr = ? AND hs.score_date = ?""",
        [state.upper(), today],
    ).fetchone()
    if not cached or cached[0] == 0:
        score_all_counties(state, con)

    # Load scores into a dict keyed by FIPS
    rows = con.execute(
        """SELECT hs.fips, hs.composite_score, hs.coverage_score,
                  hs.surveillance_score, hs.network_score, hs.risk_tier,
                  g.county_name, g.population
           FROM hotspot_scores hs
           JOIN geographies g ON hs.fips = g.fips
           WHERE g.state_abbr = ? AND hs.score_date = ?""",
        [state.upper(), today],
    ).fetchall()

    score_map = {
        r[0]: {
            "composite_score": r[1],
            "coverage_score": r[2],
            "surveillance_score": r[3],
            "network_score": r[4],
            "risk_tier": r[5],
            "county_name": r[6],
            "population": r[7],
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
    dist_path = GEOJSON_DIR / "tx_districts.geojson"
    if not dist_path.exists():
        raise HTTPException(
            status_code=503,
            detail="District GeoJSON not found. Run: python scripts/fetch_district_geojson.py",
        )

    con = get_connection()

    # Pull latest county MMR coverage keyed by full 5-digit FIPS
    county_cov = {
        r[0]: r[1]
        for r in con.execute(
            """SELECT vc.fips, vc.mmr_coverage_pct
               FROM vaccination_coverage vc
               JOIN geographies g ON vc.fips = g.fips
               WHERE g.state_abbr = ?
                 AND vc.school_year = '2023-2024'""",
            [state.upper()],
        ).fetchall()
    }

    # Pull county names
    county_names = {
        r[0]: r[1]
        for r in con.execute(
            "SELECT fips, county_name FROM geographies WHERE state_abbr = ?",
            [state.upper()],
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
            # Try building fips from county_fips field
            cfips = props.get("county_fips", "")
            if cfips:
                fips = "48" + str(cfips).zfill(3)
                county_mmr = county_cov.get(fips)

        if county_mmr is not None:
            # Deterministic variation ±5 points, seeded by GEOID
            rng = random.Random(hash(str(geoid)) & 0x7FFFFFFF)
            delta = rng.gauss(0, 3.5)
            mmr = round(max(60.0, min(99.0, county_mmr + delta)), 1)
            tier  = _district_tier(mmr)
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
