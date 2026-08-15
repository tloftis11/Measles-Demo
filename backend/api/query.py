"""
Natural language advisor endpoint.

Accepts a question about Texas measles risk, interventions, or public health
strategy. Claude uses the run_sql tool when specific data is needed, then
synthesizes findings into a plain-English answer.
"""
from __future__ import annotations

import json
import os
from typing import Any, Generator

import anthropic
import duckdb
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from db import get_connection

router = APIRouter(prefix="/api/query", tags=["query"])

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

MODEL = "claude-opus-5"

SCHEMA_DESCRIPTION = """
DATABASE SCHEMA (Texas measles hotspot, school year 2023-2024):

  geographies(fips PK, state_abbr, county_name, full_name, population)

  vaccination_coverage(fips, school_year, mmr_coverage_pct, medical_exempt_pct,
                       nonmedical_exempt_pct, enrolled, source)

  surveillance(fips, report_date, confirmed_cases, suspect_cases,
               wastewater_signal 0-1, lab_specimens_tested, lab_positivity_pct)

  network_metrics(fips, metric_date, school_district_count, total_k12_enrollment,
                  mobility_index 0-1, border_adjacent BOOL, religious_community_idx 0-1)

  hotspot_scores(fips, score_date, coverage_score 0-100, surveillance_score 0-100,
                 network_score 0-100, composite_score 0-100,
                 risk_tier [LOW|MODERATE|HIGH|CRITICAL])

  score_history(fips, week_start, composite_score, coverage_score,
                surveillance_score, network_score, risk_tier)

Composite score = 0.40×coverage + 0.35×surveillance + 0.25×network
Risk tiers: LOW 0-25 | MODERATE 25-50 | HIGH 50-75 | CRITICAL 75-100
Herd immunity threshold for measles: 95% MMR coverage (R0 ≈ 12-18)
254 TX counties total.

KEY REGIONAL PATTERNS IN THE DATA:
- Permian Basin cluster (west TX): Gaines, Andrews, Ward, Winkler counties — LOW MMR, trending upward in risk
- Border counties (TX-Mexico): elevated cross-border exposure, high mobility
- Urban cores (Harris, Travis, Dallas, Bexar): higher coverage but large absolute populations
"""

SYSTEM = f"""You are a senior CDC epidemiologist and public health advisor embedded with the Texas DSHS measles response team. You support outbreak prevention strategy, intervention planning, and data analysis.

{SCHEMA_DESCRIPTION}

WHAT YOU CAN DO:
1. QUERY & ANALYZE: Use run_sql to pull live data — risk scores, MMR coverage, case trends, network metrics — then interpret findings with epidemiological context.
2. PRIORITIZE: Identify which counties, school districts, or regions need immediate attention and explain why.
3. DESIGN INTERVENTIONS: Recommend specific, actionable campaigns — vaccination clinics, school outreach, exemption audits, community engagement — tailored to each county's risk profile.
4. ASSESS TRAJECTORIES: Estimate outbreak potential from current data; explain how coverage gaps translate to susceptible populations and outbreak size.
5. EXPLAIN CONCEPTS: Answer questions about measles epidemiology, SEIR models, herd immunity, wastewater surveillance, and public health strategy from expertise — no SQL needed for these.

ANSWERING APPROACH:
- For questions needing specific numbers: call run_sql first, then synthesize the data into your answer.
- For intervention/strategy questions: query relevant counties or metrics, then give concrete, prioritized recommendations.
- For conceptual or "what if" questions: draw on expertise; SQL is optional.
- You may run multiple queries to build a complete picture before answering.

FORMAT:
- Use ALL CAPS section headers (e.g., PRIORITY COUNTIES, RECOMMENDED ACTIONS, RISK ASSESSMENT) for structured answers.
- Name specific counties and cite actual numbers from the data.
- For action plans: state which counties, which intervention type, and the rationale.
- Responses can be as detailed as the question requires — don't truncate complex analyses."""

TOOLS = [
    {
        "name": "run_sql",
        "description": (
            "Execute a read-only SQL SELECT query against the measles hotspot DuckDB. "
            "Returns results as JSON. Use this to get specific county data, rankings, "
            "coverage rates, scores, trends, or any other quantitative information needed "
            "to ground your answer in the actual data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "A valid DuckDB SQL SELECT statement. JOINs, CTEs, and aggregations are supported. No INSERT/UPDATE/DELETE.",
                },
                "description": {
                    "type": "string",
                    "description": "One sentence describing what this query retrieves.",
                },
            },
            "required": ["sql", "description"],
        },
    }
]


def _run_sql(sql: str, con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    normalized = sql.strip().upper()
    if not normalized.startswith("SELECT") and not normalized.startswith("WITH"):
        raise ValueError("Only SELECT queries are allowed.")
    rows = con.execute(sql).fetchall()
    cols = [d[0] for d in con.description]
    return [dict(zip(cols, row)) for row in rows]


class QueryRequest(BaseModel):
    question: str
    history: list[dict] = []


def _stream_query(
    question: str,
    history: list[dict],
    con: duckdb.DuckDBPyConnection,
) -> Generator[str, None, None]:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key == "your_key_here":
        yield f"data: {json.dumps({'type': 'error', 'message': 'ANTHROPIC_API_KEY not set'})}\n\n"
        return

    client = anthropic.Anthropic(api_key=api_key)
    messages = list(history) + [{"role": "user", "content": question}]

    # Agentic loop — Claude may call run_sql one or more times
    loop_count = 0
    while loop_count < 6:  # safety cap
        loop_count += 1

        # Keepalive comment between iterations so proxies don't close the connection
        if loop_count > 1:
            yield ": keepalive\n\n"

        with client.messages.stream(
            model=MODEL,
            max_tokens=3000,
            system=SYSTEM,
            tools=TOOLS,
            messages=messages,
            thinking={"type": "adaptive"},
        ) as stream:
            tool_uses: list[dict] = []

            for event in stream:
                if not hasattr(event, "type"):
                    continue
                if event.type == "content_block_start":
                    if (
                        hasattr(event, "content_block")
                        and getattr(event.content_block, "type", None) == "tool_use"
                    ):
                        tool_uses.append({
                            "id": event.content_block.id,
                            "name": event.content_block.name,
                        })
                elif event.type == "content_block_delta":
                    delta = event.delta
                    if getattr(delta, "type", None) == "text_delta" and delta.text:
                        yield f"data: {json.dumps({'type': 'text', 'delta': delta.text})}\n\n"

            final = stream.get_final_message()

        stop_reason = final.stop_reason

        if stop_reason != "tool_use":
            break

        # Build assistant content block (include thinking blocks for context continuity)
        assistant_content = []
        for block in final.content:
            if block.type == "thinking":
                assistant_content.append({"type": "thinking", "thinking": block.thinking})
            elif block.type == "text":
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                assistant_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        messages.append({"role": "assistant", "content": assistant_content})

        tool_results = []
        for block in final.content:
            if block.type != "tool_use":
                continue
            sql = block.input.get("sql", "")
            desc = block.input.get("description", sql[:80])
            yield f"data: {json.dumps({'type': 'tool_call', 'description': desc})}\n\n"

            try:
                rows = _run_sql(sql, con)
                result_text = json.dumps(rows[:100])
                if len(rows) > 100:
                    result_text += f"\n[...{len(rows) - 100} more rows omitted]"
            except Exception as exc:
                result_text = json.dumps({"error": str(exc)})

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result_text,
            })

        messages.append({"role": "user", "content": tool_results})

    yield "data: [DONE]\n\n"


@router.post("")
def query(req: QueryRequest):
    con = get_connection()

    def generate():
        yield from _stream_query(req.question, req.history, con)

    return StreamingResponse(generate(), media_type="text/event-stream", headers=SSE_HEADERS)
