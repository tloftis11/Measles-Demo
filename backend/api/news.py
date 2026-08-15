"""
News intelligence briefing endpoints.

GET  /api/news         — returns cached briefing + freshness flag
POST /api/news/refresh — streams a fresh briefing (SSE), caches when complete
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from db import get_connection
from ai.news_analyst import stream_news_briefing, CACHE_TTL_HOURS

router = APIRouter(prefix="/api/news", tags=["news"])

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _get_cached(con) -> dict | None:
    """Return cached briefing dict or None if no cache exists."""
    row = con.execute(
        "SELECT fetched_at, briefing, sources_json FROM news_cache WHERE id = 1"
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


def _save_cache(con, fetched_at: str, briefing: str, sources: list[str]) -> None:
    con.execute(
        """
        INSERT OR REPLACE INTO news_cache (id, fetched_at, briefing, sources_json)
        VALUES (1, ?, ?, ?)
        """,
        [fetched_at, briefing, json.dumps(sources)],
    )


@router.get("")
def get_news():
    """Return cached briefing. is_fresh=False means the caller should trigger a refresh."""
    con = get_connection()
    cached = _get_cached(con)
    if not cached:
        return {"is_fresh": False, "fetched_at": None, "briefing": None, "sources": []}
    return {
        "is_fresh": _is_fresh(cached["fetched_at"]),
        "fetched_at": cached["fetched_at"],
        "briefing": cached["briefing"],
        "sources": cached["sources"],
    }


@router.post("/refresh")
def refresh_news():
    """Stream a fresh intelligence briefing, then cache the result."""
    con = get_connection()

    def generate():
        for event in stream_news_briefing():
            yield event
            # Intercept the 'done' event to save to cache
            if event.startswith("data: ") and not event.startswith("data: [DONE]"):
                raw = event[6:].strip()
                try:
                    parsed = json.loads(raw)
                    if parsed.get("type") == "done":
                        _save_cache(
                            con,
                            parsed["fetched_at"],
                            parsed["briefing"],
                            parsed.get("sources", []),
                        )
                except (json.JSONDecodeError, KeyError):
                    pass

    return StreamingResponse(generate(), media_type="text/event-stream", headers=SSE_HEADERS)
