import { useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ReferenceLine, ResponsiveContainer,
} from "recharts";
import { SimNarrative } from "./SimNarrative";
import type { SimResult } from "../types";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

const OUTBREAK_INFO = {
  "gaines-2025": {
    label: "Gaines County TX — 2025 Outbreak",
    fips: "48169",
    indexCaseDay: 45,
    description:
      "Retrospective simulation using 2023-2024 school-year vaccination data (79.2% MMR coverage). " +
      "The model seed uses 1 initial infectious individual. The dashed line marks the approximate index case confirmation date.",
  },
};

export function BacktestPanel() {
  const [result, setResult]   = useState<SimResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState("");

  const outbreakId = "gaines-2025";
  const info = OUTBREAK_INFO[outbreakId];

  const run = async () => {
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const resp = await fetch(`${BASE}/api/simulation/backtest/${outbreakId}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      setResult(data as SimResult);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setLoading(false);
    }
  };

  const chartData = result?.trajectory
    .filter((_, i) => i % 2 === 0)
    .map((p) => ({
      day: p.day,
      Infectious: Math.round(p.I),
      "New Cases (est.)": Math.round(p.new_cases * 7),
    })) ?? [];

  return (
    <div style={{
      height: "100%", overflow: "auto", padding: "24px 32px",
      fontFamily: "'Trebuchet MS', Arial, sans-serif",
    }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.14em", color: "#7A92AB", marginBottom: 6 }}>
          Retrospective Validation
        </div>
        <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: "#1A2744" }}>
          {info.label}
        </h2>
        <p style={{ margin: "8px 0 0", fontSize: 13, color: "#4A5E78", maxWidth: 680, lineHeight: 1.6 }}>
          {info.description}
        </p>
      </div>

      {/* Run button */}
      {!result && (
        <button
          onClick={run}
          disabled={loading}
          style={{
            background: "#1A2744", color: "#fff", border: "none",
            borderRadius: 6, padding: "10px 28px", fontSize: 13, fontWeight: 700,
            fontFamily: "'Trebuchet MS', Arial, sans-serif",
            cursor: loading ? "not-allowed" : "pointer",
            opacity: loading ? 0.6 : 1, marginBottom: 24,
          }}
        >
          {loading ? "Running backtest…" : "Run Gaines County Backtest"}
        </button>
      )}

      {error && (
        <div style={{ background: "#fceaea", color: "#C22828", borderRadius: 6, padding: "12px 16px", marginBottom: 20, fontSize: 13 }}>
          {error}
        </div>
      )}

      {result && (
        <div style={{ display: "flex", gap: 28, flexWrap: "wrap" }}>

          {/* Left: chart + key stats */}
          <div style={{ flex: "1 1 55%", minWidth: 400 }}>
            {/* Key stat row */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 20 }}>
              {[
                ["MMR Coverage", "79.2%"],
                ["Peak day",     String(result.peak_day)],
                ["Peak infected", Math.round(result.peak_infected).toLocaleString()],
                ["Attack rate",  `${(result.total_attack_rate * 100).toFixed(1)}%`],
              ].map(([label, val]) => (
                <div key={label} style={{ background: "#fff", border: "1px solid #D0DAE8", borderRadius: 8, padding: "10px 14px" }}>
                  <div style={{ fontSize: 9.5, textTransform: "uppercase", letterSpacing: "0.1em", color: "#7A92AB" }}>{label}</div>
                  <div style={{ fontSize: 20, fontWeight: 700, fontFamily: "monospace", color: "#1A2744", marginTop: 3 }}>{val}</div>
                </div>
              ))}
            </div>

            {/* Chart */}
            <div style={{ background: "#fff", border: "1px solid #D0DAE8", borderRadius: 8, padding: "16px 12px 8px" }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#1A2744", marginBottom: 12, paddingLeft: 8 }}>
                Simulated epidemic trajectory — R₀ = 16, seed = 1 case
              </div>
              <ResponsiveContainer width="100%" height={320}>
                <LineChart data={chartData} margin={{ top: 4, right: 16, bottom: 4, left: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e8eef6" />
                  <XAxis dataKey="day" tick={{ fontSize: 11 }} label={{ value: "Day", position: "insideBottomRight", offset: -4, fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip contentStyle={{ fontSize: 12, borderRadius: 6, border: "1px solid #D0DAE8" }} formatter={(v: number) => v.toLocaleString()} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <ReferenceLine x={info.indexCaseDay} stroke="#C22828" strokeDasharray="6 3"
                    label={{ value: "Index case confirmed", position: "top", fontSize: 10, fill: "#C22828" }}
                  />
                  <Line type="monotone" dataKey="Infectious"      stroke="#C22828" dot={false} strokeWidth={2} />
                  <Line type="monotone" dataKey="New Cases (est.)" stroke="#E8700A" dot={false} strokeWidth={1.5} strokeDasharray="4 2" />
                </LineChart>
              </ResponsiveContainer>
            </div>

            {/* Interpretation note */}
            <div style={{
              marginTop: 12, background: "#f9fafc", border: "1px solid #e0e8f4",
              borderRadius: 6, padding: "10px 14px", fontSize: 12, color: "#4A5E78", lineHeight: 1.6,
            }}>
              <strong style={{ color: "#1A2744" }}>Validation note:</strong>{" "}
              {result.reached_herd_immunity
                ? "Population is above the herd immunity threshold — model predicts the outbreak would self-limit."
                : `Population is below herd immunity threshold (needs ${result.herd_immunity_threshold}%). ` +
                  `Model predicts the outbreak would not self-limit without intervention. ` +
                  `Peak at day ${result.peak_day} with ~${Math.round(result.peak_infected).toLocaleString()} simultaneous infectious individuals.`}
            </div>

            {/* Re-run */}
            <button
              onClick={run}
              style={{
                marginTop: 12, background: "#EDF2F8", border: "1px solid #D0DAE8",
                borderRadius: 6, padding: "8px 20px", fontSize: 12, fontWeight: 700,
                color: "#1A2744", fontFamily: "'Trebuchet MS', Arial, sans-serif", cursor: "pointer",
              }}
            >
              Re-run
            </button>
          </div>

          {/* Right: Claude report */}
          <div style={{
            flex: "0 0 360px", background: "#fff", border: "1px solid #D0DAE8",
            borderRadius: 8, padding: 20, alignSelf: "flex-start",
          }}>
            <SimNarrative fips={info.fips} result={result} />
          </div>
        </div>
      )}
    </div>
  );
}
