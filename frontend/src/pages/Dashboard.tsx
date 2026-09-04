import React from 'react';
import { StationMap } from '../components/StationMap';
import { WeatherPanel } from '../components/WeatherPanel';
import { CurrentEnergyCard } from '../components/CurrentEnergyCard';
import { EnergyFlow } from '../components/EnergyFlow';
import { StationConfigComponent } from '../components/StationConfig';
import { LoadManagement } from '../components/LoadManagement';
import { OptimizationTimeline } from '../components/OptimizationTimeline';
import { P0SurvivalTimer } from '../components/P0SurvivalTimer';
import { EmergencyPanel } from '../components/EmergencyPanel';
import {
  StationConfig,
  WeatherTelemetry,
  InstantEnergyState,
  LoadItem,
  P0SurvivalHorizon
} from '../types';

interface DashboardPageProps {
  station: StationConfig;
  weather: WeatherTelemetry | null;
  weatherSourceLabel?: string;
  energyState: InstantEnergyState | null;
  p0Horizon?: P0SurvivalHorizon;
  isLoadingWeather: boolean;
  isLoadingState: boolean;
  onCoordinatesChange: (lat: number, lon: number) => void;
  onFetchLiveWeather: () => void;
  onStationConfigChange: (updated: StationConfig) => void;
  onLoadsChange: (updatedLoads: LoadItem[]) => void;
  onRecalculateState: () => void;
  optimalSchedule: any[];
  optimalSummary: any;
  recommendations: string[];
  onGeneratePlan: () => void;
  isLoadingPlan: boolean;
}

export const DashboardPage: React.FC<DashboardPageProps> = ({
  station,
  weather,
  weatherSourceLabel,
  energyState,
  p0Horizon,
  isLoadingWeather,
  isLoadingState,
  onCoordinatesChange,
  onFetchLiveWeather,
  onStationConfigChange,
  onLoadsChange,
  onRecalculateState,
  optimalSchedule,
  optimalSummary,
  recommendations,
  onGeneratePlan,
  isLoadingPlan
}) => {
  return (
    <div className="flex flex-col gap-6 max-w-7xl mx-auto pb-12">
      {/* 0. Emergency Banner (Activated during Warnings & Emergencies) */}
      <EmergencyPanel
        horizon={p0Horizon}
        energyState={energyState || undefined}
        sourceLabel={weatherSourceLabel || 'Synthetic telemetry — simulation mode'}
      />

      {/* 1. Top Section: Station Coordinates & Live Atmospheric Weather */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-6">
          <StationMap
            latitude={station.latitude}
            longitude={station.longitude}
            onCoordinatesChange={onCoordinatesChange}
            onFetchLiveWeather={onFetchLiveWeather}
            isLoadingWeather={isLoadingWeather}
            stationName={station.station_name}
            region={station.region}
            sourceLabel={weatherSourceLabel}
          />
        </div>
        <div className="lg:col-span-6">
          <WeatherPanel weather={weather} isLoading={isLoadingWeather} />
        </div>
      </div>

      {/* 2. P0 Critical Life Support Survival Timer */}
      <P0SurvivalTimer horizon={p0Horizon} />

      {/* 3. Microgrid Telemetry KPIs */}
      <CurrentEnergyCard state={energyState} isLoading={isLoadingState} />

      {/* 4. Active Energy Flow Diagram */}
      <EnergyFlow state={energyState} />

      {/* 5. Optimal 24-Hour Schedule & AI Recommendations */}
      <OptimizationTimeline
        schedule={optimalSchedule}
        summary={optimalSummary}
        recommendations={recommendations}
        onGeneratePlan={onGeneratePlan}
        isLoading={isLoadingPlan}
      />

      {/* 6. Station Equipment Configuration */}
      <StationConfigComponent
        config={station}
        onChange={onStationConfigChange}
        onRecalculate={onRecalculateState}
      />

      {/* 7. Dynamic Subsystem Load Priorities */}
      <LoadManagement
        loads={station.loads}
        onChange={onLoadsChange}
        totalDemand={energyState?.current_demand_kw || 120}
      />
    </div>
  );
};
