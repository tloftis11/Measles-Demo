"""
Measles news intelligence briefing using Claude with web search.

Searches for recent measles news relevant to the selected state and synthesizes a
structured intelligence briefing. Results are meant to be cached — call
stream_news_briefing(state) and accumulate the full text, then store it.
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

_STATE_CONFIG: dict[str, dict] = {
    "tx": {
        "name": "Texas",
        "agency": "Texas DSHS",
        "searches": [
            "Measles cases confirmed Texas 2025 OR 2026",
            "Measles outbreak United States 2025 OR 2026",
            "Measles New Mexico Oklahoma Louisiana 2025 OR 2026",
            "Measles Mexico border 2025 OR 2026",
            "Texas vaccination exemption law 2025 OR 2026",
            "Measles CDC MMWR 2025 OR 2026",
        ],
        "neighbors": "neighboring states (New Mexico, Oklahoma, Louisiana)",
        "importation": "importation risk from Mexico/international",
        "policy_context": "Texas exemption law",
        "reference_outbreak": "Gaines County 2024-2025 Permian Basin cluster",
    },
    "id": {
        "name": "Idaho",
        "agency": "Idaho IDHW",
        "searches": [
            "Measles cases Idaho 2025 OR 2026",
            "Measles outbreak Pacific Northwest 2025 OR 2026",
            "Measles Washington Oregon Montana Wyoming 2025 OR 2026",
            "Measles Canada importation 2025 OR 2026",
            "Idaho vaccination philosophical exemption 2025 OR 2026",
            "Measles CDC MMWR 2025 OR 2026",
        ],
        "neighbors": "neighboring states (Washington, Oregon, Montana, Wyoming)",
        "importation": "importation risk from Canada (Bonner and Boundary counties are border-adjacent)",
        "policy_context": "Idaho's philosophical and religious exemption law",
        "reference_outbreak": "high non-medical exemption communities in Blaine and Teton counties",
    },
    "pa": {
        "name": "Pennsylvania",
        "agency": "Pennsylvania DOH",
        "searches": [
            "Measles cases Pennsylvania 2025 OR 2026",
            "Measles outbreak Northeast United States 2025 OR 2026",
            "Measles New York New Jersey Ohio 2025 OR 2026",
            "Measles Amish community 2025 OR 2026",
            "Pennsylvania vaccination religious exemption 2025 OR 2026",
            "Measles CDC MMWR 2025 OR 2026",
        ],
        "neighbors": "neighboring states (New York, New Jersey, Ohio, Maryland)",
        "importation": "importation risk from New York/New Jersey metro communities",
        "policy_context": "Pennsylvania religious exemption law",
        "reference_outbreak": "Lancaster-Mifflin Amish belt high-risk cluster",
    },
}


def _build_prompts(state: str) -> tuple[str, str]:
    c = _STATE_CONFIG.get(state.lower(), _STATE_CONFIG["tx"])
    searches_formatted = "\n".join(f"{i+1}. {s}" for i, s in enumerate(c["searches"]))

    system = f"""You are a public health intelligence analyst monitoring measles activity for the {c['agency']} response team.

Your job: search for recent measles news (last 60 days), evaluate relevance to {c['name']} public health, and write a structured intelligence briefing. Be an analyst, not an aggregator — synthesize what you find into actionable intelligence, not a list of links.

SEARCH STRATEGY
Run searches in this order. Each search should use a specific, targeted query:
{searches_formatted}

Only search what's necessary. Stop when you have enough for a thorough briefing.

BRIEFING FORMAT
Write sections using ALL CAPS headers. Only include a section if you found genuinely relevant content. If a section has nothing to report, omit it entirely rather than writing a placeholder.

ACTIVE CASES & OUTBREAKS
Confirmed or probable cases in {c['name']}. Include: case counts, locations, affected populations (age, vaccination status if reported), outbreak status (ongoing vs. contained).

REGIONAL & IMPORTATION RISK
Outbreaks in {c['neighbors']} or {c['importation']}. Note any travel-linked cases or cross-border community connections.

NATIONAL CONTEXT
Significant US outbreaks outside the region that reflect overall measles pressure or that could reach {c['name']} through travel networks.

POLICY & LEGISLATION
{c['policy_context']} movement, {c['agency']} guidance updates, school requirement changes, federal or state legislation relevant to {c['name']} vaccination policy.

SURVEILLANCE SIGNALS
Any publicly reported wastewater findings, serological surveys, or laboratory data. Note if wastewater data lags clinical detection by 1-2 weeks.

WHAT TO WATCH
2-3 sentences: your read on what's emerging, what could escalate, and where attention should be focused in the next 30 days. Reference relevant {c['name']} context (e.g., {c['reference_outbreak']}) where applicable.

SOURCES
List each source you drew from, one per line, in this format:
Title — Publication (Date) — URL

CONTENT STANDARDS
- Cite specific numbers: case counts, county names, dates
- Note when a case is confirmed vs. probable/suspect
- Flag age and vaccination status when reported — most cases are in unvaccinated individuals
- Note geographic specificity: location precision matters
- Do not fabricate or extrapolate beyond what sources say
- If you searched and genuinely found nothing for a section, omit that section
- Keep the briefing under 600 words excluding the sources list"""

    user = (
        f"Search for recent measles news and write a {c['agency']} intelligence briefing. "
        f"Today's date is {{today}}. Focus on the last 60 days. Cover: {c['name']} cases, "
        f"{c['neighbors'].replace('neighboring states (', '').rstrip(')')} outbreaks, "
        f"{c['importation']}, and {c['name']} vaccination policy news. "
        f"Synthesize what you find into a structured briefing following the format in your instructions."
    )

    return system, user


def extract_sources(briefing: str) -> list[str]:
    """Extract URLs from briefing text for structured source display."""
    url_re = re.compile(r'https?://[^\s\)\],"\'<>]+')
    seen: dict[str, None] = {}
    for url in url_re.findall(briefing):
        url = url.rstrip(".")
        seen[url] = None
    return list(seen.keys())


def stream_news_briefing(state: str = "tx") -> Generator[str, None, None]:
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
    system_prompt, user_prompt_template = _build_prompts(state)

    accumulated: list[str] = []

    try:
        with client.messages.stream(
            model=MODEL,
            max_tokens=4000,
            system=system_prompt,
            tools=[
                {"type": "web_search_20260209", "name": "web_search"},
                {"type": "web_fetch_20260209", "name": "web_fetch"},
            ],
            messages=[{"role": "user", "content": user_prompt_template.format(today=today)}],
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
