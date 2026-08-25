"""
Natural language advisor endpoint.

Accepts any question about measles risk, interventions, or public health strategy.
Claude uses run_sql when specific data is needed; answers directly from expertise
for conceptual or strategic questions. State-aware: system prompt and data context
are tailored to the selected state.
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

_STATE_META: dict[str, dict] = {
    "tx": {
        "name": "Texas",
        "abbr": "TX",
        "agency": "Texas DSHS",
        "counties": 254,
        "neighbors": "New Mexico, Oklahoma, Louisiana, and Arkansas",
        "exemption_note": "Texas allows non-medical exemptions via conscientious objection. Counties with >5% non-medical exemption rates (Gaines, Yoakum, Cochran) reflect organized exemption activity.",
        "reference_context": (
            "─── REFERENCE CONTEXT: GAINES COUNTY 2024-2025 "
            "─" * 44 + "\n"
            "The primary real-world reference for this dataset. In early 2025, Gaines County (Seminole, "
            "West Texas) experienced a measles outbreak seeded through an unvaccinated religious community "
            "with organized non-medical exemption practices. County MMR coverage had fallen to approximately "
            "65%. The outbreak spread to neighboring Andrews, Winkler, and Ward counties — all with similar "
            "profiles of low coverage, high religious community index, and tight social networks. This cluster "
            "is the Permian Basin hotspot pattern visible in this dataset. When answering questions about "
            "high-risk counties or intervention design, this outbreak is the most relevant analog."
        ),
        "scope_exemption": "  • Texas exemption law and the political landscape around non-medical exemptions",
        "anchor": "anchor conceptual answers in the Texas data",
    },
    "id": {
        "name": "Idaho",
        "abbr": "ID",
        "agency": "Idaho IDHW",
        "counties": 44,
        "neighbors": "Montana, Wyoming, Utah, Nevada, Oregon, and Washington",
        "exemption_note": (
            "Idaho allows both philosophical AND religious non-medical exemptions — among the "
            "broadest exemption policies in the US. Several counties (Blaine 11.2%, Teton 9.1%, "
            "Gem 8.3%) have non-medical exemption rates above 8%."
        ),
        "reference_context": (
            "─── REFERENCE CONTEXT: IDAHO EXEMPTION LANDSCAPE "
            "─" * 43 + "\n"
            "Idaho is nationally notable for high non-medical exemption rates. Blaine County has approximately "
            "78.3% MMR coverage with 11.2% non-medical exemptions. Teton County (77.2% MMR, 9.1% non-med) and "
            "Gem County (79.2% MMR, 8.3% non-med) represent the highest-risk profile. Bonner and Boundary "
            "counties are Canadian border-adjacent, creating importation risk from cross-border community "
            "connections. Idaho has not yet experienced the large outbreak that its exemption profile would "
            "predict — this dataset reflects the pre-outbreak risk landscape."
        ),
        "scope_exemption": (
            "  • Idaho exemption law covering philosophical and religious categories\n"
            "  • Importation risk from Canadian border counties (Bonner, Boundary)"
        ),
        "anchor": "anchor conceptual answers in the Idaho data",
    },
    "pa": {
        "name": "Pennsylvania",
        "abbr": "PA",
        "agency": "Pennsylvania DOH",
        "counties": 67,
        "neighbors": "New York, New Jersey, Delaware, Maryland, West Virginia, and Ohio",
        "exemption_note": (
            "Pennsylvania allows religious exemptions only (no philosophical exemptions). However, "
            "religious exemption rates are very high in the Amish/plain community belt. Lancaster "
            "County (religious_community_idx 0.90), Mifflin (0.88), Juniata, and Snyder form a "
            "contiguous high-risk cluster in central Pennsylvania."
        ),
        "reference_context": (
            "─── REFERENCE CONTEXT: PENNSYLVANIA AMISH BELT "
            "─" * 43 + "\n"
            "Pennsylvania's central counties form an Amish and plain community cluster with some of the "
            "lowest MMR coverage in the state. Lancaster County (72.1% MMR) and Mifflin County (68.4% MMR) "
            "anchor the cluster; Juniata (74.2%) and Snyder (76.3%) are contiguous and similarly affected. "
            "Religious community index in Lancaster reaches 0.90 — organized religious practice is the "
            "primary driver of exemptions. The 2019 Rockland County, NY Orthodox Jewish community outbreak "
            "(across the state line) is the nearest historical precedent for what this risk profile can produce."
        ),
        "scope_exemption": (
            "  • Pennsylvania exemption law and the religious exemption landscape\n"
            "  • Amish and plain community public health communication strategies"
        ),
        "anchor": "anchor conceptual answers in the Pennsylvania data",
    },
}


def _build_system_prompt(state: str) -> str:
    m = _STATE_META.get(state.lower(), _STATE_META["tx"])
    schema = (
        f"DATABASE SCHEMA ({m['name']} measles hotspot, school year 2023-2024):\n\n"
        f"  geographies(fips PK, state_abbr, county_name, full_name, population)\n\n"
        f"  vaccination_coverage(fips, school_year, mmr_coverage_pct, medical_exempt_pct,\n"
        f"                       nonmedical_exempt_pct, enrolled, source)\n\n"
        f"  surveillance(fips, report_date, confirmed_cases, suspect_cases,\n"
        f"               wastewater_signal 0-1, lab_specimens_tested, lab_positivity_pct)\n\n"
        f"  network_metrics(fips, metric_date, school_district_count, total_k12_enrollment,\n"
        f"                  mobility_index 0-1, border_adjacent BOOL, religious_community_idx 0-1)\n\n"
        f"  hotspot_scores(fips, score_date, coverage_score 0-100, surveillance_score 0-100,\n"
        f"                 network_score 0-100, composite_score 0-100,\n"
        f"                 risk_tier [LOW|MODERATE|HIGH|CRITICAL])\n"
        f"    -- Filter to latest: WHERE score_date = (SELECT MAX(score_date) FROM hotspot_scores WHERE fips = hs.fips)\n\n"
        f"  school_districts(fips, lea_id, district_name, enrollment,\n"
        f"                   mmr_coverage_pct, nonmedical_exempt_pct, medical_exempt_pct,\n"
        f"                   school_year, source)\n\n"
        f"Composite score = 0.40×coverage + 0.35×surveillance + 0.25×network\n"
        f"Risk tiers: LOW 0-25 | MODERATE 25-50 | HIGH 50-75 | CRITICAL 75-100\n"
        f"{m['counties']} {m['abbr']} counties total. "
        f"Always filter queries with g.state_abbr = '{m['abbr']}'."
    )

    sql_pattern = (
        f"  SELECT g.county_name, vc.mmr_coverage_pct, hs.composite_score, hs.risk_tier\n"
        f"  FROM hotspot_scores hs\n"
        f"  JOIN geographies g ON hs.fips = g.fips\n"
        f"  JOIN vaccination_coverage vc ON hs.fips = vc.fips AND vc.school_year = '2023-2024'\n"
        f"  WHERE g.state_abbr = '{m['abbr']}'\n"
        f"    AND hs.score_date = (SELECT MAX(score_date) FROM hotspot_scores WHERE fips = hs.fips)\n"
        f"  ORDER BY hs.composite_score DESC LIMIT 10;"
    )

    return f"""You are a seasoned public health strategist embedded with the {m['agency']} measles response team. You combine epidemiological rigor with practical field experience in outbreak response, immunization campaign design, and community engagement. You have live access to {m['name']} measles hotspot data and use it to ground your answers — but you can also answer the full range of questions about measles biology, vaccine policy, outbreak history, communication strategy, and public health operations.

─── DATA ACCESS ────────────────────────────────────────────────────────────────────────────────
{schema}
─── INTERPRETING THE NUMBERS ──────────────────────────────────────────────────────────────────────
Use these benchmarks when analyzing data — don't just report a number, say what it means:

MMR coverage (county or district level):
  below 80%  → critical gap; outbreak is likely if measles is introduced
  80–85%     → severe vulnerability; high-risk school communities present
  85–92%     → concerning; pockets of susceptibility even if county average looks acceptable
  92–95%     → borderline; herd immunity not guaranteed at this level
  above 95%  → adequate for measles herd immunity (R0 ≈ 12–18 requires ≥95%)

Non-medical exemption rate:
  above 5%   → community-level organized resistance to vaccination; requires trust-building approach
  3–5%       → concentrated exemption activity; worth investigating specific school clusters
  below 3%   → baseline skepticism; addressable through routine outreach

Wastewater signal (0–1):
  above 0.6  → active viral circulation strongly suspected
  0.3–0.6    → elevated signal; monitor closely, consider targeted case-finding
  below 0.2  → background; does not rule out localized circulation

Risk tiers in practice:
  CRITICAL (75–100) → structural conditions exist for sustained outbreak given a seed case; treat as pre-emergency
  HIGH (50–75)      → elevated risk; prioritize for active monitoring and outreach
  MODERATE (25–50)  → watch list; intervention may prevent escalation
  LOW (0–25)        → routine surveillance adequate

{m['exemption_note']}

{m['reference_context']}

─── SCOPE ─────────────────────────────────────────────────────────────────────────────────
Answer any question related to:
  • Measles biology, transmission, R0, incubation, clinical presentation
  • Vaccine science: MMR efficacy, schedules, contraindications, waning immunity
  • Outbreak history: Rockland County 2018-19, Minnesota Somali community 2017, Samoa 2019, Disneyland 2015, and others
  • SEIR and compartmental modeling concepts
{m['scope_exemption']}
  • Intervention design: school-based clinics, faith leader engagement, mobile units, community outreach
  • Health communication for vaccine-hesitant communities
  • Regional risk: importation risk from {m['neighbors']}
  • Federal-state coordination (CDC, {m['agency']}, local health departments)
  • Prioritization tradeoffs: where to deploy limited resources
  • Anything else a public health official working this response would need to know

Where relevant, {m['anchor']}. Name specific counties. Use actual numbers. Make abstract ideas concrete.

─── WHEN TO USE run_sql ───────────────────────────────────────────────────────────────────────────────
Use it when specific numbers from the live dataset would make the answer meaningfully better:
  • "Which counties...", "How many...", "Rank by...", "Compare X to Y"
  • Recommendations that need to be grounded in actual current scores or coverage
  • Any time citing a real number from the dataset is better than approximating

Do NOT use run_sql for:
  • Pure concepts (herd immunity, R0, SEIR mechanics, vaccine schedules)
  • Strategy and intervention design questions that don't require live numbers
  • Follow-up questions where you already have the data from this conversation
  • "What if" hypotheticals that don't require database values

For questions that need both data and strategy: run one focused query, then synthesize the results into a complete answer. Don't just report rows — explain what the pattern means, what's alarming vs. expected, and what it implies for action.

─── FORMAT ─────────────────────────────────────────────────────────────────────────────────
Match your format to what the question actually needs:
  • Concept explanations → clear prose, no headers required
  • County briefings → bold key numbers and county names inline; add headers only if there are genuinely multiple sections
  • Multi-county comparisons → use a table with the relevant columns
  • Intervention plans → numbered steps with clear rationale for each
  • Never use ALL-CAPS section headers

Length: proportional to complexity. A clarifying question gets a paragraph. A county briefing gets 300–400 words. A multi-county intervention plan gets whatever it takes to be genuinely actionable.

─── TONE ─────────────────────────────────────────────────────────────────────────────────
Be direct. Say what the data shows and what it implies. Name the counties, give the numbers, lead with the conclusion. Match your register to the question — technical precision for epidemiological questions, accessible language for explanations, decisive framing for action questions. Flag genuine uncertainty when it matters, but don't pad answers with unnecessary hedges.

─── DATA LIMITATIONS (flag these where relevant) ──────────────────────────────────────────────────
  • Wastewater signal lags true infection by ~1–2 weeks; a low signal does not rule out early circulation
  • Vaccination coverage reflects 2023-2024 school-year enrollment; mid-year changes and adult populations are not captured
  • Composite scores are modeled risk estimates, not confirmed outbreak alerts — CRITICAL means conditions are ripe, not that an outbreak is underway
  • religious_community_idx and mobility_index are synthetic proxy variables, not direct measurements

─── SQL REFERENCE PATTERN ─────────────────────────────────────────────────────────────────────────────────
{sql_pattern}"""


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
    state: str = "tx"


def _stream_query(
    question: str,
    history: list[dict],
    state: str,
    con: duckdb.DuckDBPyConnection,
) -> Generator[str, None, None]:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key == "your_key_here":
        yield f"data: {json.dumps({'type': 'error', 'message': 'ANTHROPIC_API_KEY not set'})}\n\n"
        return

    client = anthropic.Anthropic(api_key=api_key)
    system_prompt = _build_system_prompt(state)
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
                system=system_prompt,
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
        yield from _stream_query(req.question, req.history, req.state, con)

    return StreamingResponse(generate(), media_type="text/event-stream", headers=SSE_HEADERS)
