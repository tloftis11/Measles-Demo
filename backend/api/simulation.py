from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from db import get_connection
from simulation.seir import SEIRParams, run

router = APIRouter(prefix="/api/simulation", tags=["simulation"])


class SimRequest(BaseModel):
    fips: str
    R0: float = Field(default=15.0, ge=1.0, le=30.0)
    seed_cases: int = Field(default=1, ge=1, le=100)
    days: int = Field(default=180, ge=30, le=365)
    override_coverage_pct: float | None = Field(default=None, ge=0.0, le=100.0)


@router.post("/run")
def run_simulation(req: SimRequest):
    con = get_connection()

    geo = con.execute(
        "SELECT population FROM geographies WHERE fips = ?", [req.fips]
    ).fetchone()
    if not geo:
        raise HTTPException(status_code=404, detail=f"County not found: {req.fips}")

    cov = con.execute(
        """
        SELECT mmr_coverage_pct FROM vaccination_coverage
        WHERE fips = ? ORDER BY school_year DESC LIMIT 1
        """,
        [req.fips],
    ).fetchone()

    coverage_pct = req.override_coverage_pct or (cov[0] if cov else 90.0)

    params = SEIRParams(
        population=geo[0],
        mmr_coverage_pct=coverage_pct,
        R0=req.R0,
        seed_cases=req.seed_cases,
        days=req.days,
    )
    result = run(params)

    return {
        "fips": req.fips,
        "params": asdict(result.params),
        "peak_day": result.peak_day,
        "peak_infected": result.peak_infected,
        "total_attack_rate": result.total_attack_rate,
        "herd_immunity_threshold": result.herd_immunity_threshold,
        "reached_herd_immunity": result.reached_herd_immunity,
        "trajectory": result.trajectory,
    }


@router.get("/backtest/{outbreak_id}")
def run_backtest(outbreak_id: str):
    """Run a pre-defined backtest against a known outbreak."""
    BACKTESTS = {
        "gaines-2025": {
            "fips": "48169",
            "label": "Gaines County TX — 2025 Outbreak",
            "description": (
                "Retrospective simulation using 2023-2024 school-year vaccination "
                "data. The county reported its index case in January 2025; the model "
                "seed uses 1 initial infectious case."
            ),
            "R0": 16.0,
            "seed_cases": 1,
            "days": 120,
        }
    }

    cfg = BACKTESTS.get(outbreak_id)
    if not cfg:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown backtest: {outbreak_id}. Available: {list(BACKTESTS)}",
        )

    req = SimRequest(
        fips=cfg["fips"],
        R0=cfg["R0"],
        seed_cases=cfg["seed_cases"],
        days=cfg["days"],
    )
    result = run_simulation(req)
    return {**cfg, **result}
