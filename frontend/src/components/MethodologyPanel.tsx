const TIER_COLOR: Record<string, string> = {
  CRITICAL: "#C22828", HIGH: "#D45F00", MODERATE: "#C9920C", LOW: "#1E8A4C",
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 32 }}>
      <div style={{
        fontSize: 10, fontWeight: 700, letterSpacing: "0.14em",
        textTransform: "uppercase", color: "#E8700A",
        borderBottom: "1px solid #e8eef6", paddingBottom: 6, marginBottom: 14,
      }}>{title}</div>
      {children}
    </div>
  );
}

function Formula() {
  return (
    <div style={{
      background: "#f6f8fc", border: "1px solid #D0DAE8",
      borderRadius: 8, padding: "16px 20px", fontFamily: "monospace",
      fontSize: 13, color: "#1A2744", lineHeight: 2,
    }}>
      <div style={{ marginBottom: 8 }}>
        <strong>HotspotScore</strong> = 0.40 × CoverageScore + 0.35 × SurveillanceScore + 0.25 × NetworkScore
      </div>
      <div style={{ fontSize: 11, color: "#7A92AB", fontFamily: "'Trebuchet MS', Arial, sans-serif" }}>
        All sub-scores are normalized to 0–100. The composite score maps directly to risk tiers.
      </div>
    </div>
  );
}

const LAYERS = [
  {
    name: "Vaccination Coverage & Exemption",
    weight: "40%",
    color: "#1E8A4C",
    components: [
      { name: "Coverage gap sub-score", formula: "max(0, 95 − MMR%) × 3.5", max: 60, note: "Penalizes distance from 95% herd immunity threshold" },
      { name: "Exemption pressure sub-score", formula: "Non-medical exempt% × 8", max: 40, note: "Non-medical exemptions signal organized resistance to vaccination" },
    ],
  },
  {
    name: "Case & Lab Surveillance",
    weight: "35%",
    color: "#D45F00",
    components: [
      { name: "Incidence sub-score", formula: "(cases / population × 100,000) × 20", max: 60, note: "Confirmed + suspect cases in the last 90 days per 100k population" },
      { name: "Wastewater signal", formula: "wastewater_index × 25", max: 25, note: "Environmental surveillance; 0–1 scale from NWSS" },
      { name: "Lab positivity", formula: "positivity% × 3", max: 15, note: "Percent of measles specimens testing positive" },
    ],
  },
  {
    name: "Network & Connectivity",
    weight: "25%",
    color: "#2F5FA8",
    components: [
      { name: "Mobility index", formula: "mobility × 40", max: 40, note: "SafeGraph/mobility data; higher mobility = higher transmission potential" },
      { name: "Community clustering", formula: "religious_idx × 40", max: 40, note: "Proxy for tight-knit communities with shared social networks" },
      { name: "Border adjacency", formula: "20 if border county", max: 20, note: "Counties on the TX-Mexico border have elevated cross-border exposure" },
    ],
  },
];

const TIERS = [
  { tier: "CRITICAL", range: "75–100", action: "Immediate public health emergency response. Contact tracing, targeted outbreak investigation, school notifications." },
  { tier: "HIGH",     range: "50–75",  action: "Enhanced surveillance, outreach to undervaccinated communities, readiness alert to local health dept." },
  { tier: "MODERATE", range: "25–50",  action: "Routine monitoring, school exemption audits, provider outreach for catch-up vaccination." },
  { tier: "LOW",      range: "0–25",   action: "Standard surveillance. No immediate action required beyond routine reporting." },
];

const SOURCES = [
  {
    layer: "Vaccination Coverage",
    name: "TX DSHS School Vaccination Coverage Survey",
    grain: "School district (aggregated to county)",
    refresh: "Annual — school year",
    url: "https://www.dshs.texas.gov/immunize/coverage/",
    notes: "Public data. School-level MMR%, medical exemption%, and non-medical exemption% for enrolled students.",
  },
  {
    layer: "Case Surveillance",
    name: "CDC NNDSS Measles Case Reports",
    grain: "County",
    refresh: "Weekly",
    url: "https://wonder.cdc.gov/nndss/",
    notes: "Confirmed and suspect measles cases reported to CDC. Lag of 1–2 weeks possible.",
  },
  {
    layer: "Environmental Surveillance",
    name: "CDC National Wastewater Surveillance System (NWSS)",
    grain: "Sewershed (mapped to county)",
    refresh: "Bi-weekly",
    url: "https://www.cdc.gov/nwss/",
    notes: "Wastewater environmental signal for measles RNA. Normalized to 0–1 index.",
  },
  {
    layer: "Network / Mobility",
    name: "SafeGraph Community Mobility Patterns",
    grain: "County",
    refresh: "Monthly",
    url: "https://www.safegraph.com/",
    notes: "Purchasable data. Device-level mobility aggregated to county. Proxy for transmission network connectivity.",
  },
  {
    layer: "Geographic Boundaries",
    name: "Census TIGER/Line 2023",
    grain: "County + school district polygons",
    refresh: "Annual",
    url: "https://www.census.gov/geo/maps-data/data/tiger-line.html",
    notes: "Used for choropleth map and school district boundary overlay.",
  },
];

export function MethodologyPanel() {
  return (
    <div style={{
      height: "100%", overflowY: "auto", padding: "28px 48px 48px",
      fontFamily: "'Trebuchet MS', Arial, sans-serif", maxWidth: 900, margin: "0 auto",
    }}>
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.14em", color: "#7A92AB", marginBottom: 6 }}>
          Technical Reference
        </div>
        <h1 style={{ margin: 0, fontSize: 26, fontWeight: 700, color: "#1A2744" }}>
          Measles Hotspot Detection — Methodology
        </h1>
        <p style={{ margin: "10px 0 0", fontSize: 13, color: "#4A5E78", lineHeight: 1.7, maxWidth: 680 }}>
          A three-layer composite scoring model that translates public health surveillance data into a
          county-level risk signal for measles outbreak potential. Designed for CDC and state health
          department use as an early-warning triage tool.
        </p>
      </div>

      <Section title="Composite Score Formula">
        <Formula />
      </Section>

      <Section title="Risk Tiers">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 12 }}>
          {TIERS.map(({ tier, range, action }) => (
            <div key={tier} style={{
              border: `1px solid ${TIER_COLOR[tier]}22`,
              borderLeft: `4px solid ${TIER_COLOR[tier]}`,
              borderRadius: 6, padding: "12px 14px", background: "#fff",
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                <span style={{ fontWeight: 700, fontSize: 13, color: TIER_COLOR[tier] }}>{tier}</span>
                <span style={{ fontFamily: "monospace", fontSize: 12, color: "#7A92AB" }}>{range}</span>
              </div>
              <p style={{ margin: 0, fontSize: 12, color: "#4A5E78", lineHeight: 1.6 }}>{action}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Scoring Layers">
        {LAYERS.map((layer) => (
          <div key={layer.name} style={{ marginBottom: 24 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
              <div style={{ width: 10, height: 10, borderRadius: 2, background: layer.color }} />
              <span style={{ fontWeight: 700, fontSize: 14, color: "#1A2744" }}>{layer.name}</span>
              <span style={{
                background: layer.color + "22", color: layer.color,
                borderRadius: 10, padding: "2px 10px", fontSize: 11, fontWeight: 700,
              }}>{layer.weight} weight</span>
            </div>
            <div style={{ background: "#fff", border: "1px solid #D0DAE8", borderRadius: 6, overflow: "hidden" }}>
              {layer.components.map((c, i) => (
                <div key={c.name} style={{
                  padding: "10px 14px",
                  borderBottom: i < layer.components.length - 1 ? "1px solid #f0f4f8" : "none",
                  display: "grid", gridTemplateColumns: "200px 1fr 48px",
                  gap: 12, alignItems: "start",
                }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#1A2744" }}>{c.name}</div>
                  <div>
                    <div style={{ fontFamily: "monospace", fontSize: 11, color: "#2F5FA8", marginBottom: 3 }}>{c.formula}</div>
                    <div style={{ fontSize: 11, color: "#7A92AB" }}>{c.note}</div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: 9, color: "#7A92AB", textTransform: "uppercase" }}>max</div>
                    <div style={{ fontFamily: "monospace", fontWeight: 700, fontSize: 13, color: "#1A2744" }}>{c.max}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </Section>

      <Section title="Data Sources">
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {SOURCES.map((s) => (
            <div key={s.name} style={{
              background: "#fff", border: "1px solid #D0DAE8", borderRadius: 6,
              padding: "12px 16px", display: "grid",
              gridTemplateColumns: "140px 1fr", gap: 16,
            }}>
              <div>
                <div style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.08em", color: "#7A92AB" }}>Layer</div>
                <div style={{ fontSize: 12, fontWeight: 700, color: "#1A2744", marginTop: 2 }}>{s.layer}</div>
                <div style={{ fontSize: 10, color: "#7A92AB", marginTop: 6 }}>
                  <div>{s.grain}</div>
                  <div>{s.refresh}</div>
                </div>
              </div>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#1A2744", marginBottom: 4 }}>{s.name}</div>
                <div style={{ fontSize: 12, color: "#4A5E78", lineHeight: 1.6 }}>{s.notes}</div>
              </div>
            </div>
          ))}
        </div>
      </Section>

      <Section title="SEIR Simulation Model">
        <div style={{ background: "#fff", border: "1px solid #D0DAE8", borderRadius: 6, padding: "16px 20px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16, marginBottom: 16 }}>
            {[
              ["R₀ (basic reproduction number)", "12–18 (default 15)"],
              ["Incubation period", "11 days"],
              ["Infectious period", "8 days"],
              ["Vaccine efficacy", "97%"],
              ["Herd immunity threshold", "1 − 1/R₀ (≈92–95% at R₀=15)"],
              ["Model type", "Discrete-time deterministic SEIR"],
            ].map(([param, val]) => (
              <div key={param as string}>
                <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", color: "#7A92AB" }}>{param}</div>
                <div style={{ fontFamily: "monospace", fontSize: 13, fontWeight: 700, color: "#1A2744", marginTop: 2 }}>{val}</div>
              </div>
            ))}
          </div>
          <div style={{ fontSize: 12, color: "#4A5E78", lineHeight: 1.7 }}>
            The effective immunity fraction is computed as (MMR coverage %) × 0.97 (vaccine efficacy).
            Susceptibles = population × (1 − effective immunity) − seed cases.
            The intervention scenario re-runs the model with a user-specified target coverage percentage,
            allowing side-by-side comparison of outbreak trajectories with and without a vaccination campaign.
          </div>
        </div>
      </Section>
    </div>
  );
}
