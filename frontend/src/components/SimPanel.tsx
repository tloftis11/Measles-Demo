import { useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { api } from "../api";
import { SimNarrative } from "./SimNarrative";
import type { CountyScore, SimResult } from "../types";

interface Props {
  counties: CountyScore[];
  initialFips: string;
}

export function SimPanel({ counties, initialFips }: Props) {
  const [fips, setFips]               = useState(initialFips);
  const [R0, setR0]                   = useState(15);
  const [days, setDays]               = useState(180);
  const [result, setResult]           = useState<SimResult | null>(null);
  const [intervention, setIntervention] = useState<SimResult | null>(null);
  const [targetCov, setTargetCov]     = useState<number | null>(null);
  const [showWhatIf, setShowWhatIf]   = useState(false);
  const [loading, setLoading]         = useState(false);
  const [error, setError]             = useState("");

  const county = counties.find((c) => c.fips === fips);
  // Infer actual coverage from existing score (coverage_score inversely maps) — use a lookup sentinel

  const run = async (overrideCovPct?: number) => {
    setLoading(true);
    setError("");
    if (!overrideCovPct) {
      setResult(null);
      setIntervention(null);
    }
    try {
      const r = await api.runSimulation(fips, R0, days, overrideCovPct);
      if (overrideCovPct) {
        setIntervention(r);
      } else {
        setResult(r);
        setIntervention(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Simulation failed");
    } finally {
      setLoading(false);
    }
  };

  const runWhatIf = async () => {
    if (!targetCov) return;
    await run(targetCov);
  };

  // Build chart data merging base + intervention
  const chartData = (() => {
    if (!result) return [];
    return result.trajectory.filter((_, i) => i % 2 === 0).map((p, idx) => {
      const intv = intervention?.trajectory.filter((_, i) => i % 2 === 0)[idx];
      return {
        day: p.day,
        "Infectious (actual)": Math.round(p.I),
        "New Cases (actual)": Math.round(p.new_cases * 7),
        ...(intv ? {
          "Infectious (intervention)": Math.round(intv.I),
          "New Cases (intervention)":  Math.round(intv.new_cases * 7),
        } : {}),
      };
    });
  })();

  return (
    <div style={{
      height: "100%", display: "flex", flexDirection: "column",
      fontFamily: "'Trebuchet MS', Arial, sans-serif", overflow: "hidden",
    }}>
      {/* Controls bar */}
      <div style={{
        background: "#fff", borderBottom: "1px solid #D0DAE8",
        padding: "12px 24px", display: "flex", alignItems: "center",
        gap: 24, flexShrink: 0, flexWrap: "wrap",
      }}>
        {/* County selector */}
        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
          <label style={{ fontSize: 9.5, textTransform: "uppercase", letterSpacing: "0.1em", color: "#7A92AB" }}>County</label>
          <select
            value={fips}
            onChange={(e) => { setFips(e.target.value); setResult(null); setIntervention(null); }}
            style={{
              border: "1px solid #D0DAE8", borderRadius: 5, padding: "5px 10px",
              fontSize: 13, color: "#1A2744", background: "#fff",
              fontFamily: "'Trebuchet MS', Arial, sans-serif", cursor: "pointer",
            }}
          >
            {[...counties]
              .sort((a, b) => b.composite_score - a.composite_score)
              .map((c) => (
                <option key={c.fips} value={c.fips}>
                  {c.county_name} — {c.composite_score.toFixed(0)} ({c.risk_tier})
                </option>
              ))}
          </select>
        </div>

        {/* R0 slider */}
        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
          <label style={{ fontSize: 9.5, textTransform: "uppercase", letterSpacing: "0.1em", color: "#7A92AB" }}>
            R₀ = {R0}
          </label>
          <input type="range" min={8} max={20} step={0.5} value={R0}
            onChange={(e) => setR0(Number(e.target.value))}
            style={{ width: 110, accentColor: "#E8700A" }}
          />
        </div>

        {/* Days slider */}
        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
          <label style={{ fontSize: 9.5, textTransform: "uppercase", letterSpacing: "0.1em", color: "#7A92AB" }}>
            Days = {days}
          </label>
          <input type="range" min={60} max={365} step={10} value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            style={{ width: 110, accentColor: "#E8700A" }}
          />
        </div>

        {/* Run button */}
        <button
          onClick={() => run()}
          disabled={loading}
          style={{
            background: "#1A2744", color: "#fff", border: "none",
            borderRadius: 6, padding: "8px 20px", fontSize: 13, fontWeight: 700,
            fontFamily: "'Trebuchet MS', Arial, sans-serif",
            cursor: loading ? "not-allowed" : "pointer",
            opacity: loading ? 0.6 : 1, letterSpacing: "0.04em",
          }}
        >
          {loading ? "Running…" : "Run Simulation"}
        </button>

        {/* What-if toggle */}
        <button
          onClick={() => setShowWhatIf((x) => !x)}
          style={{
            background: showWhatIf ? "#fff3e8" : "#f4f7fb",
            border: `1px solid ${showWhatIf ? "#D45F00" : "#D0DAE8"}`,
            color: showWhatIf ? "#D45F00" : "#4A5E78",
            borderRadius: 6, padding: "7px 14px", fontSize: 12, fontWeight: 700,
            fontFamily: "'Trebuchet MS', Arial, sans-serif", cursor: "pointer",
          }}
        >
          What-If Intervention
        </button>

        {/* Summary stats */}
        {result && (
          <div style={{ display: "flex", gap: 20, marginLeft: "auto" }}>
            {[
              ["Peak day",      result.peak_day],
              ["Peak infected", Math.round(result.peak_infected).toLocaleString()],
              ["Attack rate",   `${(result.total_attack_rate * 100).toFixed(1)}%`],
              ["Herd threshold",`${result.herd_immunity_threshold}%`],
            ].map(([label, val]) => (
              <div key={label as string} style={{ textAlign: "center" }}>
                <div style={{ fontSize: 9.5, textTransform: "uppercase", letterSpacing: "0.1em", color: "#7A92AB" }}>{label}</div>
                <div style={{ fontSize: 18, fontWeight: 700, fontFamily: "monospace", color: "#1A2744" }}>{val}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* What-If panel */}
      {showWhatIf && (
        <div style={{
          background: "#fff8f0", borderBottom: "1px solid #f0d8b8",
          padding: "10px 24px", display: "flex", alignItems: "center", gap: 20, flexShrink: 0,
        }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#D45F00" }}>INTERVENTION SCENARIO</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <label style={{ fontSize: 9.5, textTransform: "uppercase", letterSpacing: "0.1em", color: "#7A92AB" }}>
              Target MMR coverage = {targetCov ?? 95}%
            </label>
            <input
              type="range" min={70} max={99} step={1}
              value={targetCov ?? 95}
              onChange={(e) => setTargetCov(Number(e.target.value))}
              style={{ width: 160, accentColor: "#D45F00" }}
            />
          </div>
          <div style={{ fontSize: 11, color: "#7A92AB" }}>
            Simulates effect of a vaccination campaign raising coverage to the target level
          </div>
          <button
            onClick={runWhatIf}
            disabled={loading || !result}
            style={{
              background: "#D45F00", color: "#fff", border: "none",
              borderRadius: 6, padding: "7px 16px", fontSize: 12, fontWeight: 700,
              fontFamily: "'Trebuchet MS', Arial, sans-serif",
              cursor: loading || !result ? "not-allowed" : "pointer",
              opacity: loading || !result ? 0.55 : 1,
            }}
          >
            Run Scenario
          </button>
          {intervention && (
            <div style={{ fontSize: 12, color: "#1A2744" }}>
              Intervention peak: <strong>Day {intervention.peak_day}</strong>{" "}
              ({Math.round(intervention.peak_infected).toLocaleString()} infected)
              {" · "}
              {intervention.reached_herd_immunity
                ? <span style={{ color: "#1E8A4C", fontWeight: 700 }}>Self-limiting ✓</span>
                : <span style={{ color: "#C22828", fontWeight: 700 }}>Still epidemic</span>}
            </div>
          )}
        </div>
      )}

      {error && (
        <div style={{ background: "#fceaea", color: "#C22828", padding: "10px 24px", fontSize: 13 }}>
          {error}
        </div>
      )}

      {/* Chart + narrative */}
      <div style={{ flex: 1, overflow: "auto", padding: "20px 24px", display: "flex", gap: 24 }}>

        {/* Left: chart */}
        <div style={{ flex: "1 1 55%", minWidth: 0 }}>
          {!result && !loading && (
            <div style={{
              height: 360, display: "flex", alignItems: "center", justifyContent: "center",
              background: "#f6f8fc", borderRadius: 8, border: "1px dashed #D0DAE8",
              color: "#7A92AB", fontSize: 14,
            }}>
              Select a county and click Run Simulation
            </div>
          )}

          {result && (
            <>
              <div style={{ fontSize: 13, fontWeight: 700, color: "#1A2744", marginBottom: 4 }}>
                SEIR Trajectory — {county?.county_name ?? fips} County · R₀ = {R0}
                {intervention && (
                  <span style={{ marginLeft: 10, fontSize: 11, fontWeight: 400, color: "#D45F00" }}>
                    + intervention at {targetCov}% coverage
                  </span>
                )}
              </div>
              <ResponsiveContainer width="100%" height={340}>
                <LineChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e8eef6" />
                  <XAxis dataKey="day" tick={{ fontSize: 11 }} label={{ value: "Day", position: "insideBottomRight", offset: -4, fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{ fontSize: 12, borderRadius: 6, border: "1px solid #D0DAE8" }}
                    formatter={(v: number) => v.toLocaleString()}
                  />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Line type="monotone" dataKey="Infectious (actual)"      stroke="#C22828" dot={false} strokeWidth={2} />
                  <Line type="monotone" dataKey="New Cases (actual)"       stroke="#E8700A" dot={false} strokeWidth={1.5} strokeDasharray="4 2" />
                  {intervention && <>
                    <Line type="monotone" dataKey="Infectious (intervention)" stroke="#1E8A4C" dot={false} strokeWidth={2} strokeDasharray="6 3" />
                    <Line type="monotone" dataKey="New Cases (intervention)"  stroke="#2F7A3C" dot={false} strokeWidth={1.5} strokeDasharray="2 2" />
                  </>}
                </LineChart>
              </ResponsiveContainer>

              <div style={{ marginTop: 10, fontSize: 11, color: "#7A92AB", lineHeight: 1.6 }}>
                Herd immunity threshold for measles at this R₀:{" "}
                <strong style={{ color: "#1A2744" }}>{result.herd_immunity_threshold}%</strong>
                {" · "}
                {result.reached_herd_immunity
                  ? <span style={{ color: "#1E8A4C" }}>Current coverage exceeds threshold</span>
                  : <span style={{ color: "#C22828" }}>Current coverage below threshold — epidemic possible</span>}
              </div>
            </>
          )}
        </div>

        {/* Right: Claude narrative */}
        <div style={{
          flex: "0 0 340px", background: "#fff", borderRadius: 8,
          border: "1px solid #D0DAE8", padding: 20, overflowY: "auto",
        }}>
          {result
            ? <SimNarrative fips={fips} result={result} />
            : <div style={{ color: "#7A92AB", fontSize: 13, lineHeight: 1.6 }}>
                Run a simulation to get a Claude Opus interpretation of the epidemic trajectory, peak timing, and intervention tradeoffs.
              </div>}
        </div>
      </div>
    </div>
  );
}
