export type RiskTier = "LOW" | "MODERATE" | "HIGH" | "CRITICAL";

export interface CountyScore {
  fips: string;
  county_name: string;
  full_name: string;
  population: number;
  coverage_score: number;
  surveillance_score: number;
  network_score: number;
  composite_score: number;
  risk_tier: RiskTier;
}

export interface ScoreBreakdown extends CountyScore {
  coverage_gap_score: number;
  exemption_score: number;
  district_variance_score: number;
  incidence_score: number;
  wastewater_score: number;
  positivity_score: number;
  mobility_score: number;
  community_score: number;
  border_score: number;
  score_velocity: number;
  velocity_modifier: number;
  mmr_coverage_pct: number;
  nonmedical_exempt_pct: number;
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

export interface SimResult {
  fips: string;
  peak_day: number;
  peak_infected: number;
  total_attack_rate: number;
  herd_immunity_threshold: number;
  reached_herd_immunity: boolean;
  trajectory: SEIRPoint[];
}
