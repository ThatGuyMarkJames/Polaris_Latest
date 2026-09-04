"""
Unit tests for POLARIS Feature Engineering, Hybrid ML Models, and Uncertainty
"""

import pytest
import numpy as np
import pandas as pd
from backend.ml.features import extract_features_from_dataframe, get_feature_column_names, calculate_solar_elevation
from backend.ml.models import HybridSolarForecaster, HybridLoadForecaster
from backend.forecasting.solar_forecast import predict_solar_generation
from backend.forecasting.load_forecast import get_ml_load_forecast
from backend.services.weather_service import _generate_realistic_polar_data
from backend.data.station_presets import POLAR_STATIONS


def test_feature_engineering_anti_leakage():
    # Verify that lag features at row t do not use future values at t+1
    timestamps = pd.date_range("2026-01-01", periods=10, freq="1h", tz="UTC")
    df = pd.DataFrame({
        "timestamp": timestamps.astype(str),
        "pv_power_kw": [0, 10, 20, 30, 40, 50, 60, 70, 80, 90],
        "temperature": [-15] * 10,
        "wind": [20] * 10,
        "cloud": [30] * 10,
        "irradiance": [100] * 10,
        "snowfall": [0] * 10
    })
    feat_df = extract_features_from_dataframe(df)
    
    # pv_lag_1h at index 3 (value 30) should be 20 (index 2), NOT 40 (index 4)
    assert feat_df.loc[3, "pv_lag_1h"] == 20
    assert feat_df.loc[4, "pv_lag_2h"] == 20


def test_hybrid_solar_forecaster_shape_and_bounds():
    weather_resp = _generate_realistic_polar_data(lat=-69.4072, lon=76.1872, hours=24)
    weather_series = weather_resp.get("forecast_72h", [])[:24]

    res = predict_solar_generation(
        solar_capacity_kw=180.0,
        efficiency_pct=21.5,
        weather_forecast=weather_series
    )
    
    series = res["forecast_series"]
    assert len(series) == 24
    for item in series:
        assert item["lower_bound_kw"] <= item["predicted_kw"] + 1e-3
        assert item["upper_bound_kw"] >= item["predicted_kw"] - 1e-3
        assert item["lower_bound_kw"] >= 0.0


def test_hybrid_load_forecaster_p0_p1_p2_breakdown():
    weather_resp = _generate_realistic_polar_data(lat=-69.4072, lon=76.1872, hours=24)
    weather_series = weather_resp.get("forecast_72h", [])[:24]

    res = get_ml_load_forecast(weather_series, loads=POLAR_STATIONS["bharati"]["loads"])
    series = res["forecast_series"]
    assert len(series) == 24
    for item in series:
        assert item["p0_load_kw"] > 0
        assert item["p1_load_kw"] >= 0
        assert item["p2_load_kw"] >= 0
        assert item["predicted_demand_kw"] >= item["p0_load_kw"]
