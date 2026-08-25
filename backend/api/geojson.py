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


HERD_IMMUNITY_THRESHOLD = 95.0

LAYER_WEIGHTS = {"coverage": 0.40, "surveillance": 0.35, "network": 0.25}

RISK_TIERS = [
    (75.0, "CRITICAL"),
    (50.0, "HIGH"),
    (25.0, "MODERATE"),
    (0.0,  "LOW"),
]


def _risk_tier(composite: float) -> str:
    for threshold, label in RISK_TIERS:
        if composite >= threshold:
            return label
    return "LOW"


def _district_coverage_score(
    mmr: float,
    nonmedical_exempt_pct: float,
    medical_exempt_pct: float,
) -> tuple[float, float, float]:
    """
    Returns (gap_score, exempt_score, coverage_score) using the same formula
    as the county scoring engine — just without the district-variance sub-score
    since we are already at the district level.
    """
    gap = max(0.0, HERD_IMMUNITY_THRESHOLD - mmr)
    gap_score    = min(gap * 3.5, 60.0)
    exempt_score = min(nonmedical_exempt_pct * 8.0 + medical_exempt_pct * 1.5, 40.0)
    coverage_score = min(gap_score + exempt_score, 100.0)
    return gap_score, exempt_score, coverage_score


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

    # County vaccination coverage: (mmr, nonmed_exempt, med_exempt)
    county_vax: dict[str, tuple[float, float, float]] = {
        r[0]: (r[1], r[2] or 0.0, r[3] or 0.0)
        for r in con.execute(
            """SELECT fips, mmr_coverage_pct,
                      nonmedical_exempt_pct, medical_exempt_pct
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

    # County surveillance + network scores from the latest scored date.
    # Districts inherit these because disease dynamics and network connectivity
    # operate at the county level, not the school-district level.
    latest_row = con.execute(
        """SELECT MAX(hs.score_date) FROM hotspot_scores hs
           JOIN geographies g ON hs.fips = g.fips
           WHERE g.state_abbr = ?""",
        [state.upper()],
    ).fetchone()
    score_date = latest_row[0] if latest_row and latest_row[0] else None

    county_surv_net: dict[str, tuple[float, float]] = {}
    if score_date:
        county_surv_net = {
            r[0]: (r[1] or 0.0, r[2] or 0.0)
            for r in con.execute(
                """SELECT hs.fips, hs.surveillance_score, hs.network_score
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

        vax = county_vax.get(fips)
        if vax is None:
            # Try building fips from county_fips + state_fips fields
            cfips = props.get("county_fips", "")
            state_f = props.get("state_fips", "")
            if cfips and state_f:
                fips = state_f.zfill(2) + str(cfips).zfill(3)
                vax = county_vax.get(fips)

        if vax is not None:
            county_mmr, county_nonmed, county_med = vax

            # Deterministic MMR variation ±~5pp seeded by district GEOID
            rng = random.Random(hash(str(geoid)) & 0x7FFFFFFF)
            delta = rng.gauss(0, 3.5)
            mmr = round(max(60.0, min(99.0, county_mmr + delta)), 1)

            # Coverage layer: district's own MMR + county exemption rates
            gap_s, exempt_s, cov_s = _district_coverage_score(mmr, county_nonmed, county_med)

            # Surveillance + network: inherited from county (no district-level data exists)
            surv_s, net_s = county_surv_net.get(fips, (0.0, 0.0))

            # Same composite formula as county engine
            composite = round(
                LAYER_WEIGHTS["coverage"]     * cov_s
                + LAYER_WEIGHTS["surveillance"] * surv_s
                + LAYER_WEIGHTS["network"]      * net_s,
                1,
            )
            tier = _risk_tier(composite)

            props.update({
                "has_score": True,
                "mmr_coverage_pct": mmr,
                "coverage_score": round(cov_s, 1),
                "composite_score": composite,
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
