"""
Unit tests for POLARIS P0 Blackout & Survival Horizon Timer
"""

import pytest
from backend.services.resilience_service import calculate_p0_survival_horizon
from backend.services.weather_service import _generate_realistic_polar_data
from backend.data.station_presets import POLAR_STATIONS


def test_p0_timer_normal_conditions():
    station = POLAR_STATIONS["bharati"]
    weather_resp = _generate_realistic_polar_data(lat=station["latitude"], lon=station["longitude"], hours=48)
    weather_series = weather_resp.get("forecast_72h", [])[:48]

    solar_series = [{"timestamp": w["timestamp"], "predicted_kw": 50.0, "lower_bound_kw": 35.0} for w in weather_series]
    load_series = [{
        "timestamp": w["timestamp"],
        "p0_load_kw": 30.0,
        "upper_bound_kw": 35.0,
        "p1_load_kw": 3.0,
        "p2_load_kw": 40.0
    } for w in weather_series]

    res = calculate_p0_survival_horizon(
        station_config=station,
        solar_forecast_series=solar_series,
        load_forecast_series=load_series,
        generator_available=True
    )

    assert res["operating_mode"] in ["NORMAL", "WARNING"]
    assert res["survival_hours_remaining"] >= 48.0
    assert res["p0_status"] == "SECURE"


def test_p0_timer_generator_failure():
    # Generator offline, high P0 demand, depleted battery -> P0 should breach within horizon
    station = POLAR_STATIONS["bharati"]
    weather_resp = _generate_realistic_polar_data(lat=station["latitude"], lon=station["longitude"], hours=48)
    weather_series = weather_resp.get("forecast_72h", [])[:48]

    # Polar night (solar = 0)
    solar_series = [{"timestamp": w["timestamp"], "predicted_kw": 0.0, "lower_bound_kw": 0.0} for w in weather_series]
    load_series = [{
        "timestamp": w["timestamp"],
        "p0_load_kw": 60.0,
        "upper_bound_kw": 70.0,
        "p1_load_kw": 3.0,
        "p2_load_kw": 30.0
    } for w in weather_series]

    res = calculate_p0_survival_horizon(
        station_config=station,
        solar_forecast_series=solar_series,
        load_forecast_series=load_series,
        current_state={"battery_soc_pct": 35.0, "fuel_remaining_l": 0.0},
        generator_available=False,
        solar_available=False
    )

    assert res["operating_mode"] == "EMERGENCY"
    assert res["survival_hours_remaining"] < 48.0
    assert res["conservative_survival_hours"] <= res["survival_hours_remaining"]
