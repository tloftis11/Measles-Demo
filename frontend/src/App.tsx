import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { HotspotMap } from "./components/Map";
import { AnalysisSidebar } from "./components/AnalysisSidebar";
import { SimPanel } from "./components/SimPanel";
import { QueryPanel } from "./components/QueryPanel";
import { MethodologyPanel } from "./components/MethodologyPanel";
import type { ScoreBreakdown } from "./types";

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

type Tab = "map" | "simulate" | "query" | "methodology";

const TIER_COLOR: Record<string, string> = {
  CRITICAL: "#C22828",
  HIGH:     "#D45F00",
  MODERATE: "#C9920C",
  LOW:      "#1E8A4C",
};

const TAB_LABELS: Record<Tab, string> = {
  map:         "Map",
  simulate:    "Simulate",
  query:       "Query",
  methodology: "Methodology",
};

export default function App() {
  const [tab, setTab] = useState<Tab>("map");
  const [selectedFips, setSelectedFips] = useState<string | null>("48169"); // Gaines County default

  const { data: breakdown, isLoading: breakdownLoading } = useQuery({
    queryKey: ["breakdown", "tx", selectedFips],
    queryFn: () => api.countyBreakdown("tx", selectedFips!),
    enabled: !!selectedFips,
  });

  const { data: scores } = useQuery({
    queryKey: ["scores", "tx"],
    queryFn:  () => api.stateScores("tx"),
    staleTime: 10 * 60 * 1000,
  });

  return (
    <div style={{
      display: "flex", flexDirection: "column", height: "100vh",
      fontFamily: "'Trebuchet MS', Arial, sans-serif", background: "#f6f8fc",
    }}>
      {/* ── Header ── */}
      <header style={{
        background: "#1A2744", color: "#fff",
        padding: "0 24px",
        display: "flex", alignItems: "center", gap: 24,
        flexShrink: 0, height: 52,
      }}>
        <div style={{ fontSize: 15, fontWeight: 700 }}>
          Measles Hotspot Detection
        </div>

        <nav style={{ display: "flex", gap: 2, marginLeft: 16 }}>
          {(["map", "simulate", "query", "methodology"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              style={{
                background: tab === t ? "rgba(255,255,255,0.12)" : "transparent",
                border: "none",
                borderBottom: tab === t ? "2px solid #E8700A" : "2px solid transparent",
                color: tab === t ? "#fff" : "#7A99B8",
                padding: "0 14px",
                height: 52,
                fontSize: 12,
                fontWeight: tab === t ? 700 : 400,
                fontFamily: "'Trebuchet MS', Arial, sans-serif",
                letterSpacing: "0.06em",
                cursor: "pointer",
                transition: "color 0.12s, background 0.12s",
              }}
            >
              {TAB_LABELS[t]}
            </button>
          ))}
        </nav>

        <div style={{ marginLeft: "auto" }}>
          <a
            href={`${API_BASE}/api/scores/tx/export/csv`}
            download
            style={{
              fontSize: 11, fontWeight: 700, color: "#E8700A",
              background: "rgba(232,112,10,0.12)", border: "1px solid rgba(232,112,10,0.3)",
              borderRadius: 5, padding: "4px 10px", textDecoration: "none",
              fontFamily: "'Trebuchet MS', Arial, sans-serif", letterSpacing: "0.04em",
            }}
          >
            Export CSV
          </a>
        </div>
      </header>

      {/* ── Body ── */}
      <div style={{ flex: 1, overflow: "hidden", position: "relative" }}>

        {/* MAP TAB — always a flex row: 60% map + 40% sidebar */}
        <div style={{
          display: tab === "map" ? "flex" : "none",
          height: "100%", width: "100%",
        }}>
          {/* Left: map + legend overlay */}
          <div style={{ flex: "0 0 60%", position: "relative", overflow: "hidden" }}>
            <HotspotMap
              onSelect={(fips) => { setSelectedFips(fips); setTab("map"); }}
              selectedFips={selectedFips}
            />

            {/* Legend */}
            <div style={{
              position: "absolute", bottom: 16, left: 16, zIndex: 1000,
              background: "#fff", borderRadius: 8, padding: "10px 14px",
              boxShadow: "0 2px 12px rgba(0,0,0,0.12)", fontSize: 11,
              fontFamily: "'Trebuchet MS', Arial, sans-serif",
            }}>
              <div style={{
                fontWeight: 700, color: "#1A2744", marginBottom: 6,
                textTransform: "uppercase", letterSpacing: "0.08em", fontSize: 10,
              }}>
                Risk Tier
              </div>
              {(["CRITICAL", "HIGH", "MODERATE", "LOW"] as const).map((tier) => (
                <div key={tier} style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 4 }}>
                  <div style={{ width: 14, height: 10, borderRadius: 2, background: TIER_COLOR[tier] }} />
                  <span style={{ color: "#4A5E78" }}>{tier}</span>
                </div>
              ))}
              <div style={{
                marginTop: 8, borderTop: "1px solid #e8eef6",
                paddingTop: 6, color: "#7A92AB", lineHeight: 1.5,
              }}>
                Gray = no score data<br />Click county for details
              </div>
            </div>
          </div>

          {/* Right: analysis sidebar */}
          <div style={{ flex: "0 0 40%", height: "100%", overflow: "hidden" }}>
            <AnalysisSidebar
              breakdown={breakdown as ScoreBreakdown | undefined}
              isLoading={breakdownLoading && !!selectedFips}
              onSimulate={() => setTab("simulate")}
            />
          </div>
        </div>

        {/* SIMULATE TAB */}
        {tab === "simulate" && (
          <SimPanel
            counties={scores ?? []}
            initialFips={selectedFips ?? "48169"}
          />
        )}

        {/* QUERY TAB */}
        {tab === "query" && <QueryPanel />}

        {/* METHODOLOGY TAB */}
        {tab === "methodology" && <MethodologyPanel />}
      </div>
    </div>
  );
}
