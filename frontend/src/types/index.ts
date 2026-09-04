export interface LoadItem {
  id: string;
  name: string;
  power_kw: number;
  priority: 'CRITICAL' | 'IMPORTANT' | 'DEFERRABLE';
  flexible: boolean;
  min_op_pct: number;
  current_kw?: number;
  nominal_kw?: number;
}

export interface P1Config {
  nominal_jacket_power_kw: number;
  min_battery_temp_c: number;
  activation_threshold_c: number;
  emergency_shutdown_threshold_c: number;
  thermal_protection_mode: string;
}

export interface StationConfig {
  station_id?: string;
  station_name: string;
  operator?: string;
  location_name?: string;
  region?: string;
  latitude: number;
  longitude: number;
  elevation_m: number;
  solar_capacity_kw: number;
  solar_efficiency_pct: number;
  panel_tilt_deg: number;
  panel_azimuth_deg: number;
  battery_capacity_kwh: number;
  battery_soc_pct: number;
  battery_min_reserve_pct: number;
  battery_max_soc_pct: number;
  battery_max_charge_kw: number;
  battery_max_discharge_kw: number;
  battery_rte_pct: number;
  battery_health_pct: number;
  diesel_capacity_kw: number;
  diesel_fuel_l: number;
  diesel_consumption_l_per_kwh: number;
  diesel_min_load_pct: number;
  diesel_startup_min: number;
  occupants: number;
  operating_mode: string;
  research_intensity: number;
  heating_intensity: number;
  p1_config?: P1Config;
  loads: LoadItem[];
}

export interface WeatherTelemetry {
  timestamp: string;
  temperature_c: number;
  apparent_temperature_c: number;
  wind_speed_kmh: number;
  wind_gusts_kmh: number;
  wind_direction_deg: number;
  cloud_cover_pct: number;
  precipitation_mm: number;
  snowfall_cm: number;
  solar_irradiance_wm2: number;
  direct_normal_irradiance_wm2: number;
  global_tilted_irradiance_wm2: number;
  diffuse_radiation_wm2: number;
  sunshine_duration_s: number;
  is_day: boolean;
  is_storm: boolean;
  storm_probability_pct: number;
}

export interface WeatherDataResponse {
  latitude: number;
  longitude: number;
  source: string;
  cached: boolean;
  fetched_at: string;
  current: WeatherTelemetry;
  forecast_72h: WeatherTelemetry[];
}

export interface P0SurvivalHorizon {
  operating_mode: 'NORMAL' | 'WARNING' | 'EMERGENCY';
  operating_mode_color: string;
  survival_hours_remaining: number;
  conservative_survival_hours: number;
  estimated_breach_time: string;
  conservative_breach_time: string;
  confidence_interval_hours: [number, number];
  current_p0_load_kw: number;
  expected_minimum_soc_pct: number;
  conservative_minimum_soc_pct: number;
  generator_contribution_kwh: number;
  fuel_remaining_liters: number;
  p1_shed_status: 'ACTIVE' | 'SHED';
  p2_shed_status: 'ACTIVE' | 'CURTAILED';
  p0_status: 'SECURE' | 'AT_RISK' | 'BREACHED';
  explainability: string[];
  recommended_actions: string[];
}

export interface InstantEnergyState {
  current_demand_kw: number;
  p0_load_kw?: number;
  p1_load_kw?: number;
  p2_load_kw?: number;
  critical_load_kw: number;
  important_load_kw: number;
  deferrable_load_kw: number;
  solar_generation_kw: number;
  solar_direct_kw: number;
  solar_to_battery_kw: number;
  battery_soc_pct: number;
  battery_temperature_c?: number;
  battery_available_energy_kwh: number;
  battery_discharging_kw: number;
  battery_charging_kw: number;
  diesel_fuel_liters: number;
  generator_output_kw: number;
  generator_state: string;
  critical_load_coverage_pct: number;
  renewable_contribution_pct: number;
  evaluated_loads: LoadItem[];
}

export interface ScenarioDefinition {
  id: string;
  name: string;
  description: string;
  solar_multiplier: number;
  demand_multiplier: number;
  temp_offset_c: number;
  wind_multiplier: number;
  generator_available: boolean;
  solar_available: boolean;
  initial_ice_pct: number;
  humidity_factor_override?: number;
  duration_hours: number;
  severity: 'LOW' | 'MODERATE' | 'HIGH' | 'CRITICAL' | 'EMERGENCY';
  color: string;
}

export interface SimulationTimestep {
  hour: number;
  demand_kw: number;
  p0_load_kw?: number;
  p1_load_kw?: number;
  p2_load_kw?: number;
  p1_jacket_active?: boolean;
  critical_load_kw?: number;
  solar_kw: number;
  solar_direct_kw: number;
  solar_charge_kw?: number;
  solar_to_battery_kw?: number;
  battery_discharge_kw: number;
  battery_soc_pct: number;
  battery_energy_kwh?: number;
  generator_kw: number;
  generator_active: boolean;
  curtailed_kw: number;
  p2_curtailed_kw?: number;
  p0_unserved_kw?: number;
  fuel_remaining_l: number;
  fuel_consumed_l?: number;
  load_served_kw?: number;
  ice_coverage_pct: number;
  chp_heat_kw: number;
  chp_heat_displacing_kw: number;
  battery_heater_kw: number;
  battery_heater_active: boolean;
  eta_rte_pct: number;
  thermal_load_kw: number;
}

export interface DualSimulationResult {
  scenario: ScenarioDefinition;
  duration_hours: number;
  p0_survival_horizon?: P0SurvivalHorizon;
  metrics_comparison: {
    diesel_consumed_liters: { baseline: number; ai: number; unit: string };
    fuel_saved_liters: { value: number; percentage: number; unit: string };
    minimum_battery_soc: { baseline: number; ai: number; unit: string };
    critical_load_coverage: { baseline: number; ai: number; unit: string };
    renewable_utilization: { baseline: number; ai: number; unit: string };
    p0_survival_hours?: { baseline: number; ai: number; unit: string };
    p1_shutdown_duration?: { value: number; unit: string };
    p2_curtailed_energy?: { value: number; unit: string };
    resilience_risk_score: { baseline: number; ai: number; unit: string };
    agent_interventions_count: number;
    plan_revisions_count: number;
  };
  baseline_timeline: SimulationTimestep[];
  ai_timeline: SimulationTimestep[];
  weather_timeline: WeatherTelemetry[];
  ice_trajectory?: number[];
  baseline_ice_trajectory?: number[];
  mechanical_clearing_hours?: number[];
}

export interface AgentLog {
  timestamp: string;
  agent: string;
  type: 'alert' | 'forecast' | 'plan' | 'reject' | 'replan' | 'approve' | 'execute';
  icon: string;
  message: string;
  details?: string;
}

export interface AgentCycleResult {
  status: string;
  scenario: string;
  agent_logs: AgentLog[];
  explainability: {
    title: string;
    summary: string;
    key_factors: { factor: string; value: string; impact: string }[];
    actions_taken: string[];
  };
  approval_status: {
    forecast_agent: string;
    energy_manager: string;
    safety_agent: string;
    reserve_margin_pct: number;
  };
}
