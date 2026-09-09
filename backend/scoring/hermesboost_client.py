"""Fetches the real HermesBoost risk score for Texas counties and writes it
into hotspot_scores, replacing the internal 3-layer engine for Texas only
-- Idaho and Pennsylvania have no HermesBoost model and keep using
scoring.engine.score_all_counties unchanged.

HermesBoost's risk score combines a trained classification model's P(any
case) with a trained regression model's predicted case count if one
occurs -- a real ML model, not a hand-weighted formula. Its raw risk_score
(probability * predicted_magnitude) has no fixed range and drifts as the
underlying models retrain, so it's rescaled here to a 0-100 percentile
rank among the counties currently being scored -- stable over time in a
way a fixed linear scale would not be.
"""

from __future__ import annotations

import json
import os
from datetime import date

import duckdb
import httpx

from scoring.engine import RISK_TIERS, _compute_district_variance

HERMESBOOST_API_URL = os.getenv("HERMESBOOST_API_URL", "")
HERMESBOOST_API_KEY = os.getenv("HERMESBOOST_API_KEY", "")
HERMESBOOST_RISK_SCORE_ID = os.getenv("HERMESBOOST_RISK_SCORE_ID", "")


def _risk_tier(percentile: float) -> str:
    for threshold, label in RISK_TIERS:
        if percentile >= threshold:
            return label
    return "LOW"


def fetch_and_score_texas(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """Fetches HermesBoost's current TX risk scores, rescales to a 0-100
    percentile rank, and persists into hotspot_scores. Returns the scored
    rows in the same shape score_all_counties() would have. Raises
    RuntimeError if the integration isn't configured, and re-raises any
    HTTP error from HermesBoost -- a misconfigured or unreachable
    integration should be loud, not silently serve stale data."""
    if not (HERMESBOOST_API_URL and HERMESBOOST_API_KEY and HERMESBOOST_RISK_SCORE_ID):
        raise RuntimeError(
            "HermesBoost integration not configured -- set HERMESBOOST_API_URL, "
            "HERMESBOOST_API_KEY, and HERMESBOOST_RISK_SCORE_ID in backend/.env"
        )

    resp = httpx.get(
        f"{HERMESBOOST_API_URL}/api/v1/risk-scores/{HERMESBOOST_RISK_SCORE_ID}/scores",
        headers={"X-API-Key": HERMESBOOST_API_KEY},
        timeout=30.0,
    )
    resp.raise_for_status()
    rows = resp.json()["rows"]  # already sorted descending by risk_score

    today = date.today().isoformat()
    n = len(rows)
    results = []

    for i, row in enumerate(rows):
        fips = row["entity_id"]
        # Percentile rank: highest risk_score -> 100, lowest -> 0.
        percentile = round(100.0 * (n - 1 - i) / max(n - 1, 1), 1) if n > 1 else 100.0
        tier = _risk_tier(percentile)
        district_variance = _compute_district_variance(fips, con)
        probability_pct = round(row["probability"] * 100, 1)
        predicted_magnitude = row["predicted_magnitude"]

        con.execute(
            """
            INSERT OR REPLACE INTO hotspot_scores
            (fips, score_date, coverage_score, surveillance_score, network_score,
             composite_score, risk_tier, score_components,
             scoring_source, probability_pct, predicted_magnitude)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            [
                fips,
                today,
                None,
                None,
                district_variance,
                percentile,
                tier,
                json.dumps(
                    {
                        "probability": row["probability"],
                        "predicted_magnitude": predicted_magnitude,
                        "risk_score_raw": row["risk_score"],
                        "district_variance_score": district_variance,
                        "percentile_rank": percentile,
                        "hermesboost_risk_score_id": HERMESBOOST_RISK_SCORE_ID,
                    }
                ),
                "hermesboost",
                probability_pct,
                predicted_magnitude,
            ],
        )
        results.append(
            {
                "fips": fips,
                "composite_score": percentile,
                "risk_tier": tier,
                "scoring_source": "hermesboost",
                "probability_pct": probability_pct,
                "predicted_magnitude": predicted_magnitude,
                "network_score": district_variance,
            }
        )

    return results
