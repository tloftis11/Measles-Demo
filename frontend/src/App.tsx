import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { HotspotMap } from "./components/Map";
import type { DistrictMapProps } from "./components/Map";
import { AnalysisSidebar } from "./components/AnalysisSidebar";
import { SimPanel } from "./components/SimPanel";
import { QueryPanel } from "./components/QueryPanel";
import { MethodologyPanel } from "./components/MethodologyPanel";
import { NewsPanel } from "./components/NewsPanel";
import type { ScoreBreakdown, SchoolDistrict } from "./types";

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

type Tab = "map" | "simulate" | "query" | "methodology" | "news";
type StateAbbr = "tx" | "id" | "pa";

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
  news:        "News",
};

const STATE_LABELS: Record<StateAbbr, string> = {
  tx: "Texas",
  id: "Idaho",
  pa: "Pennsylvania",
};

export default function App() {
  const [tab, setTab] = useState<Tab>("map");
  const [selectedState, setSelectedState] = useState<StateAbbr>("tx");
  const [selectedFips, setSelectedFips] = useState<string | null>(null);
  const [pendingDistrictLeaId, setPendingDistrictLeaId] = useState<string | null>(null);

  const { data: breakdown, isLoading: breakdownLoading } = useQuery({
    queryKey: ["breakdown", selectedState, selectedFips],
    queryFn: () => api.countyBreakdown(selectedState, selectedFips!),
    enabled: !!selectedFips,
  });

  const { data: scores } = useQuery({
    queryKey: ["scores", selectedState],
    queryFn:  () => api.stateScores(selectedState),
    staleTime: 10 * 60 * 1000,
  });

  // Fetch district list when user clicks a district on the map
  const { data: countyDistricts } = useQuery({
    queryKey: ["countyDistricts", selectedState, selectedFips, pendingDistrictLeaId],
    queryFn: () => api.countyDistricts(selectedState, selectedFips!),
    enabled: !!selectedFips && !!pendingDistrictLeaId,
    staleTime: 5 * 60 * 1000,
  });

  // Find the matching SchoolDistrict for the map-clicked district
  const autoSelectedDistrict = useMemo((): SchoolDistrict | null => {
    if (!pendingDistrictLeaId || !countyDistricts) return null;
    return countyDistricts.districts.find(
      (d) => d.lea_id === pendingDistrictLeaId
    ) ?? null;
  }, [pendingDistrictLeaId, countyDistricts]);

  const handleSelectDistrict = (district: DistrictMapProps) => {
    setSelectedFips(district.county_fips);
    setPendingDistrictLeaId(district.lea_geoid);
    setTab("map");
  };

  const handleStateChange = (s: StateAbbr) => {
    setSelectedState(s);
    setSelectedFips(null);
    setPendingDistrictLeaId(null);
  };

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
          {(["map", "simulate", "query", "methodology", "news"] as Tab[]).map((t) => (
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

        {/* State selector */}
        <div style={{
          display: "flex", alignItems: "center", gap: 6,
          marginLeft: 8,
          background: "rgba(255,255,255,0.07)",
          border: "1px solid rgba(255,255,255,0.15)",
          borderRadius: 6, padding: "0 4px", height: 32,
        }}>
          {(["tx", "id", "pa"] as StateAbbr[]).map((s) => (
            <button
              key={s}
              onClick={() => handleStateChange(s)}
              title={STATE_LABELS[s]}
              style={{
                background: selectedState === s ? "#E8700A" : "transparent",
                color: selectedState === s ? "#fff" : "#7A99B8",
                border: "none",
                borderRadius: 4,
                padding: "0 10px",
                height: 24,
                fontSize: 11,
                fontWeight: 700,
                fontFamily: "'Trebuchet MS', Arial, sans-serif",
                letterSpacing: "0.08em",
                cursor: "pointer",
                textTransform: "uppercase",
                transition: "all 0.12s",
              }}
            >
              {s.toUpperCase()}
            </button>
          ))}
        </div>

        <div style={{ marginLeft: "auto" }}>
          <a
            href={`${API_BASE}/api/scores/${selectedState}/export/csv`}
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
              state={selectedState}
              onSelect={(fips) => { setSelectedFips(fips); setPendingDistrictLeaId(null); setTab("map"); }}
              onSelectDistrict={handleSelectDistrict}
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
              initialDistrict={autoSelectedDistrict}
            />
          </div>
        </div>

        {/* SIMULATE TAB */}
        {tab === "simulate" && (
          <SimPanel
            counties={scores ?? []}
            initialFips={selectedFips ?? (selectedState === "tx" ? "48169" : selectedState === "id" ? "16001" : "42003")}
          />
        )}

        {/* QUERY TAB */}
        {tab === "query" && <QueryPanel state={selectedState} stateName={STATE_LABELS[selectedState]} />}

        {/* METHODOLOGY TAB */}
        {tab === "methodology" && <MethodologyPanel />}

        {/* NEWS TAB */}
        {tab === "news" && <NewsPanel state={selectedState} />}
      </div>
    </div>
  );
}
