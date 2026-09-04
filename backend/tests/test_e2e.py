"""
End-to-end integration tests for POLARIS pipeline:
Open-Meteo -> Telemetry -> Feature Engineering -> Hybrid Forecast -> Optimizer -> P0 Timer -> Digital Twin
"""

import pytest
from backend.services.weather_service import fetch_open_meteo_weather
from backend.forecasting.solar_forecast import predict_solar_generation
from backend.forecasting.load_forecast import get_ml_load_forecast
from backend.optimization.energy_optimizer import optimize_energy_schedule
from backend.services.resilience_service import calculate_p0_survival_horizon
from backend.simulation.engine import run_dual_simulation
from backend.data.station_presets import POLAR_STATIONS


@pytest.mark.asyncio
async def test_full_pipeline_e2e():
    station = POLAR_STATIONS["bharati"]
    
    # 1. Pipeline A: Fetch weather
    weather_resp = await fetch_open_meteo_weather(lat=station["latitude"], lon=station["longitude"], forecast_days=2, station_id="bharati")
    forecast_series = weather_resp.get("forecast_72h", [])
    assert len(forecast_series) > 0

    # 2. Hybrid Predictions
    solar_res = predict_solar_generation(station["default_solar_kw"], station["default_solar_efficiency_pct"], forecast_series)
    load_res = get_ml_load_forecast(forecast_series, loads=station["loads"])
    assert "forecast_series" in solar_res
    assert "forecast_series" in load_res

    # 3. MILP Optimization
    opt_res = optimize_energy_schedule(
        station_config=station,
        solar_forecast_series=solar_res["forecast_series"],
        load_forecast_series=load_res["forecast_series"],
        planning_horizon_hours=24,
        weather_forecast_series=forecast_series
    )
    assert opt_res["success"] is True
    assert len(opt_res["schedule"]) == 24

    # 4. Resilience & P0 Timer
    p0_timer = calculate_p0_survival_horizon(
        station_config=station,
        solar_forecast_series=solar_res["forecast_series"],
        load_forecast_series=load_res["forecast_series"]
    )
    assert "survival_hours_remaining" in p0_timer
    assert p0_timer["operating_mode"] in ["NORMAL", "WARNING", "EMERGENCY"]

    # 5. Dual Simulation
    sim_res = run_dual_simulation(station, forecast_series, scenario_id="polar_storm")
    assert "metrics_comparison" in sim_res
    assert "ai_timeline" in sim_res
    assert "baseline_timeline" in sim_res
