export type ArchetypeKey = "membership" | "dine_in" | "takeaway" | "retail" | "appointment" | "lodging";
export type Goal = "profit" | "low_risk" | "break_even" | "growth";
export type Objective = "start_new" | "improve_existing" | "compare_locations" | "test_strategy" | "diagnose";

export interface User {
  id: string;
  email: string;
  name: string;
  preferences: Record<string, unknown>;
}

export interface ParamDef {
  value: number;
  low: number;
  high: number;
  unit: string;
  description: string;
  status: string;
}

export interface CapacityField {
  key: string;
  label: string;
  unit: string;
  default: number | null;
  help: string;
  kind: string;
}

export interface Archetype {
  key: ArchetypeKey;
  label: string;
  description: string;
  unit_label: string;
  price_label: string;
  period_note: string;
  demand_base: string;
  params: Record<string, ParamDef>;
  segments: { key: string; label: string; share: number; wtp_multiplier: number }[];
  capacity_fields: CapacityField[];
  default_catchment_km: number;
  limitations: string[];
}

export interface Category {
  query: string;
  key: string;
  label: string;
  archetype: ArchetypeKey;
  filters: string[];
  method: string;
  confidence: number;
  needs_confirmation: boolean;
  alternatives: { key: string; label: string; archetype: ArchetypeKey; score: number }[];
  notes: string[];
  archetype_detail?: Archetype;
  ai_available?: boolean;
}

export interface Catchment {
  mode: "radius" | "isochrone";
  radius_km: number | null;
  minutes: number | null;
  profile: "foot-walking" | "driving-car" | "cycling-regular";
}

export interface Location {
  id: string;
  label: string;
  address: string;
  lat: number;
  lng: number;
  catchment: Catchment;
  manual_population: number | null;
}

export interface ScenarioInputs {
  price: number;
  quality: number;
  marketing_spend: number;
  reference_price: number | null;
  variable_cost_per_unit: number | null;
  capacity: Record<string, number>;
  rent: number;
  payroll: number;
  utilities: number;
  other_fixed: number;
  startup_cost: number;
  param_overrides: Record<string, number>;
  seed: number;
}

export interface Scenario {
  id: string;
  name: string;
  is_baseline: boolean;
  location_id: string;
  inputs: ScenarioInputs;
  latest_run: { id: string; status: string; finished_at: string | null; stale: boolean; model_version: string } | null;
}

export interface Project {
  id: string;
  name: string;
  objective: Objective;
  decision_goal: Goal;
  category: Category;
  profile: Record<string, unknown>;
  status: string;
  is_demo: boolean;
  created_at: string;
  updated_at: string;
  locations: Location[];
  summary: { scenario: string; units_sold: number; unit_label: string; operating_profit: number; prob_loss: number | null; run_at: string | null } | null;
  scenarios?: Scenario[];
  archetype?: Archetype;
  data_kinds?: { connected_sources: boolean; user_provided: boolean; demo: boolean; synthetic_estimates: boolean; user_competitors: boolean };
  snapshots?: Record<string, { id: string; retrieved_at: string; status: string } | null>;
}

export interface Provenance {
  source: string;
  name: string;
  kind: string;
  license?: string;
  attribution?: string;
  url?: string;
  coverage_note?: string;
  retrieved_at?: string;
  source_updated_at?: string | null;
  detail?: string;
  status?: string;
  from_cache?: boolean;
  layer?: string;
}

export interface Zone {
  lat: number;
  lng: number;
  population: number;
  buildings?: number;
  activity?: number;
}

export interface Snapshot {
  id: string;
  location_id: string;
  retrieved_at: string;
  status: "complete" | "partial" | "failed";
  catchment_geojson: { type: "Polygon"; coordinates: number[][][] };
  catchment_method: "radius" | "isochrone";
  zones: Zone[];
  population: { method: string; source: string | null; total: number | null; radius_km?: number; zones?: number; spacing_km?: number; buildings_used?: number };
  sources: Provenance[];
  coverage: { level: string; note: string; signals: { signal: string; value: number; why: string }[]; method: string };
  activity_points: { lat: number; lng: number; name: string; kind: string }[];
  errors: { source: string; message: string; fallback?: string }[];
}

export interface CompetitorRec {
  id: string;
  source: "osm" | "user" | "demo";
  source_ref: string | null;
  name: string;
  lat: number;
  lng: number;
  category_tag: string | null;
  public_attributes: Record<string, string>;
  price: number | null;
  price_status: string;
  quality: number | null;
  quality_status: string;
  is_hypothetical: boolean;
  active: boolean;
  notes: string;
  source_updated_at: string | null;
  retrieved_at: string | null;
  osm_url: string | null;
  distance_km?: number;
}

export interface MarketData {
  location: Location;
  snapshot: Snapshot | null;
  loading_snapshot_id: string | null;
  competitors: CompetitorRec[];
  locations: Location[];
  category: Category;
}

export interface Pct {
  mean?: number | null;
  p10: number | null;
  p50: number | null;
  p90: number | null;
}

export interface SimResult {
  model_version: string;
  archetype: ArchetypeKey;
  unit_label: string;
  summary: {
    in_market_units: number;
    modeled_demand_units: number;
    units_sold: number;
    capacity_units: number;
    capacity_bound: boolean;
    capture_of_in_market: number;
    captured_by_all_modeled: number;
    awareness: number;
    price: number;
    reference_price: number;
    reference_price_status: string;
    variable_cost_per_unit: number;
    variable_cost_status: string;
  };
  finance: {
    period: string;
    revenue: number;
    variable_cost: number;
    fixed_cost: number;
    fixed_breakdown: Record<string, number>;
    operating_profit: number;
    unit_margin: number;
    break_even_units: number | null;
    break_even_utilization: number | null;
    utilization: number;
    startup_cost: number;
    payback_months: number | null;
    included: string[];
    excluded: string[];
  };
  segments: { key: string; label: string; share: number; affordability_at_price: number; in_market_units: number; units_to_user: number }[];
  competitors: {
    id: string;
    name: string;
    source: string;
    modeled_units: number;
    modeled_share_of_in_market: number;
    price_used: number;
    price_status: string;
    quality_used: number;
    quality_status: string;
    distance_km: number;
  }[];
  zones: { lat: number; lng: number; weight: number; capture: number }[];
  agents: { columns: string[]; rows: [number, number, number, number][]; note: string };
  monte_carlo: {
    draws: number;
    seed: number;
    profit: Pct;
    units: Pct;
    revenue: Pct;
    prob_loss: number;
    prob_capacity_bound: number;
    histogram: { counts: number[]; edges: number[] };
    note: string;
  } | null;
  drivers: { param: string; label: string; spearman_rho: number }[];
  sensitivity: {
    tornado: { param: string; label: string; low_value: number; high_value: number; profit_at_low: number; profit_at_high: number; swing: number; status: string }[];
    price_curve: { price: number; units: number; revenue: number; profit: number }[];
    marketing_curve: { spend: number; units: number; profit: number }[];
    stress_tests: { label: string; units: number; profit: number; delta_profit: number }[];
    thresholds: { participation_break_even?: number | null };
  } | null;
  parameters: Record<string, { value: number; low: number; high: number; status: string; label: string; description: string }>;
  limitations: string[];
  duration_ms: number;
  abm?: Abm;
  evidence?: {
    snapshot_id: string;
    retrieved_at: string;
    catchment_method: string;
    population_method: string;
    population_source: string;
    coverage: Snapshot["coverage"];
    n_competitors: number;
    n_user_competitors: number;
    n_hypothetical: number;
    failed_layers?: string[];
  };
}

export interface Run {
  id: string;
  scenario_id: string;
  snapshot_id: string | null;
  status: string;
  model_version: string;
  input_hash: string;
  seed: number;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  error: string | null;
  results?: SimResult;
}

export interface Recommendation {
  action: string;
  reason: string;
  change_vs_baseline: Record<string, number>;
  main_uncertainty: string;
  verify_next: string;
  reconsider_if: string;
}

export interface Decision {
  verdict: "potentially_viable" | "financially_challenging" | "high_uncertainty" | "more_evidence_required" | "no_conclusion";
  headline: string;
  objective?: Goal;
  objective_label?: string;
  best_scenario_id?: string;
  ranking: {
    scenario_id: string;
    name: string;
    is_baseline: boolean;
    rank: number;
    units: number;
    profit: number;
    profit_p10: number | null;
    profit_p50: number | null;
    prob_loss: number | null;
    payback_months: number | null;
    break_even_units: number | null;
  }[];
  recommendations: Recommendation[];
  next_actions: { action: string; why: string; priority: string }[];
  risks: { factor: string; text: string; status: string }[];
  gaps?: { key: string; severity: string; text: string; action: string }[];
  financial_summary?: {
    scenario: string;
    revenue: number;
    operating_cost: number;
    operating_profit: number;
    profit_p10: number | null;
    profit_p90: number | null;
    prob_loss: number | null;
    break_even_units: number | null;
    utilization: number;
    startup_cost: number;
    payback_months: number | null;
    unit_label: string;
  };
  drivers?: { param: string; label: string; spearman_rho: number }[];
  method_note?: string;
  stale_scenarios?: string[];
  not_run?: string[];
  model_version?: string | null;
}

export interface CompareRow {
  scenario: Scenario;
  run_id?: string;
  unit_label?: string;
  metrics?: {
    in_market_units: number;
    modeled_demand_units: number;
    units_sold: number;
    capacity_units: number;
    price: number;
    revenue: number;
    operating_cost: number;
    operating_profit: number;
    break_even_units: number | null;
    utilization: number;
    payback_months: number | null;
    profit_p10: number | null;
    profit_p50: number | null;
    profit_p90: number | null;
    prob_loss: number | null;
  };
}

export interface GeoResult {
  name: string;
  display_name: string;
  lat: number;
  lng: number;
  type: string | null;
  class: string | null;
  bbox: number[] | null;
}

export interface Capabilities {
  ai: boolean;
  routing: boolean;
  population: string;
  places: string;
  model_version: string;
}

export interface Abm {
  n_agents: number;
  scale: number;
  days: number;
  seed: number;
  age_source: string;
  in_market_agents: number;
  monthly_units: number[];
  steady_units: number;
  peak_weekly_units: number;
  ramp_up_week: number | null;
  weekly: { week: number; units: number; aware_share: number; customers_cum: number; turned_away: number; comp_units: number }[];
  daily: { units_you: number[]; units_comp: number[]; aware_share: number[]; customers_you: number[]; turned_away: number[] };
  frames: { day: number; a: number[]; c: number[] }[];
  frame_every: number;
  businesses: { idx: number; name: string; lat: number; lng: number }[];
  agents: { columns: string[]; rows: number[][]; modes: string[]; segments: string[]; time_prefs: string[] };
  metrics: Record<string, unknown> & {
    aware_final: number;
    trial_rate: number;
    repeat_share: number;
    customers_total: number;
    mean_trip_km: number | null;
    afford_share: number;
    mean_age: number;
    female_share: number;
    wtp_p10: number;
    wtp_p50: number;
    wtp_p90: number;
    customer_modes: Record<string, number | null>;
    customer_segments: Record<string, number | null>;
    competitor_shares: number[];
  };
  monthly_finance: { month: number; units: number; capped_units: number; revenue: number; profit: number }[];
  assumptions: Record<string, number>;
  note: string;
  duration_ms: number;
  timing_ms?: { genome: number; total: number };
  genome?: {
    size: number;
    per_agent: number;
    total_parameters: number;
    by_block: Record<string, number>;
    blocks: Record<string, string>;
    audit: Record<string, number>;
    hours_source: string;
    attr_sources: Record<string, string>;
    your_hours: number[];
    month0: number;
  };
  calibration?: {
    applied: boolean;
    multiplier: number;
    method: string;
    reason?: string;
    incumbents_used?: number;
    median_incumbent_units?: number;
    survival_floor_units?: number;
    summary?: string | null;
  };
  decomposition?: Record<"chose_you" | "chose_competitor" | "chose_none", null | { n_agents: number; channels: Record<string, { you: number; best_competitor: number; edge: number }> }>;
  top_drivers_against_you?: { key: string; label: string; block: string; feat: string | null; mean_effect: number }[];
}

export interface GenomeParam {
  key: string;
  label: string;
  block: string;
  unit: string;
  origin: "evidence" | "latent" | "generated";
  mechanism: string;
  w: number;
  feat: string | null;
  loads: Record<string, number>;
  sd: number;
  transform: string;
  range: [number, number];
}

export interface GenomeRegistry {
  size: number;
  blocks: Record<string, string>;
  by_block: Record<string, number>;
  by_mechanism: Record<string, number>;
  by_origin: Record<string, number>;
  latents: { key: string; label: string }[];
  params: GenomeParam[];
  audit: Record<string, number>;
}

export interface XrayOption {
  idx: number;
  name: string;
  reachable: boolean;
  dist_km: number;
  time_min: number;
  utility: number | null;
  parts: Record<string, number>;
}

export interface AgentXray {
  agent: number;
  final_choice: number;
  outside_utility: number;
  noise_scale: number;
  options: XrayOption[];
  drivers_vs_you: { key: string; label: string; feat: string | null; value: number; z: number; effect: number }[];
  ref_option: number;
  genome: (number | null)[];
  percentile: number[];
  summary: Record<string, number>;
  segment: string;
  mode: string;
  scale: number;
  note: string;
}

export interface GenomeMatrix {
  rows: number;
  cols: number;
  data: string;
  agent_index: number[];
  groups: ("you" | "competitor" | "none" | "not_in_market")[];
  group_counts: Record<string, number>;
  blocks: { key: string; label: string; start: number; size: number }[];
  params: { key: string; label: string; block: string; mechanism: string; origin: string }[];
  separators: { key: string; label: string; block: string; delta_pct: number; you_pct: number; competitor_pct: number }[];
  n_agents: number;
  note: string;
}

export interface SurveyQuestion {
  id: string;
  section: string;
  type: "single" | "multi" | "money" | "scale5" | "text";
  text: string;
  options?: string[];
  measures: string[];
  why: string;
}

export interface SurveyKit {
  title: string;
  purpose: string;
  sample_size: { recommended: number; minimum: number; margin_of_error_at_100: string; how: string };
  reference_price: number | null;
  focus: { weakest_channels_vs_competitors: string[]; top_parameters_against_you: string[] };
  questions: SurveyQuestion[];
  note: string;
}

export interface FactorDef {
  key: string;
  label: string;
  domain: string;
  group: string;
  unit: string;
  scope: string;
  source: string;
  role: string;
  description: string;
}

export interface FactorsResponse {
  definitions: FactorDef[];
  values: { key: string; value: unknown; status: "computed" | "user" | "assumed" | "simulated" | "pending" | "unavailable" }[];
  summary: Record<string, number>;
  counts: { total: number; by_domain: Record<string, number>; by_role: Record<string, number>; by_source: Record<string, number> };
  domains: Record<string, string>;
  scenario: { id: string; name: string; run_id: string | null };
}
