"""
Claude Opus interpretation of a SEIR simulation result.
"""
from __future__ import annotations
import json, os
from typing import Generator
import anthropic
import duckdb

MODEL = "claude-opus-5"

SYSTEM = """You are a CDC epidemiological analyst interpreting a measles SEIR simulation result.
Write a concise, data-driven narrative interpreting the outbreak trajectory for public health officials.
Use plain text with section headers in ALL CAPS. No markdown.

Structure:
TRAJECTORY SUMMARY
[2-3 sentences describing the epidemic curve and key numbers]

PEAK AND TIMING
[Specific peak day, peak infectious count, and what drives the timing]

HERD IMMUNITY GAP
[Compare current MMR coverage to the herd immunity threshold; quantify the gap and its consequence]

INTERVENTION SCENARIOS
[2-3 numbered specific interventions — vaccination campaigns, school exclusions, exposure notifications — with expected impact on peak timing or attack rate]

Keep total under 380 words. Be specific with numbers. No hedging."""


def stream_narrative(
    fips: str,
    sim_result: dict,
    con: duckdb.DuckDBPyConnection,
) -> Generator[str, None, None]:

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key == "your_key_here":
        yield f"data: {json.dumps({'type': 'error', 'message': 'ANTHROPIC_API_KEY not set'})}\n\n"
        return

    geo = con.execute(
        "SELECT county_name, population FROM geographies WHERE fips = ?", [fips]
    ).fetchone()
    cov = con.execute(
        "SELECT mmr_coverage_pct FROM vaccination_coverage WHERE fips = ? ORDER BY school_year DESC LIMIT 1",
        [fips],
    ).fetchone()

    county_name = geo[0] if geo else fips
    population  = geo[1] if geo else "unknown"
    coverage    = cov[0] if cov else "unknown"

    params = sim_result.get("params", {})
    prompt = f"""Interpret this SEIR simulation for {county_name} County (population {population:,} if numeric).

SIMULATION INPUTS:
  Population:      {population}
  MMR coverage:    {coverage}%
  R₀:              {params.get('R0', 'N/A')}
  Vaccine efficacy: {params.get('vaccine_efficacy', 0.97) * 100:.0f}%
  Seed cases:      {params.get('seed_cases', 1)}
  Days simulated:  {params.get('days', 180)}

SIMULATION OUTPUTS:
  Peak infectious day:  Day {sim_result.get('peak_day')}
  Peak infected count:  {sim_result.get('peak_infected'):,.0f}
  Total attack rate:    {sim_result.get('total_attack_rate', 0) * 100:.1f}% of susceptibles
  Herd immunity threshold: {sim_result.get('herd_immunity_threshold')}% needed
  Population above threshold: {sim_result.get('reached_herd_immunity')}

Write your interpretation now."""

    client = anthropic.Anthropic(api_key=api_key)
    try:
        with client.messages.stream(
            model=MODEL,
            max_tokens=1400,
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            thinking={"type": "adaptive"},
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'type': 'text', 'delta': text})}\n\n"
    except anthropic.APIError as exc:
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        return

    yield "data: [DONE]\n\n"
