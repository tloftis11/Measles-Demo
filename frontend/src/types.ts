export type RiskTier = "LOW" | "MODERATE" | "HIGH" | "CRITICAL";

export type ScoringSource = "hermesboost" | "internal_engine";

export interface CountyScore {
  fips: string;
  county_name: string;
  full_name: string;
  population: number;
  coverage_score: number | null;
  surveillance_score: number | null;
  network_score: number;
  composite_score: number;
  risk_tier: RiskTier;
  scoring_source?: ScoringSource;
  probability_pct?: number | null;
  predicted_magnitude?: number | null;
}

export interface ScoreBreakdown extends CountyScore {
  // Only populated when scoring_source === "internal_engine" -- null for
  // HermesBoost-scored (Texas) counties, which have no hand-weighted
  // sub-scores to report.
  coverage_gap_score: number | null;
  exemption_score: number | null;
  district_variance_score: number | null;
  incidence_score: number | null;
  wastewater_score: number | null;
  positivity_score: number | null;
  mobility_score: number | null;
  community_score: number | null;
  border_score: number | null;
  score_velocity: number | null;
  velocity_modifier: number | null;
  mmr_coverage_pct: number | null;
  nonmedical_exempt_pct: number | null;
  recent_cases: number;
}

export interface SEIRPoint {
  day: number;
  S: number;
  E: number;
  I: number;
  R: number;
  new_cases: number;
}

export interface SchoolDistrict {
  lea_id: string;
  district_name: string;
  enrollment: number;
  mmr_coverage_pct: number;
  nonmedical_exempt_pct: number;
  medical_exempt_pct: number;
  school_year: string;
}

export interface DistrictBreakdown {
  fips: string;
  county_name: string;
  districts: SchoolDistrict[];
}

export interface ScoreHistoryPoint {
  date: string;
  score: number;
  tier: string;
}

export interface NewsBriefing {
  is_fresh: boolean;
  fetched_at: string | null;
  briefing: string | null;
  sources: string[];
}

export interface SimResult {
  fips: string;
  peak_day: number;
  peak_infected: number;
  total_attack_rate: number;
  herd_immunity_threshold: number;
  reached_herd_immunity: boolean;
  trajectory: SEIRPoint[];
}
