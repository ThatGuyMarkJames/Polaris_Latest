import React, { useState, useEffect, useRef } from 'react';
import { Header } from './components/Header';
import { DashboardPage } from './pages/Dashboard';
import { SimulationPage } from './pages/Simulation';
import { ForecastPage } from './pages/Forecast';
import { ExplainabilityModal } from './components/ExplainabilityModal';
import { FinalReportModal } from './components/FinalReportModal';
import { DataSourcesFooter } from './components/DataSourcesFooter';
import { apiClient } from './api/client';
import {
  StationConfig,
  WeatherTelemetry,
  InstantEnergyState,
  DualSimulationResult,
  AgentLog,
  AgentCycleResult,
  ScenarioDefinition,
  LoadItem,
  P0SurvivalHorizon
} from './types';

// Default Bharati Station fallback configuration
const DEFAULT_STATION: StationConfig = {
  station_id: 'bharati',
  station_name: 'Bharati Research Station',
  operator: 'NCPOR / Ministry of Earth Sciences, India',
  location_name: 'Larsemann Hills, East Antarctica',
  region: 'Antarctica',
  latitude: -69.4072,
  longitude: 76.1872,
  elevation_m: 35,
  solar_capacity_kw: 180.0,
  solar_efficiency_pct: 21.5,
  panel_tilt_deg: 65.0,
  panel_azimuth_deg: 0.0,
  battery_capacity_kwh: 600.0,
  battery_soc_pct: 75.0,
  battery_min_reserve_pct: 30.0,
  battery_max_soc_pct: 98.0,
  battery_max_charge_kw: 150.0,
  battery_max_discharge_kw: 150.0,
  battery_rte_pct: 92.0,
  battery_health_pct: 98.0,
  diesel_capacity_kw: 250.0,
  diesel_fuel_l: 1200.0,
  diesel_consumption_l_per_kwh: 0.28,
  diesel_min_load_pct: 25.0,
  diesel_startup_min: 5,
  occupants: 24,
  operating_mode: 'Normal Operation',
  research_intensity: 1.0,
  heating_intensity: 1.0,
  p1_config: {
    nominal_jacket_power_kw: 3.0,
    min_battery_temp_c: -20.0,
    activation_threshold_c: -10.0,
    emergency_shutdown_threshold_c: -5.0,
    thermal_protection_mode: 'auto'
  },
  loads: [
    { id: 'heat_life', name: 'Habitat & Life Support Thermal', power_kw: 55.0, priority: 'CRITICAL', flexible: false, min_op_pct: 100 },
    { id: 'comm_nav', name: 'Satellite Uplink & Comms', power_kw: 12.0, priority: 'CRITICAL', flexible: false, min_op_pct: 100 },
    { id: 'life_support', name: 'Water Purification & Air Scrubbers', power_kw: 18.0, priority: 'CRITICAL', flexible: false, min_op_pct: 80 },
    { id: 'atmos_lab', name: 'Atmospheric & Ionospheric Labs', power_kw: 32.0, priority: 'IMPORTANT', flexible: true, min_op_pct: 50 },
    { id: 'station_light', name: 'Perimeter & Internal Lighting', power_kw: 14.0, priority: 'IMPORTANT', flexible: true, min_op_pct: 60 },
    { id: 'computing_hpc', name: 'Climate Modeling & Data Cluster', power_kw: 25.0, priority: 'DEFERRABLE', flexible: true, min_op_pct: 0 },
    { id: 'water_heating', name: 'Domestic Water Heating & Storage', power_kw: 16.0, priority: 'DEFERRABLE', flexible: true, min_op_pct: 0 },
    { id: 'ev_snowcat', name: 'Electric Snowmobile & Rover Bay', power_kw: 20.0, priority: 'DEFERRABLE', flexible: true, min_op_pct: 0 }
  ]
};

export function App() {
  // Navigation
  const [activeTab, setActiveTab] = useState<'control' | 'simulation' | 'forecast'>('control');

  // Station State
  const [station, setStation] = useState<StationConfig>(DEFAULT_STATION);
  const [presets, setPresets] = useState<StationConfig[]>([]);

  // Telemetry & Physics State
  const [weather, setWeather] = useState<WeatherTelemetry | null>(null);
  const [weatherForecast, setWeatherForecast] = useState<WeatherTelemetry[]>([]);
  const [weatherSource, setWeatherSource] = useState<string>('Open-Meteo High-Resolution API');
  const [energyState, setEnergyState] = useState<InstantEnergyState | null>(null);
  const [p0Horizon, setP0Horizon] = useState<P0SurvivalHorizon | undefined>();
  const [resilienceRisk, setResilienceRisk] = useState<any>({
    score: 35,
    level: 'MODERATE',
    color: '#f59e0b',
    breakdown: { thermal_stress: 12, wind_severity: 10, battery_margin: 6, atmospheric_instability: 7 }
  });

  // Forecasting & Optimization
  const [solarForecast, setSolarForecast] = useState<any>(null);
  const [loadForecast, setLoadForecast] = useState<any>(null);
  const [optimalSchedule, setOptimalSchedule] = useState<any[]>([]);
  const [optimalSummary, setOptimalSummary] = useState<any>(null);
  const [recommendations, setRecommendations] = useState<string[]>([
    'Forecasted solar generation covers daytime demand.',
    'Maintain standard 30% battery reserve under normal conditions.'
  ]);

  // Simulation Engine State
  const [scenarios, setScenarios] = useState<ScenarioDefinition[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>('polar_storm');
  const [simResult, setSimResult] = useState<DualSimulationResult | null>(null);
  const [currentHour, setCurrentHour] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(10);

  // Agent State
  const [agentLogs, setAgentLogs] = useState<AgentLog[]>([]);
  const [approvalStatus, setApprovalStatus] = useState<AgentCycleResult['approval_status'] | undefined>();
  const [explainability, setExplainability] = useState<AgentCycleResult['explainability'] | null>(null);

  // Modals & Demo
  const [isExplainModalOpen, setIsExplainModalOpen] = useState<boolean>(false);
  const [isReportModalOpen, setIsReportModalOpen] = useState<boolean>(false);
  const [isDemoRunning, setIsDemoRunning] = useState<boolean>(false);

  // Loading flags
  const [isLoadingWeather, setIsLoadingWeather] = useState<boolean>(false);
  const [isLoadingState, setIsLoadingState] = useState<boolean>(false);
  const [isLoadingPlan, setIsLoadingPlan] = useState<boolean>(false);
  const [isRunningSim, setIsRunningSim] = useState<boolean>(false);

  // 1. Initial Load: Presets, Scenarios, Live Weather
  useEffect(() => {
    async function initPlatform() {
      try {
        const pRes = await apiClient.getPresets();
        setPresets(pRes.stations);

        const sRes = await apiClient.getScenarios();
        setScenarios(sRes.scenarios);

        await fetchLiveWeatherData(station.latitude, station.longitude);
      } catch (err) {
        console.error('Initialization error:', err);
      }
    }
    initPlatform();
  }, []);

  // 2. Fetch Live Weather Data from Backend
  const fetchLiveWeatherData = async (lat: number, lon: number) => {
    setIsLoadingWeather(true);
    try {
      const data = await apiClient.getLiveWeather(lat, lon, 4);
      setWeather(data.current);
      setWeatherForecast(data.forecast_72h);
      setWeatherSource(data.source);

      // Re-run instant state and forecasting pipeline
      await calculateMicrogridState(data.current);
      await runForecastAndOptimization(station);
      await runSimulationScenario('polar_storm', station);
    } catch (err) {
      console.error('Weather fetch error:', err);
    } finally {
      setIsLoadingWeather(false);
    }
  };

  // 3. Instant Microgrid Physics Calculation
  const calculateMicrogridState = async (w: WeatherTelemetry | null = weather) => {
    if (!w) return;
    setIsLoadingState(true);
    try {
      const state = await apiClient.calculateInstantState(
        station,
        w.temperature_c,
        w.wind_speed_kmh,
        w.global_tilted_irradiance_wm2
      );
      setEnergyState(state);
    } catch (err) {
      console.error('State calculation error:', err);
    } finally {
      setIsLoadingState(false);
    }
  };

  // 4. Run Forecasting and Optimization Pipelines
  const runForecastAndOptimization = async (cfg: StationConfig = station) => {
    setIsLoadingPlan(true);
    try {
      const fRes = await apiClient.runForecastPipeline(cfg);
      setSolarForecast(fRes.solar_forecast);
      setLoadForecast(fRes.load_forecast);
      setResilienceRisk(fRes.resilience_risk);

      const optRes = await apiClient.solveOptimization(cfg, 24, 0.0);
      setOptimalSchedule(optRes.schedule || []);
      setOptimalSummary(optRes.summary || null);
      setRecommendations(optRes.ai_recommendations || []);
      if (optRes.p0_survival_horizon) {
        setP0Horizon(optRes.p0_survival_horizon);
      }
    } catch (err) {
      console.error('Forecast/Optimization error:', err);
    } finally {
      setIsLoadingPlan(false);
    }
  };

  // 5. Run Dual Simulation & Agent Orchestration
  const runSimulationScenario = async (scenarioId: string, cfg: StationConfig = station) => {
    setIsRunningSim(true);
    try {
      const sim = await apiClient.runSimulation(cfg, scenarioId);
      setSimResult(sim);
      setCurrentHour(0);
      if (sim.p0_survival_horizon) {
        setP0Horizon(sim.p0_survival_horizon);
      }

      const agentRes = await apiClient.orchestrateAgents(cfg, scenarioId, sim);
      setAgentLogs(agentRes.agent_logs);
      setApprovalStatus(agentRes.approval_status);
      setExplainability(agentRes.explainability);
    } catch (err) {
      console.error('Simulation execution error:', err);
    } finally {
      setIsRunningSim(false);
    }
  };

  // 6. Simulation Clock Runner Loop
  useEffect(() => {
    let timer: any = null;
    if (isPlaying && simResult) {
      const intervalMs = Math.max(20, 1000 / playbackSpeed);
      timer = setInterval(() => {
        setCurrentHour((prev) => {
          if (prev >= simResult.duration_hours - 1) {
            setIsPlaying(false);
            setIsReportModalOpen(true);
            return prev;
          }
          return prev + 1;
        });
      }, intervalMs);
    }
    return () => clearInterval(timer);
  }, [isPlaying, simResult, playbackSpeed]);

  // Handlers
  const handleSelectStationPreset = (stationId: string) => {
    const found = presets.find((p) => p.station_id === stationId);
    if (found) {
      setStation(found);
      fetchLiveWeatherData(found.latitude, found.longitude);
    }
  };

  const handleCoordinatesChange = (lat: number, lon: number) => {
    setStation((prev) => ({
      ...prev,
      latitude: lat,
      longitude: lon,
      station_id: 'custom',
      station_name: `Polar Station (${lat > 0 ? lat + '°N' : Math.abs(lat) + '°S'}, ${lon > 0 ? lon + '°E' : Math.abs(lon) + '°W'})`
    }));
  };

  const handleScenarioChange = (scenarioId: string) => {
    setSelectedScenarioId(scenarioId);
    runSimulationScenario(scenarioId, station);
  };

  // Presentation Demo Sequence
  const handleStartDemoMode = async () => {
    if (isDemoRunning) return;
    setIsDemoRunning(true);
    setActiveTab('control');

    // Step 1: Bharati Preset and Fetch Live
    handleSelectStationPreset('bharati');
    await new Promise((r) => setTimeout(r, 1200));

    // Step 2: Switch to Agentic Simulation Tab
    setActiveTab('simulation');
    await new Promise((r) => setTimeout(r, 1000));

    // Step 3: Trigger Polar Storm Scenario & Agent Cycle
    setSelectedScenarioId('polar_storm');
    await runSimulationScenario('polar_storm', station);
    await new Promise((r) => setTimeout(r, 1500));

    // Step 4: Fast-forward Playback Simulation
    setPlaybackSpeed(50);
    setIsPlaying(true);
    setIsDemoRunning(false);
  };

  // Active Timestep Data
  const currentStep = simResult?.ai_timeline[currentHour] || null;
  const currentSimWeather = simResult?.weather_timeline[currentHour] || weather;

  return (
    <div className="min-h-screen bg-polaris-950 text-slate-100 flex flex-col justify-between">
      {/* Top Header */}
      <Header
        currentStation={station}
        onSelectStationPreset={handleSelectStationPreset}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        onStartDemoMode={handleStartDemoMode}
        isDemoRunning={isDemoRunning}
        resilienceScore={resilienceRisk?.score || 45}
        resilienceLevel={resilienceRisk?.level || 'MODERATE'}
        resilienceColor={resilienceRisk?.color || '#10b981'}
      />

      {/* Main Tab Content */}
      <main className="flex-1 p-4 lg:p-8">
        {activeTab === 'control' && (
          <DashboardPage
            station={station}
            weather={weather}
            weatherSourceLabel={weatherSource}
            energyState={energyState}
            p0Horizon={p0Horizon}
            isLoadingWeather={isLoadingWeather}
            isLoadingState={isLoadingState}
            onCoordinatesChange={handleCoordinatesChange}
            onFetchLiveWeather={() => fetchLiveWeatherData(station.latitude, station.longitude)}
            onStationConfigChange={(updated) => {
              setStation(updated);
              calculateMicrogridState(weather);
            }}
            onLoadsChange={(updatedLoads: LoadItem[]) => {
              const updated = { ...station, loads: updatedLoads };
              setStation(updated);
              calculateMicrogridState(weather);
            }}
            onRecalculateState={() => {
              calculateMicrogridState(weather);
              runForecastAndOptimization(station);
            }}
            optimalSchedule={optimalSchedule}
            optimalSummary={optimalSummary}
            recommendations={recommendations}
            onGeneratePlan={() => runForecastAndOptimization(station)}
            isLoadingPlan={isLoadingPlan}
          />
        )}

        {activeTab === 'simulation' && (
          <SimulationPage
            currentStep={currentStep}
            currentHour={currentHour}
            maxHours={simResult?.duration_hours || 48}
            weather={currentSimWeather}
            isPlaying={isPlaying}
            onPlayPause={() => setIsPlaying(!isPlaying)}
            onReset={() => {
              setIsPlaying(false);
              setCurrentHour(0);
            }}
            onStep={() => setCurrentHour((prev) => Math.min((simResult?.duration_hours || 48) - 1, prev + 1))}
            playbackSpeed={playbackSpeed}
            onSpeedChange={setPlaybackSpeed}
            onScrubHour={setCurrentHour}
            scenarios={scenarios}
            selectedScenarioId={selectedScenarioId}
            onSelectScenario={handleScenarioChange}
            isRunningSim={isRunningSim}
            simResult={simResult}
            agentLogs={agentLogs}
            approvalStatus={approvalStatus}
            onOpenExplainability={() => setIsExplainModalOpen(true)}
            onOpenReport={() => setIsReportModalOpen(true)}
            stationName={station.station_name}
          />
        )}

        {activeTab === 'forecast' && (
          <ForecastPage
            solarForecast={solarForecast}
            loadForecast={loadForecast}
            weatherForecast={weatherForecast}
            resilienceRisk={resilienceRisk}
            onRefreshForecast={() => runForecastAndOptimization(station)}
            isLoading={isLoadingPlan}
          />
        )}
      </main>

      {/* Decision Explainability Modal */}
      <ExplainabilityModal
        isOpen={isExplainModalOpen}
        onClose={() => setIsExplainModalOpen(false)}
        explainability={explainability}
      />

      {/* Comprehensive End-of-Simulation Report Modal */}
      <FinalReportModal
        isOpen={isReportModalOpen}
        onClose={() => setIsReportModalOpen(false)}
        simResult={simResult}
        stationName={station.station_name}
      />

      {/* Data Lineage Footer */}
      <DataSourcesFooter />
    </div>
  );
}
