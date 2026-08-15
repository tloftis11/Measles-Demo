"""
Three-layer measles hotspot scoring engine.

HotspotScore = (0.40 × CoverageScore + 0.35 × SurveillanceScore + 0.25 × NetworkScore) × 100
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import date

import duckdb

HERD_IMMUNITY_THRESHOLD = 95.0  # % for measles

LAYER_WEIGHTS = {"coverage": 0.40, "surveillance": 0.35, "network": 0.25}

RISK_TIERS = [
    (75.0, "CRITICAL"),
    (50.0, "HIGH"),
    (25.0, "MODERATE"),
    (0.0,  "LOW"),
]


@dataclass
class ScoreComponents:
    # Coverage sub-scores
    coverage_gap_score: float  # from gap to 95% herd immunity threshold
    exemption_score: float     # from non-medical exemptions
    coverage_score: float      # weighted layer total (0-100)

    # Surveillance sub-scores
    incidence_score: float     # per-100k case incidence
    wastewater_score: float    # environmental surveillance signal
    positivity_score: float    # lab positivity rate
    surveillance_score: float  # weighted layer total (0-100)

    # Network sub-scores
    mobility_score: float      # county movement connectivity
    community_score: float     # religious/homogeneous community clustering
    border_score: float        # cross-border adjacency
    network_score: float       # weighted layer total (0-100)

    # Final
    composite_score: float
    risk_tier: str

    mmr_coverage_pct: float
    nonmedical_exempt_pct: float
    recent_cases: int
    population: int


def _score_coverage(
    mmr_coverage_pct: float,
    nonmedical_exempt_pct: float,
    medical_exempt_pct: float,
) -> tuple[float, float, float]:
    """Returns (gap_score, exemption_score, coverage_score) each 0-100."""
    gap = max(0.0, HERD_IMMUNITY_THRESHOLD - mmr_coverage_pct)
    gap_score = min(gap * 3.5, 60.0)

    # Non-medical exemptions are voluntary and more concerning than medical
    exempt_score = min(nonmedical_exempt_pct * 8.0 + medical_exempt_pct * 1.5, 40.0)

    coverage_score = min(gap_score + exempt_score, 100.0)
    return gap_score, exempt_score, coverage_score


def _score_surveillance(
    confirmed_cases: int,
    suspect_cases: int,
    wastewater_signal: float | None,
    lab_positivity_pct: float | None,
    population: int,
) -> tuple[float, float, float, float]:
    """Returns (incidence_score, wastewater_score, positivity_score, surveillance_score)."""
    total_cases = confirmed_cases + (suspect_cases or 0)
    incidence_per_100k = (total_cases / population * 100_000) if population > 0 else 0.0
    # 3 cases per 100k in 90 days → 60 pts (high but not max)
    incidence_score = min(incidence_per_100k * 20.0, 60.0)

    ww = wastewater_signal or 0.0
    wastewater_score = ww * 25.0

    pos = lab_positivity_pct or 0.0
    positivity_score = min(pos * 3.0, 15.0)

    surveillance_score = min(incidence_score + wastewater_score + positivity_score, 100.0)
    return incidence_score, wastewater_score, positivity_score, surveillance_score


def _score_network(
    mobility_index: float,
    religious_community_idx: float,
    border_adjacent: bool,
) -> tuple[float, float, float, float]:
    """Returns (mobility_score, community_score, border_score, network_score)."""
    mobility_score = mobility_index * 40.0
    community_score = religious_community_idx * 40.0
    border_score = 20.0 if border_adjacent else 0.0
    network_score = min(mobility_score + community_score + border_score, 100.0)
    return mobility_score, community_score, border_score, network_score


def _risk_tier(composite: float) -> str:
    for threshold, label in RISK_TIERS:
        if composite >= threshold:
            return label
    return "LOW"


def score_county(fips: str, con: duckdb.DuckDBPyConnection) -> ScoreComponents | None:
    """Compute a full score for a single county from the latest available data."""
    cov_row = con.execute(
        """
        SELECT mmr_coverage_pct, medical_exempt_pct, nonmedical_exempt_pct
        FROM vaccination_coverage
        WHERE fips = ? ORDER BY school_year DESC LIMIT 1
        """,
        [fips],
    ).fetchone()

    if not cov_row:
        return None

    surv_row = con.execute(
        """
        SELECT confirmed_cases, suspect_cases, wastewater_signal,
               lab_positivity_pct
        FROM surveillance
        WHERE fips = ? ORDER BY report_date DESC LIMIT 1
        """,
        [fips],
    ).fetchone()

    net_row = con.execute(
        """
        SELECT mobility_index, religious_community_idx, border_adjacent
        FROM network_metrics
        WHERE fips = ? ORDER BY metric_date DESC LIMIT 1
        """,
        [fips],
    ).fetchone()

    pop_row = con.execute(
        "SELECT population FROM geographies WHERE fips = ?", [fips]
    ).fetchone()

    mmr_pct, med_pct, nonmed_pct = cov_row
    confirmed   = surv_row[0] if surv_row else 0
    suspect     = surv_row[1] if surv_row else 0
    ww_signal   = surv_row[2] if surv_row else None
    lab_pos     = surv_row[3] if surv_row else None
    mobility    = net_row[0] if net_row else 0.5
    rel_idx     = net_row[1] if net_row else 0.3
    border      = bool(net_row[2]) if net_row else False
    population  = pop_row[0] if pop_row else 50_000

    gap_s, exempt_s, cov_s = _score_coverage(mmr_pct, nonmed_pct, med_pct)
    inc_s, ww_s, pos_s, surv_s = _score_surveillance(
        confirmed, suspect, ww_signal, lab_pos, population
    )
    mob_s, com_s, bord_s, net_s = _score_network(mobility, rel_idx, border)

    composite = (
        LAYER_WEIGHTS["coverage"]     * cov_s
        + LAYER_WEIGHTS["surveillance"] * surv_s
        + LAYER_WEIGHTS["network"]      * net_s
    )

    return ScoreComponents(
        coverage_gap_score=round(gap_s, 1),
        exemption_score=round(exempt_s, 1),
        coverage_score=round(cov_s, 1),
        incidence_score=round(inc_s, 1),
        wastewater_score=round(ww_s, 1),
        positivity_score=round(pos_s, 1),
        surveillance_score=round(surv_s, 1),
        mobility_score=round(mob_s, 1),
        community_score=round(com_s, 1),
        border_score=round(bord_s, 1),
        network_score=round(net_s, 1),
        composite_score=round(composite, 1),
        risk_tier=_risk_tier(composite),
        mmr_coverage_pct=mmr_pct,
        nonmedical_exempt_pct=nonmed_pct,
        recent_cases=confirmed,
        population=population,
    )


def score_all_counties(
    state_abbr: str, con: duckdb.DuckDBPyConnection
) -> list[dict]:
    """Score every county in a state and persist results to hotspot_scores."""
    fips_rows = con.execute(
        "SELECT fips FROM geographies WHERE state_abbr = ?", [state_abbr.upper()]
    ).fetchall()

    today = date.today().isoformat()
    results = []

    for (fips,) in fips_rows:
        sc = score_county(fips, con)
        if sc is None:
            continue

        con.execute(
            """
            INSERT OR REPLACE INTO hotspot_scores VALUES (?,?,?,?,?,?,?,?)
            """,
            [
                fips,
                today,
                sc.coverage_score,
                sc.surveillance_score,
                sc.network_score,
                sc.composite_score,
                sc.risk_tier,
                json.dumps(asdict(sc)),
            ],
        )
        results.append({"fips": fips, **asdict(sc)})

    return results
