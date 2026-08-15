"""
Discrete-time SEIR simulation for measles.

Parameters tuned to measles biology:
  R0:             12–18 (highly contagious)
  Incubation:     10–12 days (latent period)
  Infectious:     8 days
  Vaccine efficacy: 97%
  Herd immunity threshold: ~92–95%
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

import numpy as np


class SEIRPoint(TypedDict):
    day: int
    S: float
    E: float
    I: float
    R: float
    new_cases: float


@dataclass
class SEIRParams:
    population: int = 50_000
    mmr_coverage_pct: float = 90.0
    vaccine_efficacy: float = 0.97
    R0: float = 15.0
    incubation_days: float = 11.0  # sigma = 1/incubation
    infectious_days: float = 8.0   # gamma = 1/infectious
    seed_cases: int = 1
    days: int = 180


@dataclass
class SEIRResult:
    params: SEIRParams
    trajectory: list[SEIRPoint]
    peak_day: int
    peak_infected: float
    total_attack_rate: float  # fraction of susceptibles who got infected
    herd_immunity_threshold: float
    reached_herd_immunity: bool


def run(params: SEIRParams) -> SEIRResult:
    N = params.population
    sigma = 1.0 / params.incubation_days
    gamma = 1.0 / params.infectious_days
    beta = params.R0 * gamma / N

    # Effective immunity from vaccination
    immune_frac = (params.mmr_coverage_pct / 100.0) * params.vaccine_efficacy
    S0 = N * (1.0 - immune_frac) - params.seed_cases
    E0 = 0.0
    I0 = float(params.seed_cases)
    R0_state = N * immune_frac

    S, E, I, R = S0, E0, I0, R0_state

    hit = 1.0 - 1.0 / params.R0  # herd immunity threshold (fraction)

    trajectory: list[SEIRPoint] = []
    initial_susceptible = S0

    peak_infected = I0
    peak_day = 0

    for day in range(params.days + 1):
        new_exposed = beta * S * I
        new_infectious = sigma * E
        new_recovered = gamma * I

        trajectory.append(
            SEIRPoint(
                day=day,
                S=round(S, 2),
                E=round(E, 2),
                I=round(I, 2),
                R=round(R, 2),
                new_cases=round(new_infectious, 2),
            )
        )

        if I > peak_infected:
            peak_infected = I
            peak_day = day

        dS = -new_exposed
        dE = new_exposed - new_infectious
        dI = new_infectious - new_recovered
        dR = new_recovered

        S = max(0.0, S + dS)
        E = max(0.0, E + dE)
        I = max(0.0, I + dI)
        R = min(float(N), R + dR)

    final_R = trajectory[-1]["R"]
    total_infected = final_R - N * immune_frac
    attack_rate = total_infected / initial_susceptible if initial_susceptible > 0 else 0.0

    return SEIRResult(
        params=params,
        trajectory=trajectory,
        peak_day=peak_day,
        peak_infected=round(peak_infected, 1),
        total_attack_rate=round(attack_rate, 4),
        herd_immunity_threshold=round(hit * 100, 1),
        reached_herd_immunity=immune_frac >= hit,
    )
