"""
Claude Opus analyst for a specific school district within a county.

Pulls district vaccination data and county context, then streams a focused
analysis of the district's contribution to outbreak risk and targeted actions.
"""

from __future__ import annotations

import json
import os
from typing import Generator

import anthropic
import duckdb

MODEL = "claude-opus-5"

SYSTEM = """You are a public health advisor specializing in school-based \
immunization programs and outbreak prevention.

You are reviewing MMR vaccination data for a single school district. The \
audience is district health liaisons and county public health officials who \
need specific, actionable intelligence about this school community.

Format your response as plain text using this structure:
RISK ASSESSMENT
[2-3 sentences: bottom-line risk this district presents, given its coverage \
level, enrollment size, and how it compares to county and state benchmarks.]

KEY VULNERABILITIES
[Bullet points using • — identify what makes this district specifically \
concerning. Focus on: exemption concentration, enrollment size, gap to herd \
immunity, and how it differs from neighboring districts. Use exact numbers.]

IMMEDIATE ACTIONS
[Numbered list of 3-4 concrete actions appropriate for district-level \
intervention: targeted outreach, exemption review, IEP/immunization clinic \
scheduling, communication to parents. Be specific to this district's profile.]

Keep the total response under 350 words. Use specific numbers. \
Do not use markdown formatting."""


def _build_district_context_from_map(
    lea_id: str, fips: str, district_data: dict, con: duckdb.DuckDBPyConnection
) -> dict:
    """Build context from GeoJSON-derived district_data (map-click path)."""
    geo = con.execute(
        "SELECT county_name, state_abbr FROM geographies WHERE fips = ?", [fips]
    ).fetchone()
    county_avg = con.execute(
        "SELECT mmr_coverage_pct FROM vaccination_coverage WHERE fips = ? ORDER BY school_year DESC LIMIT 1",
        [fips],
    ).fetchone()
    county_score = con.execute(
        "SELECT composite_score, risk_tier FROM hotspot_scores WHERE fips = ? ORDER BY score_date DESC LIMIT 1",
        [fips],
    ).fetchone()
    state_avg = con.execute(
        """SELECT AVG(vc.mmr_coverage_pct)
           FROM vaccination_coverage vc
           JOIN geographies g ON vc.fips = g.fips
           WHERE g.state_abbr = ? AND vc.school_year = '2023-2024'""",
        [geo[1] if geo else "TX"],
    ).fetchone()

    mmr_pct = float(district_data.get("mmr_coverage_pct", 0))
    return {
        "lea_id":                    lea_id,
        "district_name":             district_data.get("district_name", "Unknown District"),
        "enrollment":                None,  # not available from GeoJSON
        "mmr_coverage_pct":          mmr_pct,
        "nonmedical_exempt_pct":     None,
        "medical_exempt_pct":        None,
        "composite_score":           district_data.get("composite_score"),
        "coverage_score":            district_data.get("coverage_score"),
        "surveillance_score":        district_data.get("surveillance_score"),
        "network_score":             district_data.get("network_score"),
        "risk_tier":                 district_data.get("risk_tier"),
        "county_name":               geo[0] if geo else district_data.get("county_name", "Unknown"),
        "county_avg_mmr":            round(county_avg[0], 1) if county_avg else None,
        "county_composite_score":    county_score[0] if county_score else None,
        "county_risk_tier":          county_score[1] if county_score else None,
        "state_avg_mmr":             round(state_avg[0], 1) if state_avg and state_avg[0] else None,
        "rank_in_county":            None,
        "total_districts_in_county": None,
    }


def _build_district_context(
    lea_id: str, fips: str, con: duckdb.DuckDBPyConnection
) -> dict | None:
    dist = con.execute(
        """
        SELECT lea_id, district_name, enrollment,
               mmr_coverage_pct, nonmedical_exempt_pct, medical_exempt_pct
        FROM school_districts
        WHERE lea_id = ? AND fips = ? AND school_year = '2023-2024'
        LIMIT 1
        """,
        [lea_id, fips],
    ).fetchone()
    if not dist:
        return None

    geo = con.execute(
        "SELECT county_name, state_abbr FROM geographies WHERE fips = ?", [fips]
    ).fetchone()

    # County-level vaccination average
    county_avg = con.execute(
        "SELECT mmr_coverage_pct FROM vaccination_coverage WHERE fips = ? ORDER BY school_year DESC LIMIT 1",
        [fips],
    ).fetchone()

    # County risk score/tier
    county_score = con.execute(
        "SELECT composite_score, risk_tier FROM hotspot_scores WHERE fips = ? ORDER BY score_date DESC LIMIT 1",
        [fips],
    ).fetchone()

    # State average MMR
    state_avg = con.execute(
        """SELECT AVG(vc.mmr_coverage_pct)
           FROM vaccination_coverage vc
           JOIN geographies g ON vc.fips = g.fips
           WHERE g.state_abbr = ? AND vc.school_year = '2023-2024'""",
        [geo[1] if geo else "TX"],
    ).fetchone()

    # District's rank in the county by MMR (1 = lowest = most at-risk)
    rank_row = con.execute(
        """
        SELECT COUNT(*) + 1
        FROM school_districts
        WHERE fips = ? AND school_year = '2023-2024' AND mmr_coverage_pct < ?
        """,
        [fips, dist[3]],
    ).fetchone()

    total_districts = con.execute(
        "SELECT COUNT(*) FROM school_districts WHERE fips = ? AND school_year = '2023-2024'",
        [fips],
    ).fetchone()

    enrollment = dist[2] or 0
    mmr_pct = dist[3]
    nonmed_pct = dist[4] or 0.0
    med_pct = dist[5] or 0.0
    unprotected = round(enrollment * (1 - mmr_pct / 100))
    nm_exempt_count = round(enrollment * nonmed_pct / 100)

    return {
        "lea_id": dist[0],
        "district_name": dist[1],
        "enrollment": enrollment,
        "mmr_coverage_pct": mmr_pct,
        "nonmedical_exempt_pct": nonmed_pct,
        "medical_exempt_pct": med_pct,
        "unprotected_students": unprotected,
        "nm_exempt_count": nm_exempt_count,
        "county_name": geo[0] if geo else "Unknown",
        "county_avg_mmr": round(county_avg[0], 1) if county_avg else None,
        "county_composite_score": county_score[0] if county_score else None,
        "county_risk_tier": county_score[1] if county_score else None,
        "state_avg_mmr": round(state_avg[0], 1) if state_avg and state_avg[0] else None,
        "rank_in_county": rank_row[0] if rank_row else None,
        "total_districts_in_county": total_districts[0] if total_districts else None,
    }


def _build_district_prompt(ctx: dict) -> str:
    county_tier = ctx.get("county_risk_tier") or "UNKNOWN"
    county_score = ctx.get("county_composite_score")
    county_score_text = f"{county_score:.0f}/100" if county_score is not None else "N/A"

    # Composite score section — shown when available (map-click path)
    composite_lines = ""
    if ctx.get("composite_score") is not None:
        composite_lines = (
            f"  • Composite risk score: {ctx['composite_score']:.0f}/100 ({ctx.get('risk_tier','?')} RISK)\n"
            f"  • Coverage layer score: {ctx.get('coverage_score', 0):.0f}/100\n"
            f"  • Surveillance layer (county): {ctx.get('surveillance_score', 0):.0f}/100\n"
            f"  • Network layer (county): {ctx.get('network_score', 0):.0f}/100\n"
        )

    # Enrollment / exemption section — shown when available (DistrictTable path)
    enrollment_lines = ""
    if ctx.get("enrollment") is not None:
        nm = ctx.get("nonmedical_exempt_pct", 0) or 0
        med = ctx.get("medical_exempt_pct", 0) or 0
        nm_count = ctx.get("nm_exempt_count", 0) or 0
        unprotected = ctx.get("unprotected_students", 0) or 0
        enrollment_lines = (
            f"  • Non-medical exemptions: {nm:.1f}% of students ({nm_count:,} students)\n"
            f"  • Medical exemptions: {med:.1f}%\n"
            f"  • Total enrolled: {ctx['enrollment']:,}\n"
            f"  • Estimated unprotected students: ~{unprotected:,}\n"
        )

    rank_text = (
        f"Ranked {ctx['rank_in_county']} of {ctx['total_districts_in_county']} "
        f"districts in {ctx['county_name']} County by MMR coverage (1 = lowest)"
        if ctx.get("rank_in_county") is not None else "Ranking unavailable"
    )

    return f"""Analyze the measles risk profile for {ctx['district_name']} school district.

DISTRICT: {ctx['district_name']}
COUNTY CONTEXT: {ctx['county_name']} County — {county_tier} RISK (score {county_score_text})

VACCINATION DATA (school year 2023-2024):
  • MMR coverage: {ctx['mmr_coverage_pct']:.1f}% (herd immunity threshold: 95%)
  • Gap to herd immunity: {max(0, 95 - ctx['mmr_coverage_pct']):.1f} percentage points
{composite_lines}{enrollment_lines}
BENCHMARKS:
  • County average MMR: {ctx['county_avg_mmr']}%
  • Statewide average MMR: {ctx['state_avg_mmr']}%
  • {rank_text}

Provide your district-specific analysis now."""


def stream_district_analyst(
    lea_id: str,
    fips: str,
    con: duckdb.DuckDBPyConnection,
    district_data: dict | None = None,
) -> Generator[str, None, None]:
    """Yield SSE-formatted events: text deltas, then [DONE].

    When district_data is provided (map-click path), uses those values directly
    and skips the school_districts DB lookup to avoid LEAID format mismatches.
    """
    if district_data:
        ctx = _build_district_context_from_map(lea_id, fips, district_data, con)
    else:
        ctx = _build_district_context(lea_id, fips, con)
    if ctx is None:
        yield f"data: {json.dumps({'type': 'error', 'message': f'District {lea_id} not found'})}\n\n"
        return

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key == "your_key_here":
        yield f"data: {json.dumps({'type': 'error', 'message': 'ANTHROPIC_API_KEY not set'})}\n\n"
        return

    client = anthropic.Anthropic(api_key=api_key)

    yield f"data: {json.dumps({'type': 'meta', 'district': ctx['district_name']})}\n\n"

    try:
        with client.messages.stream(
            model=MODEL,
            max_tokens=1200,
            system=SYSTEM,
            messages=[{"role": "user", "content": _build_district_prompt(ctx)}],
            thinking={"type": "adaptive"},
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'type': 'text', 'delta': text})}\n\n"
    except anthropic.APIError as exc:
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        return

    yield "data: [DONE]\n\n"
