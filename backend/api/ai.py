from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Any

from db import get_connection
from ai.analyst import stream_analyst
from ai.district_analyst import stream_district_analyst
from ai.simulation_narrative import stream_narrative

router = APIRouter(prefix="/api/ai", tags=["ai"])

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


class AnalystRequest(BaseModel):
    fips: str
    state: str = "tx"


class DistrictAnalystRequest(BaseModel):
    lea_id: str
    fips: str
    state: str = "tx"


class NarrativeRequest(BaseModel):
    fips: str
    simulation_result: dict[str, Any]


@router.post("/analyst")
def analyst(req: AnalystRequest):
    """Stream a Claude Opus risk analysis for a county."""
    con = get_connection()
    def generate():
        yield from stream_analyst(req.fips, con)
    return StreamingResponse(generate(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.post("/district-analyst")
def district_analyst(req: DistrictAnalystRequest):
    """Stream a Claude Opus risk analysis for a specific school district."""
    con = get_connection()
    def generate():
        yield from stream_district_analyst(req.lea_id, req.fips, con)
    return StreamingResponse(generate(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.post("/narrative")
def narrative(req: NarrativeRequest):
    """Stream a Claude Opus interpretation of a SEIR simulation result."""
    con = get_connection()
    def generate():
        yield from stream_narrative(req.fips, req.simulation_result, con)
    return StreamingResponse(generate(), media_type="text/event-stream", headers=SSE_HEADERS)
