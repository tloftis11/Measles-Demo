import { useEffect, useState } from "react";
import {
  LineChart, Line, ResponsiveContainer, Tooltip, ReferenceLine,
} from "recharts";
import type { ScoreBreakdown, SchoolDistrict, ScoreHistoryPoint } from "../types";
import { api } from "../api";
import { AIAnalyst } from "./AIAnalyst";

const TIER_COLOR: Record<string, string> = {
  CRITICAL: "#C22828",
  HIGH:     "#D45F00",
  MODERATE: "#C9920C",
  LOW:      "#1E8A4C",
};

function Bar({ value, color }: { value: number; color: string }) {
  return (
    <div style={{ background: "#e8eef6", borderRadius: 3, height: 8, overflow: "hidden" }}>
      <div style={{ width: `${value}%`, height: "100%", background: color, borderRadius: 3 }} />
    </div>
  );
}

function Row({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 3 }}>
        <span style={{ color: "#4A5E78" }}>{label}</span>
        <span style={{ fontFamily: "monospace", fontWeight: 700 }}>{value.toFixed(1)}</span>
      </div>
      <Bar value={value} color={color} />
    </div>
  );
}

// ── Sparkline ────────────────────────────────────────────────────────────────
function Sparkline({ fips }: { fips: string }) {
  const [history, setHistory] = useState<ScoreHistoryPoint[]>([]);

  useEffect(() => {
    api.countyHistory("tx", fips).then(setHistory).catch(() => {});
  }, [fips]);

  if (history.length < 2) return null;

  const first = history[0].score;
  const last  = history[history.length - 1].score;
  const delta = last - first;
  const deltaColor = delta > 5 ? "#C22828" : delta > 0 ? "#D45F00" : "#1E8A4C";
  const arrow = delta > 0 ? "↑" : delta < 0 ? "↓" : "→";

  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
        <div style={{ fontSize: 9.5, textTransform: "uppercase", letterSpacing: "0.1em", color: "#7A92AB" }}>
          10-week trend
        </div>
        <div style={{ fontSize: 11, fontWeight: 700, color: deltaColor, fontFamily: "monospace" }}>
          {arrow} {Math.abs(delta).toFixed(1)} pts
        </div>
      </div>
      <ResponsiveContainer width="100%" height={52}>
        <LineChart data={history} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
          <ReferenceLine y={75} stroke="#C22828" strokeDasharray="3 2" strokeWidth={0.8} />
          <ReferenceLine y={50} stroke="#D45F00" strokeDasharray="3 2" strokeWidth={0.8} />
          <ReferenceLine y={25} stroke="#C9920C" strokeDasharray="3 2" strokeWidth={0.8} />
          <Tooltip
            contentStyle={{ fontSize: 11, borderRadius: 4, border: "1px solid #D0DAE8", padding: "3px 8px" }}
            formatter={(v: number) => [v.toFixed(1), "Score"]}
            labelFormatter={(_, payload) => payload?.[0]?.payload?.date ?? ""}
          />
          <Line
            type="monotone" dataKey="score" stroke={deltaColor}
            dot={false} strokeWidth={2}
            activeDot={{ r: 3, stroke: deltaColor, fill: "#fff", strokeWidth: 1.5 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── District drill-down ───────────────────────────────────────────────────────
function DistrictTable({ fips }: { fips: string }) {
  const [districts, setDistricts] = useState<SchoolDistrict[] | null>(null);
  const [expanded, setExpanded]   = useState(false);

  useEffect(() => {
    setDistricts(null);
    setExpanded(false);
    api.countyDistricts("tx", fips)
      .then((d) => setDistricts(d.districts))
      .catch(() => setDistricts([]));
  }, [fips]);

  if (!districts) return (
    <div style={{ fontSize: 11, color: "#7A92AB", padding: "6px 0" }}>Loading districts…</div>
  );
  if (districts.length === 0) return null;

  const shown = expanded ? districts : districts.slice(0, 4);
  const flagged = districts.filter((d) => d.mmr_coverage_pct < 85).length;

  return (
    <div style={{ borderTop: "1px solid #e8eef6", marginTop: 14, paddingTop: 12 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <div style={{ fontSize: 9.5, textTransform: "uppercase", letterSpacing: "0.1em", color: "#7A92AB" }}>
          School Districts ({districts.length})
        </div>
        {flagged > 0 && (
          <div style={{
            background: "#fceaea", color: "#C22828", borderRadius: 10,
            padding: "2px 8px", fontSize: 10, fontWeight: 700,
          }}>
            {flagged} below 85%
          </div>
        )}
      </div>

      {/* Column headers */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 52px 52px", gap: 4, marginBottom: 4 }}>
        {["District", "MMR", "Enroll"].map((h) => (
          <div key={h} style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.08em", color: "#7A92AB" }}>
            {h}
          </div>
        ))}
      </div>

      {shown.map((d) => {
        const flagColor = d.mmr_coverage_pct < 80 ? "#C22828"
                        : d.mmr_coverage_pct < 85 ? "#D45F00"
                        : d.mmr_coverage_pct < 92 ? "#C9920C"
                        : "#1E8A4C";
        const below95 = d.mmr_coverage_pct < 95;
        return (
          <div key={d.lea_id} style={{
            display: "grid", gridTemplateColumns: "1fr 52px 52px",
            gap: 4, padding: "5px 0",
            borderBottom: "1px solid #f0f4f8",
            background: d.mmr_coverage_pct < 80 ? "#fff8f8" : "transparent",
          }}>
            <div style={{
              fontSize: 11.5, color: "#1A2744", overflow: "hidden",
              textOverflow: "ellipsis", whiteSpace: "nowrap",
            }} title={d.district_name}>
              {d.district_name}
            </div>
            <div style={{ fontFamily: "monospace", fontSize: 12, fontWeight: 700, color: flagColor, textAlign: "right" }}>
              {d.mmr_coverage_pct.toFixed(1)}%
            </div>
            <div style={{ fontFamily: "monospace", fontSize: 11, color: "#7A92AB", textAlign: "right" }}>
              {d.enrollment.toLocaleString()}
            </div>
          </div>
        );
      })}

      {districts.length > 4 && (
        <button
          onClick={() => setExpanded((x) => !x)}
          style={{
            marginTop: 6, background: "none", border: "none",
            color: "#E8700A", fontSize: 11, fontWeight: 700, cursor: "pointer",
            padding: 0, fontFamily: "'Trebuchet MS', Arial, sans-serif",
          }}
        >
          {expanded ? "Show fewer" : `Show all ${districts.length} districts`}
        </button>
      )}
    </div>
  );
}

// ── Main panel ───────────────────────────────────────────────────────────────
export function ScorePanel({
  data, onClose, onSimulate,
}: {
  data: ScoreBreakdown;
  onClose: () => void;
  onSimulate?: () => void;
}) {
  const tierColor = TIER_COLOR[data.risk_tier] ?? "#4A5E78";

  return (
    <div style={{
      position: "absolute", top: 16, right: 16, width: 380,
      maxHeight: "calc(100vh - 32px)", zIndex: 1000,
      background: "#fff", borderRadius: 8,
      boxShadow: "0 4px 24px rgba(0,0,0,0.18)",
      fontFamily: "'Trebuchet MS', Arial, sans-serif",
      display: "flex", flexDirection: "column", overflow: "hidden",
    }}>

      {/* ── Header ── */}
      <div style={{
        background: tierColor, padding: "14px 16px 12px",
        color: "#fff", flexShrink: 0, position: "relative",
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", paddingRight: 28 }}>
          <div>
            <div style={{ fontSize: 10, opacity: 0.8, textTransform: "uppercase", letterSpacing: "0.12em" }}>
              {data.risk_tier} RISK
            </div>
            <div style={{ fontSize: 18, fontWeight: 700, marginTop: 2 }}>{data.county_name} County</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 34, fontWeight: 700, lineHeight: 1, fontFamily: "monospace" }}>
              {data.composite_score.toFixed(0)}
            </div>
            <div style={{ fontSize: 10, opacity: 0.75 }}>/ 100</div>
          </div>
        </div>
        <button
          onClick={onClose}
          aria-label="Close panel"
          style={{
            position: "absolute", top: 10, right: 10,
            background: "rgba(255,255,255,0.25)", border: "none", color: "#fff",
            borderRadius: 4, padding: "2px 8px", cursor: "pointer", fontSize: 14, lineHeight: 1,
          }}
        >✕</button>
      </div>

      {/* ── Body ── */}
      <div style={{ flex: 1, overflowY: "auto", padding: 16 }}>

        {/* 10-week sparkline */}
        <Sparkline fips={data.fips} />

        {/* Key stat chips */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 16 }}>
          {[
            ["MMR Coverage",   `${data.mmr_coverage_pct.toFixed(1)}%`],
            ["Non-Med Exempt", `${data.nonmedical_exempt_pct.toFixed(1)}%`],
            ["Recent Cases",   String(data.recent_cases)],
            ["Population",     data.population.toLocaleString()],
          ].map(([label, val]) => (
            <div key={label} style={{ background: "#f6f8fc", borderRadius: 6, padding: "8px 10px" }}>
              <div style={{ fontSize: 9.5, color: "#7A92AB", textTransform: "uppercase", letterSpacing: "0.1em" }}>
                {label}
              </div>
              <div style={{ fontSize: 15, fontWeight: 700, fontFamily: "monospace", color: "#1A2744", marginTop: 2 }}>
                {val}
              </div>
            </div>
          ))}
        </div>

        {/* Layer bars */}
        <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.1em", color: "#7A92AB", marginBottom: 8 }}>
          Layer Scores
        </div>
        <Row label="Vaccination Coverage (40%)" value={data.coverage_score}    color="#1E8A4C" />
        <Row label="Surveillance (35%)"          value={data.surveillance_score} color="#D45F00" />
        <Row label="Network (25%)"               value={data.network_score}      color="#2F5FA8" />

        {/* Sub-score grid */}
        <div style={{ borderTop: "1px solid #e8eef6", marginTop: 12, paddingTop: 12 }}>
          <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.1em", color: "#7A92AB", marginBottom: 8 }}>
            Sub-scores
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 16px", fontSize: 12, color: "#4A5E78" }}>
            {([
              ["Coverage gap", data.coverage_gap_score],
              ["Exemption",    data.exemption_score],
              ["Incidence",    data.incidence_score],
              ["Wastewater",   data.wastewater_score],
              ["Mobility",     data.mobility_score],
              ["Community",    data.community_score],
            ] as [string, number][]).map(([label, val]) => (
              <div key={label} style={{ display: "flex", justifyContent: "space-between" }}>
                <span>{label}</span>
                <span style={{ fontFamily: "monospace", fontWeight: 600 }}>{val.toFixed(1)}</span>
              </div>
            ))}
          </div>
        </div>

        {/* School district drill-down */}
        <DistrictTable fips={data.fips} />

        {/* Simulate button */}
        {onSimulate && (
          <button
            onClick={onSimulate}
            style={{
              width: "100%", marginTop: 14,
              background: "#EDF2F8", border: "1px solid #D0DAE8",
              borderRadius: 6, padding: "8px 0",
              fontSize: 12, fontWeight: 700, color: "#1A2744",
              fontFamily: "'Trebuchet MS', Arial, sans-serif",
              cursor: "pointer", letterSpacing: "0.04em",
            }}
          >
            Run SEIR Simulation →
          </button>
        )}

        {/* AI Analyst */}
        <AIAnalyst fips={data.fips} countyName={data.county_name} />
      </div>
    </div>
  );
}
