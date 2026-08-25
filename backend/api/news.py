"""
News intelligence briefing endpoints.

GET  /api/news?state=tx         — returns cached briefing + freshness flag
POST /api/news/refresh?state=tx — streams a fresh briefing (SSE), caches when complete
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from db import get_connection
from ai.news_analyst import stream_news_briefing, CACHE_TTL_HOURS

router = APIRouter(prefix="/api/news", tags=["news"])

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

# Map state abbreviation to a stable integer id for the news_cache PRIMARY KEY
_STATE_IDS: dict[str, int] = {"tx": 1, "id": 2, "pa": 3}


def _state_id(state: str) -> int:
    return _STATE_IDS.get(state.lower(), 1)


def _get_cached(con, state: str) -> dict | None:
    """Return cached briefing dict for a state, or None if no cache exists."""
    sid = _state_id(state)
    row = con.execute(
        "SELECT fetched_at, briefing, sources_json FROM news_cache WHERE id = ?",
        [sid],
    ).fetchone()
    if not row:
        return None
    return {"fetched_at": str(row[0]), "briefing": row[1], "sources": json.loads(row[2] or "[]")}


def _is_fresh(fetched_at_str: str) -> bool:
    fetched = datetime.fromisoformat(fetched_at_str)
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - fetched).total_seconds() / 3600
    return age < CACHE_TTL_HOURS


def _save_cache(con, state: str, fetched_at: str, briefing: str, sources: list[str]) -> None:
    sid = _state_id(state)
    con.execute(
        """
        INSERT OR REPLACE INTO news_cache (id, state_abbr, fetched_at, briefing, sources_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        [sid, state.lower(), fetched_at, briefing, json.dumps(sources)],
    )


@router.get("")
def get_news(state: str = Query(default="tx")):
    """Return cached briefing for a state. is_fresh=False means the caller should trigger a refresh."""
    con = get_connection()
    cached = _get_cached(con, state)
    if not cached:
        return {"is_fresh": False, "fetched_at": None, "briefing": None, "sources": []}
    return {
        "is_fresh": _is_fresh(cached["fetched_at"]),
        "fetched_at": cached["fetched_at"],
        "briefing": cached["briefing"],
        "sources": cached["sources"],
    }


@router.post("/refresh")
def refresh_news(state: str = Query(default="tx")):
    """Stream a fresh intelligence briefing for a state, then cache the result."""
    con = get_connection()

    def generate():
        for event in stream_news_briefing(state):
            yield event
            # Intercept the 'done' event to save to cache
            if event.startswith("data: ") and not event.startswith("data: [DONE]"):
                raw = event[6:].strip()
                try:
                    parsed = json.loads(raw)
                    if parsed.get("type") == "done":
                        _save_cache(
                            con,
                            state,
                            parsed["fetched_at"],
                            parsed["briefing"],
                            parsed.get("sources", []),
                        )
                except (json.JSONDecodeError, KeyError):
                    pass

    return StreamingResponse(generate(), media_type="text/event-stream", headers=SSE_HEADERS)
