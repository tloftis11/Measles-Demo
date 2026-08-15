"""
Measles news intelligence briefing using Claude with web search.

Searches for recent measles news relevant to Texas and synthesizes a
structured intelligence briefing. Results are meant to be cached —
call stream_news_briefing() and accumulate the full text, then store it.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Generator

import anthropic

MODEL = "claude-opus-5"
CACHE_TTL_HOURS = 6

SYSTEM = """You are a public health intelligence analyst monitoring measles activity for the Texas DSHS response team.

Your job: search for recent measles news (last 60 days), evaluate relevance to Texas public health, and write a structured intelligence briefing. Be a analyst, not an aggregator — synthesize what you find into actionable intelligence, not a list of links.

SEARCH STRATEGY
Run searches in this order. Each search should use a specific, targeted query:
1. Measles cases confirmed Texas 2025 OR 2026
2. Measles outbreak United States 2025 OR 2026
3. Measles New Mexico Oklahoma Louisiana 2025 OR 2026 (neighboring states)
4. Measles Mexico border 2025 OR 2026 (importation risk)
5. Texas vaccination exemption law 2025 OR 2026
6. Measles CDC MMWR 2025 OR 2026

Only search what's necessary. Stop when you have enough for a thorough briefing.

BRIEFING FORMAT
Write sections using ALL CAPS headers. Only include a section if you found genuinely relevant content. If a section has nothing to report, omit it entirely rather than writing a placeholder.

ACTIVE CASES & OUTBREAKS
Confirmed or probable cases in Texas. Include: case counts, locations, affected populations (age, vaccination status if reported), outbreak status (ongoing vs. contained).

REGIONAL & IMPORTATION RISK
Outbreaks in neighboring states (New Mexico, Oklahoma, Louisiana) or Mexico that create importation risk. Note any travel-linked cases or cross-border community connections.

NATIONAL CONTEXT
Significant US outbreaks outside the region that reflect overall measles pressure or that could reach Texas through travel networks.

POLICY & LEGISLATION
Texas exemption law movement, DSHS guidance updates, school requirement changes, federal or state legislation relevant to Texas vaccination policy.

SURVEILLANCE SIGNALS
Any publicly reported wastewater findings, serological surveys, or laboratory data. Note if wastewater data lags clinical detection by 1-2 weeks.

WHAT TO WATCH
2-3 sentences: your read on what's emerging, what could escalate, and where attention should be focused in the next 30 days.

SOURCES
List each source you drew from, one per line, in this format:
Title — Publication (Date) — URL

CONTENT STANDARDS
- Cite specific numbers: case counts, county names, dates
- Note when a case is confirmed vs. probable/suspect
- Flag age and vaccination status when reported — most cases are in unvaccinated individuals
- Note geographic specificity: a Dallas case is different from a Gaines County case
- Do not fabricate or extrapolate beyond what sources say
- If you searched and genuinely found nothing for a section, omit that section
- Keep the briefing under 600 words excluding the sources list"""

USER_PROMPT = """Search for recent measles news and write a Texas DSHS intelligence briefing. Today's date is {today}. Focus on the last 60 days. Cover: Texas cases, neighboring state outbreaks, importation risk from Mexico/international, and Texas vaccination policy news. Synthesize what you find into a structured briefing following the format in your instructions."""


def extract_sources(briefing: str) -> list[str]:
    """Extract URLs from briefing text for structured source display."""
    url_re = re.compile(r'https?://[^\s\)\],"\'<>]+')
    seen: dict[str, None] = {}
    for url in url_re.findall(briefing):
        url = url.rstrip(".")
        seen[url] = None
    return list(seen.keys())


def stream_news_briefing() -> Generator[str, None, None]:
    """
    Yield SSE events: text deltas while streaming, then a 'done' event with
    the full briefing text and extracted sources when complete.

    Caller should accumulate 'text' deltas + listen for 'done' to get
    the final result for caching.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key == "your_key_here":
        yield f"data: {json.dumps({'type': 'error', 'message': 'ANTHROPIC_API_KEY not set'})}\n\n"
        return

    client = anthropic.Anthropic(api_key=api_key)
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")

    accumulated: list[str] = []

    try:
        with client.messages.stream(
            model=MODEL,
            max_tokens=4000,
            system=SYSTEM,
            tools=[
                {"type": "web_search_20260209", "name": "web_search"},
                {"type": "web_fetch_20260209", "name": "web_fetch"},
            ],
            messages=[{"role": "user", "content": USER_PROMPT.format(today=today)}],
        ) as stream:
            for text in stream.text_stream:
                accumulated.append(text)
                yield f"data: {json.dumps({'type': 'text', 'delta': text})}\n\n"

    except anthropic.APIError as exc:
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        return
    except Exception as exc:
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        return

    briefing = "".join(accumulated)
    sources = extract_sources(briefing)
    fetched_at = datetime.now(timezone.utc).isoformat()

    yield f"data: {json.dumps({'type': 'done', 'fetched_at': fetched_at, 'briefing': briefing, 'sources': sources})}\n\n"
    yield "data: [DONE]\n\n"
