import type { CountyScore, ScoreBreakdown, SimResult, DistrictBreakdown, ScoreHistoryPoint } from "./types";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  stateScores: (state: string) =>
    get<CountyScore[]>(`/api/scores/${state}`),

  countyBreakdown: (state: string, fips: string) =>
    get<ScoreBreakdown>(`/api/scores/${state}/${fips}/breakdown`),

  runSimulation: (fips: string, R0 = 15, days = 180, override_coverage_pct?: number) =>
    fetch(`${BASE}/api/simulation/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fips, R0, seed_cases: 1, days, override_coverage_pct }),
    }).then((r) => r.json()) as Promise<SimResult>,

  countyDistricts: (state: string, fips: string) =>
    get<DistrictBreakdown>(`/api/districts/${state}/${fips}`),

  countyHistory: (state: string, fips: string) =>
    get<ScoreHistoryPoint[]>(`/api/districts/${state}/${fips}/history`),
};
