"""
Natural language advisor endpoint.

Accepts any question about Texas measles risk, interventions, or public health
strategy. Claude uses run_sql when specific data is needed; answers directly
from expertise for conceptual or strategic questions.
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
    -- Use MAX(score_date) to get the latest score per county.
    -- Multiple rows per county: one per scoring date, so filter by date.

Composite score = 0.40×coverage + 0.35×surveillance + 0.25×network
Risk tiers: LOW 0-25 | MODERATE 25-50 | HIGH 50-75 | CRITICAL 75-100
Herd immunity threshold for measles: 95% MMR coverage (R0 ≈ 12-18)
254 TX counties total.

KEY PATTERNS:
- West TX Permian Basin cluster: Gaines, Andrews, Ward, Winkler — low MMR, rising risk
- Border counties (TX-Mexico): elevated cross-border exposure and mobility
- Urban cores (Harris, Travis, Dallas, Bexar): higher coverage, large absolute populations
"""

SYSTEM = f"""You are a senior CDC epidemiologist and public health advisor embedded with the Texas DSHS measles response team.

{SCHEMA_DESCRIPTION}

WHEN TO USE run_sql (use it for these):
- Questions that require specific county names, numbers, rankings, or comparisons from the dataset
- "Which counties...", "How many...", "What are the top...", "Compare X to Y"
- Recommendations that must be grounded in actual risk scores or coverage data

WHEN TO ANSWER DIRECTLY — do NOT call run_sql for these:
- Conceptual questions: what is herd immunity, how does SEIR work, what is R0, measles epidemiology
- General intervention tactics: types of vaccination campaigns, how to approach exemption communities, outreach strategies
- "What if" hypotheticals that don't require database numbers
- Follow-up questions where you already have the data from this conversation

FOR QUESTIONS THAT NEED BOTH DATA AND STRATEGY:
- Run one focused query to get the key numbers, then give the full strategic answer.
- Prefer a single well-constructed query over multiple back-and-forth queries.

EXAMPLE SQL PATTERN for latest scores:
  SELECT g.county_name, vc.mmr_coverage_pct, hs.composite_score, hs.risk_tier
  FROM hotspot_scores hs
  JOIN geographies g ON hs.fips = g.fips
  JOIN vaccination_coverage vc ON hs.fips = vc.fips AND vc.school_year = '2023-2024'
  WHERE hs.score_date = (SELECT MAX(score_date) FROM hotspot_scores WHERE fips = hs.fips)
  ORDER BY hs.composite_score DESC LIMIT 10;

FORMAT YOUR ANSWERS:
- Use ALL CAPS section headers (PRIORITY COUNTIES, RECOMMENDED ACTIONS, RISK ASSESSMENT)
- Name specific counties with actual numbers from queries
- For action plans: county → intervention type → rationale → expected impact
- Be as thorough as the question requires"""

TOOLS = [
    {
        "name": "run_sql",
        "description": (
            "Execute a read-only SQL SELECT query against the measles hotspot DuckDB. "
            "Returns results as JSON rows. Use this only when the answer requires specific "
            "numbers, county names, rankings, or data comparisons from the live dataset."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "A valid DuckDB SQL SELECT statement. JOINs and CTEs are supported. No INSERT/UPDATE/DELETE.",
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

    loop_count = 0
    while loop_count < 5:
        loop_count += 1

        if loop_count > 1:
            yield ": keepalive\n\n"

        try:
            with client.messages.stream(
                model=MODEL,
                max_tokens=3000,
                system=SYSTEM,
                tools=TOOLS,
                messages=messages,
                # No extended thinking — it causes signature serialization failures
                # in multi-turn tool-use loops when thinking blocks are included in history
            ) as stream:
                for event in stream:
                    if not hasattr(event, "type"):
                        continue
                    if event.type == "content_block_delta":
                        delta = event.delta
                        if getattr(delta, "type", None) == "text_delta" and delta.text:
                            yield f"data: {json.dumps({'type': 'text', 'delta': delta.text})}\n\n"

                final = stream.get_final_message()

        except anthropic.APIError as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': f'API error: {exc.message}'})}\n\n"
            return
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
            return

        if final.stop_reason != "tool_use":
            break

        # Serialize assistant turn — only text and tool_use blocks (no thinking blocks)
        assistant_content = []
        for block in final.content:
            if block.type == "text":
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
                if len(rows) > 100:
                    result_text = json.dumps(rows[:100]) + f"\n[...{len(rows) - 100} more rows omitted]"
                else:
                    result_text = json.dumps(rows)
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
