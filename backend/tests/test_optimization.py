"""
Unit tests for POLARIS MILP Optimizer and Emergency Mode
"""

import pytest
from backend.optimization.energy_optimizer import optimize_energy_schedule
from backend.services.weather_service import _generate_realistic_polar_data
from backend.data.station_presets import POLAR_STATIONS


def test_optimizer_prioritizes_p0_protection():
    station = POLAR_STATIONS["bharati"]
    weather_resp = _generate_realistic_polar_data(lat=station["latitude"], lon=station["longitude"], hours=24)
    weather_series = weather_resp.get("forecast_72h", [])[:24]

    solar_series = [{"timestamp": w["timestamp"], "predicted_kw": 50.0} for w in weather_series]
    load_series = [{
        "timestamp": w["timestamp"],
        "p0_load_kw": 40.0,
        "p1_load_kw": 3.0,
        "p2_load_kw": 60.0,
        "predicted_demand_kw": 103.0,
        "thermal_load_kw": 20.0
    } for w in weather_series]

    # Run optimization with generator active
    opt_res = optimize_energy_schedule(
        station_config=station,
        solar_forecast_series=solar_series,
        load_forecast_series=load_series,
        planning_horizon_hours=24,
        weather_forecast_series=weather_series
    )

    assert opt_res["success"] is True
    assert opt_res["status"] == "OPTIMAL"
    assert opt_res["summary"]["critical_p0_coverage_pct"] == 100.0


def test_optimizer_sheds_p2_before_p1_in_emergency():
    # Force generator offline and low solar -> microgrid is power-constrained
    station = POLAR_STATIONS["bharati"]
    weather_resp = _generate_realistic_polar_data(lat=station["latitude"], lon=station["longitude"], hours=12)
    weather_series = weather_resp.get("forecast_72h", [])[:12]

    solar_series = [{"timestamp": w["timestamp"], "predicted_kw": 10.0} for w in weather_series]
    load_series = [{
        "timestamp": w["timestamp"],
        "p0_load_kw": 35.0,
        "p1_load_kw": 3.0,
        "p2_load_kw": 50.0,
        "predicted_demand_kw": 88.0,
        "thermal_load_kw": 15.0
    } for w in weather_series]

    opt_res = optimize_energy_schedule(
        station_config=station,
        solar_forecast_series=solar_series,
        load_forecast_series=load_series,
        planning_horizon_hours=12,
        forced_generator_offline=True,
        weather_forecast_series=weather_series
    )

    assert opt_res["success"] is True
    # In power deficit, P2 curtailment should be positive while P0 remains prioritized
    assert opt_res["summary"]["total_p2_curtailed_kwh"] > 0.0
    assert opt_res["summary"]["critical_p0_coverage_pct"] >= 85.0
