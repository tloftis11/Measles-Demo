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

function Bar({ value, color, max = 100 }: { value: number; color: string; max?: number }) {
  return (
    <div style={{ background: "#e8eef6", borderRadius: 3, height: 8, overflow: "hidden" }}>
      <div style={{ width: `${(value / max) * 100}%`, height: "100%", background: color, borderRadius: 3 }} />
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

function DistrictTable({
  fips,
  onSelect,
}: {
  fips: string;
  onSelect: (d: SchoolDistrict) => void;
}) {
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

  const shown   = expanded ? districts : districts.slice(0, 4);
  const flagged = districts.filter((d) => d.mmr_coverage_pct < 85).length;

  return (
    <div style={{ borderTop: "1px solid #e8eef6", marginTop: 14, paddingTop: 12 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <div style={{ fontSize: 9.5, textTransform: "uppercase", letterSpacing: "0.1em", color: "#7A92AB" }}>
          School Districts ({districts.length}) — click for details
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
        return (
          <div
            key={d.lea_id}
            onClick={() => onSelect(d)}
            style={{
              display: "grid", gridTemplateColumns: "1fr 52px 52px",
              gap: 4, padding: "5px 6px",
              borderBottom: "1px solid #f0f4f8",
              background: d.mmr_coverage_pct < 80 ? "#fff8f8" : "transparent",
              cursor: "pointer",
              borderRadius: 4,
              transition: "background 0.1s",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = "#f0f6ff")}
            onMouseLeave={(e) => (e.currentTarget.style.background = d.mmr_coverage_pct < 80 ? "#fff8f8" : "transparent")}
          >
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

// ── District detail data view ─────────────────────────────────────────────────
function DistrictDataView({
  district,
  countyBreakdown,
}: {
  district: SchoolDistrict;
  countyBreakdown: ScoreBreakdown;
}) {
  const unprotected = Math.round(district.enrollment * (1 - district.mmr_coverage_pct / 100));
  const nmExemptCount = Math.round(district.enrollment * district.nonmedical_exempt_pct / 100);
  const gap = Math.max(0, 95 - district.mmr_coverage_pct);

  const mmrColor = district.mmr_coverage_pct < 80 ? "#C22828"
                 : district.mmr_coverage_pct < 85 ? "#D45F00"
                 : district.mmr_coverage_pct < 92 ? "#C9920C"
                 : "#1E8A4C";

  const countyDiff = district.mmr_coverage_pct - countyBreakdown.mmr_coverage_pct;

  return (
    <div>
      {/* MMR coverage bar with 95% threshold marker */}
      <div style={{ marginBottom: 18 }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, fontWeight: 700, marginBottom: 6 }}>
          <span style={{ color: "#4A5E78" }}>MMR Coverage</span>
          <span style={{ fontFamily: "monospace", color: mmrColor }}>
            {district.mmr_coverage_pct.toFixed(1)}%
          </span>
        </div>
        <div style={{ position: "relative", height: 12 }}>
          <div style={{ background: "#e8eef6", borderRadius: 4, height: "100%", overflow: "hidden" }}>
            <div style={{ width: `${district.mmr_coverage_pct}%`, height: "100%", background: mmrColor, borderRadius: 4 }} />
          </div>
          {/* 95% threshold marker */}
          <div style={{
            position: "absolute", left: "95%", top: -2, width: 2, height: 16,
            background: "#1A2744", borderRadius: 1,
          }} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
          <span style={{ fontSize: 10, color: gap > 0 ? "#C22828" : "#1E8A4C" }}>
            {gap > 0 ? `${gap.toFixed(1)}pp below herd immunity threshold` : "Above herd immunity threshold ✓"}
          </span>
          <span style={{ fontSize: 10, color: "#7A92AB" }}>95%</span>
        </div>
      </div>

      {/* Key stats grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 16 }}>
        {([
          ["Enrolled",         district.enrollment.toLocaleString()],
          ["Unprotected",      unprotected.toLocaleString()],
          ["Non-Med Exempt",   `${district.nonmedical_exempt_pct.toFixed(1)}%`],
          ["NM Exempt Count",  nmExemptCount.toLocaleString()],
        ] as [string, string][]).map(([label, val]) => (
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

      {/* County & state comparison */}
      <div style={{ borderTop: "1px solid #e8eef6", paddingTop: 12, marginBottom: 12 }}>
        <div style={{ fontSize: 9.5, textTransform: "uppercase", letterSpacing: "0.1em", color: "#7A92AB", marginBottom: 8 }}>
          Benchmarks
        </div>
        <div style={{ fontSize: 12, color: "#4A5E78", lineHeight: 2 }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span>County avg MMR ({countyBreakdown.county_name})</span>
            <span style={{ fontFamily: "monospace", fontWeight: 700 }}>
              {countyBreakdown.mmr_coverage_pct.toFixed(1)}%
            </span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span>vs. county avg</span>
            <span style={{
              fontFamily: "monospace", fontWeight: 700,
              color: countyDiff >= 0 ? "#1E8A4C" : "#C22828",
            }}>
              {countyDiff >= 0 ? "+" : ""}{countyDiff.toFixed(1)}pp
            </span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span>County risk score</span>
            <span style={{ fontFamily: "monospace", fontWeight: 700, color: TIER_COLOR[countyBreakdown.risk_tier] ?? "#4A5E78" }}>
              {countyBreakdown.composite_score.toFixed(0)} ({countyBreakdown.risk_tier})
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Velocity chip ─────────────────────────────────────────────────────────────
function VelocityChip({ velocity, modifier }: { velocity: number; modifier: number }) {
  if (velocity === 0 && modifier === 0) return null;
  const rising = velocity > 0;
  const color = rising ? "#C22828" : "#1E8A4C";
  const bg    = rising ? "#fceaea" : "#eafaf1";
  const arrow = rising ? "↑" : "↓";
  return (
    <div style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      background: bg, border: `1px solid ${color}30`,
      borderRadius: 10, padding: "2px 8px",
      fontSize: 10, fontWeight: 700, color,
      fontFamily: "monospace",
    }}>
      {arrow} {Math.abs(velocity).toFixed(1)} pts/wk
      {modifier !== 0 && (
        <span style={{ fontWeight: 400, opacity: 0.75 }}>
          ({modifier > 0 ? "+" : ""}{modifier.toFixed(1)} to score)
        </span>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
type SidebarTab = "data" | "ai";

interface Props {
  breakdown: ScoreBreakdown | undefined;
  isLoading?: boolean;
  onSimulate?: () => void;
}

export function AnalysisSidebar({ breakdown, isLoading, onSimulate }: Props) {
  const [activeTab, setActiveTab]             = useState<SidebarTab>("data");
  const [selectedDistrict, setSelectedDistrict] = useState<SchoolDistrict | null>(null);

  // Reset district selection when county changes
  useEffect(() => {
    setSelectedDistrict(null);
    setActiveTab("data");
  }, [breakdown?.fips]);

  const tierColor = breakdown
    ? (TIER_COLOR[breakdown.risk_tier] ?? "#4A5E78")
    : "#1A2744";

  // ── Empty / loading state ───────────────────────────────────────────────────
  if (!breakdown) {
    return (
      <div style={{
        width: "100%", height: "100%", background: "#fff",
        borderLeft: "1px solid #D0DAE8", display: "flex", flexDirection: "column",
        fontFamily: "'Trebuchet MS', Arial, sans-serif",
      }}>
        <div style={{ background: "#1A2744", color: "#fff", padding: "14px 16px 12px", flexShrink: 0 }}>
          <div style={{ fontSize: 10, opacity: 0.7, textTransform: "uppercase", letterSpacing: "0.12em" }}>
            County Analysis
          </div>
          <div style={{ fontSize: 14, fontWeight: 700, marginTop: 2, opacity: 0.85 }}>
            {isLoading ? "Loading…" : "Select a county on the map"}
          </div>
        </div>
        <div style={{
          flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
          flexDirection: "column", gap: 12, padding: 24, textAlign: "center",
        }}>
          {!isLoading && (
            <>
              <div style={{
                width: 48, height: 48, borderRadius: "50%",
                background: "#f0f4f8", display: "flex",
                alignItems: "center", justifyContent: "center", fontSize: 22,
              }}>🗺️</div>
              <div style={{ fontSize: 14, fontWeight: 700, color: "#1A2744" }}>No county selected</div>
              <div style={{ fontSize: 12, color: "#7A92AB", lineHeight: 1.6, maxWidth: 220 }}>
                Click any county on the map to see its risk analysis.
              </div>
            </>
          )}
        </div>
      </div>
    );
  }

  // ── District selected view ──────────────────────────────────────────────────
  if (selectedDistrict) {
    return (
      <div style={{
        width: "100%", height: "100%", background: "#fff",
        borderLeft: "1px solid #D0DAE8", display: "flex", flexDirection: "column",
        fontFamily: "'Trebuchet MS', Arial, sans-serif", overflow: "hidden",
      }}>
        {/* District header */}
        <div style={{
          background: "#1A2744", color: "#fff",
          padding: "10px 14px 10px", flexShrink: 0,
        }}>
          {/* Breadcrumb back button */}
          <button
            onClick={() => { setSelectedDistrict(null); setActiveTab("data"); }}
            style={{
              background: "rgba(255,255,255,0.12)", border: "none", color: "#fff",
              borderRadius: 4, padding: "3px 10px", cursor: "pointer",
              fontSize: 11, marginBottom: 8, display: "flex", alignItems: "center", gap: 5,
              fontFamily: "'Trebuchet MS', Arial, sans-serif",
            }}
          >
            ← {breakdown.county_name} County
          </button>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <div>
              <div style={{ fontSize: 10, opacity: 0.75, textTransform: "uppercase", letterSpacing: "0.12em" }}>
                School District
              </div>
              <div style={{ fontSize: 15, fontWeight: 700, marginTop: 2, lineHeight: 1.3 }}>
                {selectedDistrict.district_name}
              </div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: 26, fontWeight: 700, lineHeight: 1, fontFamily: "monospace" }}>
                {selectedDistrict.mmr_coverage_pct.toFixed(1)}%
              </div>
              <div style={{ fontSize: 10, opacity: 0.7 }}>MMR</div>
            </div>
          </div>
        </div>

        {/* Tab bar */}
        <div style={{
          display: "flex", borderBottom: "1px solid #D0DAE8",
          background: "#f9fafc", flexShrink: 0,
        }}>
          {(["data", "ai"] as SidebarTab[]).map((t) => (
            <button
              key={t}
              onClick={() => setActiveTab(t)}
              style={{
                flex: 1, padding: "10px 0",
                background: activeTab === t ? "#fff" : "transparent",
                border: "none",
                borderBottom: activeTab === t ? "2px solid #1A2744" : "2px solid transparent",
                color: activeTab === t ? "#1A2744" : "#7A92AB",
                fontSize: 12, fontWeight: activeTab === t ? 700 : 400,
                fontFamily: "'Trebuchet MS', Arial, sans-serif",
                cursor: "pointer", letterSpacing: "0.04em",
                transition: "color 0.12s, background 0.12s",
              }}
            >
              {t === "data" ? "Data" : "AI Analysis"}
            </button>
          ))}
        </div>

        {/* Both tab panels always mounted */}
        <div style={{ flex: 1, overflow: "hidden", position: "relative" }}>
          <div style={{ display: activeTab === "data" ? "block" : "none", height: "100%", overflowY: "auto", padding: 16 }}>
            <DistrictDataView district={selectedDistrict} countyBreakdown={breakdown} />
          </div>
          <div style={{ display: activeTab === "ai" ? "block" : "none", height: "100%", overflowY: "auto", padding: 16 }}>
            <AIAnalyst
              fips={breakdown.fips}
              countyName={breakdown.county_name}
              leaId={selectedDistrict.lea_id}
              districtName={selectedDistrict.district_name}
            />
          </div>
        </div>
      </div>
    );
  }

  // ── County view ─────────────────────────────────────────────────────────────
  return (
    <div style={{
      width: "100%", height: "100%", background: "#fff",
      borderLeft: "1px solid #D0DAE8", display: "flex", flexDirection: "column",
      fontFamily: "'Trebuchet MS', Arial, sans-serif", overflow: "hidden",
    }}>
      {/* County header */}
      <div style={{
        background: tierColor, color: "#fff",
        padding: "14px 16px 12px", flexShrink: 0,
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <div style={{ fontSize: 10, opacity: 0.8, textTransform: "uppercase", letterSpacing: "0.12em" }}>
              {breakdown.risk_tier} RISK
            </div>
            <div style={{ fontSize: 17, fontWeight: 700, marginTop: 2 }}>
              {breakdown.county_name} County
            </div>
            {/* Velocity chip */}
            {(breakdown.score_velocity !== 0 || breakdown.velocity_modifier !== 0) && (
              <div style={{ marginTop: 6 }}>
                <VelocityChip
                  velocity={breakdown.score_velocity}
                  modifier={breakdown.velocity_modifier}
                />
              </div>
            )}
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 32, fontWeight: 700, lineHeight: 1, fontFamily: "monospace" }}>
              {breakdown.composite_score.toFixed(0)}
            </div>
            <div style={{ fontSize: 10, opacity: 0.75 }}>/ 100</div>
          </div>
        </div>
      </div>

      {/* Tab bar */}
      <div style={{
        display: "flex", borderBottom: "1px solid #D0DAE8",
        background: "#f9fafc", flexShrink: 0,
      }}>
        {(["data", "ai"] as SidebarTab[]).map((t) => (
          <button
            key={t}
            onClick={() => setActiveTab(t)}
            style={{
              flex: 1, padding: "10px 0",
              background: activeTab === t ? "#fff" : "transparent",
              border: "none",
              borderBottom: activeTab === t ? `2px solid ${tierColor}` : "2px solid transparent",
              color: activeTab === t ? "#1A2744" : "#7A92AB",
              fontSize: 12, fontWeight: activeTab === t ? 700 : 400,
              fontFamily: "'Trebuchet MS', Arial, sans-serif",
              cursor: "pointer", letterSpacing: "0.04em",
              transition: "color 0.12s, background 0.12s",
            }}
          >
            {t === "data" ? "Data" : "AI Analysis"}
          </button>
        ))}
      </div>

      {/* Both tab panels always mounted */}
      <div style={{ flex: 1, overflow: "hidden", position: "relative" }}>
        {/* Data tab */}
        <div style={{ display: activeTab === "data" ? "block" : "none", height: "100%", overflowY: "auto", padding: 16 }}>
          <Sparkline fips={breakdown.fips} />

          {/* Key stat chips */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 16 }}>
            {([
              ["MMR Coverage",   `${breakdown.mmr_coverage_pct.toFixed(1)}%`],
              ["Non-Med Exempt", `${breakdown.nonmedical_exempt_pct.toFixed(1)}%`],
              ["Recent Cases",   String(breakdown.recent_cases)],
              ["Population",     breakdown.population.toLocaleString()],
            ] as [string, string][]).map(([label, val]) => (
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
          <Row label="Vaccination Coverage (40%)" value={breakdown.coverage_score}    color="#1E8A4C" />
          <Row label="Surveillance (35%)"          value={breakdown.surveillance_score} color="#D45F00" />
          <Row label="Network (25%)"               value={breakdown.network_score}      color="#2F5FA8" />

          {/* Sub-scores — now includes district_variance */}
          <div style={{ borderTop: "1px solid #e8eef6", marginTop: 12, paddingTop: 12 }}>
            <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.1em", color: "#7A92AB", marginBottom: 8 }}>
              Sub-scores
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 16px", fontSize: 12, color: "#4A5E78" }}>
              {([
                ["Coverage gap",      breakdown.coverage_gap_score],
                ["Exemption",         breakdown.exemption_score],
                ["District variance", breakdown.district_variance_score],
                ["Incidence",         breakdown.incidence_score],
                ["Wastewater",        breakdown.wastewater_score],
                ["Mobility",          breakdown.mobility_score],
                ["Community",         breakdown.community_score],
              ] as [string, number][]).map(([label, val]) => (
                <div key={label} style={{ display: "flex", justifyContent: "space-between" }}>
                  <span>{label}</span>
                  <span style={{ fontFamily: "monospace", fontWeight: 600 }}>{val.toFixed(1)}</span>
                </div>
              ))}
            </div>
          </div>

          {/* District drill-down */}
          <DistrictTable fips={breakdown.fips} onSelect={(d) => {
            setSelectedDistrict(d);
            setActiveTab("data");
          }} />

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
        </div>

        {/* AI Analysis tab */}
        <div style={{ display: activeTab === "ai" ? "block" : "none", height: "100%", overflowY: "auto", padding: 16 }}>
          <AIAnalyst
            fips={breakdown.fips}
            countyName={breakdown.county_name}
          />
        </div>
      </div>
    </div>
  );
}
