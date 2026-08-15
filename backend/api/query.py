"""
Natural language query endpoint.

Accepts a user question, sends it to Claude with a `run_sql` tool,
and streams back the result as SSE. Claude calls the tool to query
DuckDB, then writes a plain-English interpretation of the result.
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
Database: measles hotspot DuckDB (Texas, school year 2023-2024)

Tables:
  geographies(fips PK, state_fips, state_abbr, county_name, full_name, population)
  vaccination_coverage(fips, school_year, mmr_coverage_pct, medical_exempt_pct,
                       nonmedical_exempt_pct, enrolled, source)
  surveillance(fips, report_date, confirmed_cases, suspect_cases,
               wastewater_signal 0-1, lab_specimens_tested, lab_positivity_pct, source)
  network_metrics(fips, metric_date, school_district_count, total_k12_enrollment,
                  mobility_index 0-1, border_adjacent BOOL, religious_community_idx 0-1)
  hotspot_scores(fips, score_date, coverage_score 0-100, surveillance_score 0-100,
                 network_score 0-100, composite_score 0-100,
                 risk_tier [LOW|MODERATE|HIGH|CRITICAL], score_components JSON)

Risk tiers: LOW 0-25, MODERATE 25-50, HIGH 50-75, CRITICAL 75-100
Herd immunity threshold for measles: 95% MMR coverage
All data is for Texas. 254 counties total.
"""

SYSTEM = f"""You are a CDC data analyst with access to a measles hotspot database.
Answer the user's question concisely using the run_sql tool to query the data.

{SCHEMA_DESCRIPTION}

Rules:
- Always call run_sql at least once before answering.
- Write only SELECT queries — no INSERT/UPDATE/DELETE.
- Format your final answer as plain text with ALL CAPS section headers when helpful.
- Be specific: include actual county names and numbers from the query results.
- Keep the answer under 350 words.
- Do not include raw SQL in your final answer unless the user asked for it."""

TOOLS = [
    {
        "name": "run_sql",
        "description": "Execute a read-only SQL SELECT query against the measles hotspot DuckDB and return results as JSON.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "A valid DuckDB SQL SELECT statement. No INSERT/UPDATE/DELETE.",
                },
                "description": {
                    "type": "string",
                    "description": "One sentence describing what this query retrieves.",
                },
            },
            "required": ["sql"],
        },
    }
]


def _run_sql(sql: str, con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Execute SQL and return rows as list-of-dicts. Raises on non-SELECT."""
    normalized = sql.strip().upper()
    if not normalized.startswith("SELECT") and not normalized.startswith("WITH"):
        raise ValueError("Only SELECT queries are allowed.")
    rows = con.execute(sql).fetchall()
    cols = [d[0] for d in con.description]
    return [dict(zip(cols, row)) for row in rows]


class QueryRequest(BaseModel):
    question: str
    history: list[dict] = []  # prior [{role, content}] pairs for follow-up


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

    # Agentic loop — Claude may call run_sql multiple times
    while True:
        with client.messages.stream(
            model=MODEL,
            max_tokens=1200,
            system=SYSTEM,
            tools=TOOLS,
            messages=messages,
            thinking={"type": "adaptive"},
        ) as stream:
            tool_uses: list[dict] = []
            text_chunks: list[str] = []

            for event in stream:
                if hasattr(event, "type"):
                    if event.type == "content_block_start":
                        if hasattr(event.content_block, "type"):
                            if event.content_block.type == "tool_use":
                                tool_uses.append({
                                    "id": event.content_block.id,
                                    "name": event.content_block.name,
                                    "input": {},
                                    "_raw_input": "",
                                })
                    elif event.type == "content_block_delta":
                        delta = event.delta
                        if hasattr(delta, "type"):
                            if delta.type == "text_delta":
                                text_chunks.append(delta.text)
                                yield f"data: {json.dumps({'type': 'text', 'delta': delta.text})}\n\n"
                            elif delta.type == "input_json_delta":
                                if tool_uses:
                                    tool_uses[-1]["_raw_input"] += delta.partial_json

            final = stream.get_final_message()

        stop_reason = final.stop_reason

        if stop_reason == "tool_use":
            # Parse accumulated JSON inputs
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
                tool_id = block.id
                tool_input = block.input

                if block.name == "run_sql":
                    sql = tool_input.get("sql", "")
                    desc = tool_input.get("description", "")
                    yield f"data: {json.dumps({'type': 'tool_call', 'description': desc or sql[:80]})}\n\n"
                    try:
                        rows = _run_sql(sql, con)
                        result_text = json.dumps(rows[:50])  # cap at 50 rows
                        if len(rows) > 50:
                            result_text = json.dumps(rows[:50]) + f"\n[...{len(rows)-50} more rows truncated]"
                    except Exception as exc:
                        result_text = json.dumps({"error": str(exc)})

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": result_text,
                    })

            messages.append({"role": "user", "content": tool_results})
            # Loop: Claude will now interpret the results

        else:
            # End turn or max_tokens — done
            break

    yield "data: [DONE]\n\n"


@router.post("")
def query(req: QueryRequest):
    """Stream a Claude Opus natural language query interpretation."""
    con = get_connection()

    def generate():
        yield from _stream_query(req.question, req.history, con)

    return StreamingResponse(generate(), media_type="text/event-stream", headers=SSE_HEADERS)
