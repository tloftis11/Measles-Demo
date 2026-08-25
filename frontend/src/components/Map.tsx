import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

const TIER_COLOR: Record<string, string> = {
  CRITICAL: "#C22828",
  HIGH:     "#D45F00",
  MODERATE: "#C9920C",
  LOW:      "#1E8A4C",
};

const NO_DATA_STYLE: L.PathOptions = {
  color: "#b0bec5", weight: 0.5, fillColor: "#eceff1", fillOpacity: 0.45,
};

const STATE_VIEW: Record<string, { center: [number, number]; zoom: number }> = {
  tx: { center: [31.5, -99.5],  zoom: 6   },
  id: { center: [44.5, -114.5], zoom: 6   },
  pa: { center: [40.9, -77.8],  zoom: 7   },
};

function tierStyle(tier: string | null, thin = false): L.PathOptions {
  if (!tier || !TIER_COLOR[tier]) return NO_DATA_STYLE;
  return {
    color: "#fff",
    weight: thin ? 0.4 : 0.8,
    fillColor: TIER_COLOR[tier],
    fillOpacity: 0.78,
  };
}

type ViewMode = "county" | "district";

export interface DistrictMapProps {
  lea_geoid: string;
  district_name: string;
  county_name: string;
  county_fips: string;
  mmr_coverage_pct: number;
  composite_score: number;
  coverage_score: number;
  surveillance_score: number;
  network_score: number;
  risk_tier: string;
}

interface Props {
  state: string;
  onSelect: (fips: string) => void;
  onSelectDistrict?: (district: DistrictMapProps) => void;
  selectedFips: string | null;
}

export function HotspotMap({ state, onSelect, onSelectDistrict, selectedFips }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef        = useRef<L.Map | null>(null);
  const layerRef      = useRef<L.GeoJSON | null>(null);
  const selectedRef   = useRef<string | null>(null);
  const [viewMode, setViewMode]   = useState<ViewMode>("county");
  const [loading, setLoading]     = useState(false);
  const viewModeRef = useRef<ViewMode>("county");

  // Keep ref in sync for use inside closures
  useEffect(() => { viewModeRef.current = viewMode; }, [viewMode]);

  // Init map once
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const { center, zoom } = STATE_VIEW[state] ?? STATE_VIEW.tx;
    mapRef.current = L.map(containerRef.current, {
      center,
      zoom,
      zoomSnap: 0.5,
    });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap contributors",
      opacity: 0.35,
    }).addTo(mapRef.current);

    return () => {
      mapRef.current?.remove();
      mapRef.current = null;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Re-center and reload when state changes
  useEffect(() => {
    if (!mapRef.current) return;
    const { center, zoom } = STATE_VIEW[state] ?? STATE_VIEW.tx;
    mapRef.current.setView(center, zoom);
    selectedRef.current = null;
    setViewMode("county");
  }, [state]);

  // Load/reload the GeoJSON layer whenever viewMode or state changes
  useEffect(() => {
    if (!mapRef.current) return;

    // Remove old layer
    if (layerRef.current) {
      mapRef.current.removeLayer(layerRef.current);
      layerRef.current = null;
    }

    const isDistrict = viewMode === "district";
    const url = isDistrict
      ? `${BASE}/api/geojson/${state}/districts`
      : `${BASE}/api/geojson/${state}/counties`;

    setLoading(true);

    fetch(url)
      .then((r) => r.json())
      .then((geojson) => {
        const map = mapRef.current;
        if (!map) return;

        layerRef.current = L.geoJSON(geojson, {
          style: (feature) => {
            const p = feature?.properties ?? {};
            return tierStyle(p.risk_tier, isDistrict);
          },
          onEachFeature: (feature, layer) => {
            const p    = feature.properties ?? {};
            const fips = (p.fips ?? "") as string;

            if (p.has_score) {
              const label = isDistrict
                ? `<strong>${p.district_name}</strong><br/>` +
                  `${p.county_name} County<br/>` +
                  `MMR coverage: <strong>${Number(p.mmr_coverage_pct).toFixed(1)}%</strong> — ${p.risk_tier}`
                : `<strong>${p.county_name}</strong><br/>` +
                  `Score: <strong>${Number(p.composite_score).toFixed(1)}</strong> — ${p.risk_tier}`;

              layer.bindTooltip(label, { sticky: true, opacity: 0.95 });
              layer.on("click", () => {
                if (!fips) return;
                if (isDistrict && onSelectDistrict) {
                  onSelectDistrict({
                    lea_geoid:          String(p.lea_geoid ?? ""),
                    district_name:      String(p.district_name ?? ""),
                    county_name:        String(p.county_name ?? ""),
                    county_fips:        fips,
                    mmr_coverage_pct:   Number(p.mmr_coverage_pct ?? 0),
                    composite_score:    Number(p.composite_score ?? 0),
                    coverage_score:     Number(p.coverage_score ?? 0),
                    surveillance_score: Number(p.surveillance_score ?? 0),
                    network_score:      Number(p.network_score ?? 0),
                    risk_tier:          String(p.risk_tier ?? ""),
                  });
                } else {
                  onSelect(fips);
                }
              });
              layer.on("mouseover", function () {
                (this as L.Path).setStyle({ weight: isDistrict ? 1.5 : 2, color: "#1A2744" });
              });
              layer.on("mouseout", function () {
                layerRef.current?.resetStyle(this as L.Path);
                if (selectedRef.current === fips) {
                  (this as L.Path).setStyle({ weight: 2.5, color: "#1A2744" });
                }
              });
            } else {
              const noDataLabel = isDistrict
                ? `${p.district_name ?? "District"} — No coverage data`
                : `${p.county_name ?? "County"} — No data`;
              layer.bindTooltip(noDataLabel, { sticky: true, opacity: 0.7 });
            }
          },
        }).addTo(map);

        setLoading(false);
        // Re-apply selected highlight if any
        if (selectedRef.current) applyHighlight(selectedRef.current);
      })
      .catch((err) => {
        console.error("GeoJSON load failed:", err);
        setLoading(false);
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewMode, state]);

  function applyHighlight(fips: string | null) {
    const layer = layerRef.current;
    if (!layer) return;
    layer.eachLayer((l) => {
      const gl = l as L.GeoJSON & { feature?: GeoJSON.Feature };
      const f  = gl.feature?.properties?.fips;
      if (!gl.feature?.properties?.has_score) return;
      if (f === fips) {
        (l as L.Path).setStyle({ weight: 2.5, color: "#1A2744", fillOpacity: 0.92 });
        (l as L.Path).bringToFront();
      } else {
        layerRef.current?.resetStyle(l as L.Path);
      }
    });
  }

  // Highlight selected county/district
  useEffect(() => {
    selectedRef.current = selectedFips;
    applyHighlight(selectedFips);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedFips]);

  const showDistrictToggle = true;

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <div ref={containerRef} style={{ width: "100%", height: "100%" }} />

      {/* View toggle — top left overlay */}
      {showDistrictToggle && (
        <div style={{
          position: "absolute", top: 12, left: 12, zIndex: 1000,
          background: "#fff", borderRadius: 8,
          boxShadow: "0 2px 10px rgba(0,0,0,0.15)",
          overflow: "hidden", display: "flex",
          fontFamily: "'Trebuchet MS', Arial, sans-serif",
        }}>
          {(["county", "district"] as ViewMode[]).map((mode) => (
            <button
              key={mode}
              onClick={() => setViewMode(mode)}
              style={{
                padding: "7px 14px",
                fontSize: 11, fontWeight: 700,
                fontFamily: "'Trebuchet MS', Arial, sans-serif",
                letterSpacing: "0.05em",
                background: viewMode === mode ? "#1A2744" : "#fff",
                color: viewMode === mode ? "#fff" : "#4A5E78",
                border: "none",
                cursor: viewMode === mode ? "default" : "pointer",
                borderRight: mode === "county" ? "1px solid #e0e8f4" : "none",
                transition: "background 0.12s, color 0.12s",
              }}
            >
              {mode === "county" ? "Counties" : "School Districts"}
            </button>
          ))}
        </div>
      )}

      {/* Loading indicator */}
      {loading && (
        <div style={{
          position: "absolute", top: 50, left: "50%", transform: "translateX(-50%)",
          zIndex: 1000, background: "#fff", borderRadius: 6,
          boxShadow: "0 2px 10px rgba(0,0,0,0.12)",
          padding: "8px 18px", fontSize: 12,
          fontFamily: "'Trebuchet MS', Arial, sans-serif", color: "#4A5E78",
        }}>
          Loading {viewMode === "district" ? "school districts" : "counties"}…
        </div>
      )}

      {/* District-view note */}
      {viewMode === "district" && !loading && (
        <div style={{
          position: "absolute", bottom: 90, left: 12, zIndex: 1000,
          background: "#fff8f0", border: "1px solid #f0d8b8",
          borderRadius: 6, padding: "7px 12px",
          fontSize: 11, color: "#7A5020",
          fontFamily: "'Trebuchet MS', Arial, sans-serif", maxWidth: 240,
          boxShadow: "0 1px 6px rgba(0,0,0,0.08)",
        }}>
          Showing <strong>coverage risk</strong> (MMR%) at district level.
          Click any district for district details.
        </div>
      )}
    </div>
  );
}
