import json
from pathlib import Path
from datetime import date

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from db import get_connection
from scoring.engine import score_all_counties
from scoring.hermesboost_client import fetch_and_score_texas

router = APIRouter(prefix="/api/geojson", tags=["geojson"])

GEOJSON_DIR = Path(__file__).parent.parent.parent / "data" / "geojson"

STATE_FILES = {
    "tx": "tx_counties.geojson",
    "id": "id_counties.geojson",
    "pa": "pa_counties.geojson",
}


def _rescore(state: str, con) -> None:
    """TX uses the real HermesBoost risk score; every other state keeps
    the internal 3-layer engine (no HermesBoost model exists for them)."""
    if state.upper() == "TX":
        fetch_and_score_texas(con)
    else:
        score_all_counties(state, con)


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
        _rescore(state, con)
        score_date = today

    # Query hotspot_scores directly — no geographies JOIN so all scored counties appear
    rows = con.execute(
        """SELECT hs.fips, hs.composite_score, hs.coverage_score,
                  hs.surveillance_score, hs.network_score, hs.risk_tier,
                  hs.scoring_source, hs.probability_pct, hs.predicted_magnitude
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
            "scoring_source": r[6],
            "probability_pct": r[7],
            "predicted_magnitude": r[8],
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

    Uses Census TIGER district boundaries. There is no reliable district-
    level score: the dashboard's own school_districts table uses synthetic,
    fabricated district names/ids that don't correspond to these real
    Census TIGER boundaries, so there's nothing genuine to key a
    per-district score off of. Every district in a county is given that
    county's real score directly (flat broadcast) -- mmr_coverage_pct shown
    here is the county's real average, not a per-district number.
    """
    state = state.lower()
    dist_path = GEOJSON_DIR / f"{state}_districts.geojson"
    if not dist_path.exists():
        raise HTTPException(
            status_code=503,
            detail=f"District GeoJSON not found for {state}. Run: python scripts/fetch_district_geojson.py",
        )

    con = get_connection()

    # County average MMR (real, shown as county context -- never per-district)
    county_mmr: dict[str, float] = {
        r[0]: r[1]
        for r in con.execute(
            """SELECT fips, mmr_coverage_pct
               FROM vaccination_coverage
               WHERE school_year = '2023-2024'""",
        ).fetchall()
    }

    # County names
    county_names = {
        r[0]: r[1]
        for r in con.execute(
            "SELECT fips, county_name FROM geographies WHERE state_abbr = ?",
            [state.upper()],
        ).fetchall()
    }

    today = date.today().isoformat()
    latest_row = con.execute(
        """SELECT MAX(hs.score_date) FROM hotspot_scores hs
           JOIN geographies g ON hs.fips = g.fips
           WHERE g.state_abbr = ?""",
        [state.upper()],
    ).fetchone()
    score_date = latest_row[0] if latest_row and latest_row[0] else None
    if not score_date:
        _rescore(state, con)
        score_date = today

    county_scores: dict[str, dict] = {
        r[0]: {
            "composite_score": r[1],
            "risk_tier": r[2],
            "scoring_source": r[3],
            "probability_pct": r[4],
            "predicted_magnitude": r[5],
        }
        for r in con.execute(
            """SELECT hs.fips, hs.composite_score, hs.risk_tier,
                      hs.scoring_source, hs.probability_pct, hs.predicted_magnitude
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
        fips = props.get("fips", "")

        if fips not in county_scores:
            # Try building fips from county_fips + state_fips fields
            cfips = props.get("county_fips", "")
            state_f = props.get("state_fips", "")
            if cfips and state_f:
                fips = state_f.zfill(2) + str(cfips).zfill(3)

        score = county_scores.get(fips)
        if score is not None:
            props.update(score)
            props["has_score"] = True
            props["mmr_coverage_pct"] = county_mmr.get(fips)
            props["county_name"] = county_names.get(fips, "")
            props["fips"] = fips
        else:
            props.update({
                "has_score": False,
                "risk_tier": None,
                "mmr_coverage_pct": None,
            })

    return JSONResponse(content=fc)
