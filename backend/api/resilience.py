"""
POLARIS Resilience & P0 Critical Survival Horizon API Router
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional

from backend.services.weather_service import fetch_open_meteo_weather
from backend.forecasting.solar_forecast import predict_solar_generation
from backend.forecasting.load_forecast import get_ml_load_forecast
from backend.services.resilience_service import calculate_p0_survival_horizon
from backend.data.station_presets import POLAR_STATIONS
from backend.database.db import get_latest_telemetry

router = APIRouter(prefix="/api/resilience", tags=["resilience"])


@router.get("/p0-horizon/{station_id}")
async def get_p0_survival_horizon(station_id: str):
    """
    Computes real-time P0 critical survival horizon and conservative bounds.
    """
    st_id = station_id.lower()
    preset = POLAR_STATIONS.get(st_id, POLAR_STATIONS["bharati"])
    
    # 1. Fetch live Open-Meteo weather
    weather_resp = await fetch_open_meteo_weather(lat=preset["latitude"], lon=preset["longitude"], forecast_days=4, station_id=st_id)
    weather_series = weather_resp.get("forecast_72h", [])

    # 2. Get hybrid forecasts
    solar_res = predict_solar_generation(
        solar_capacity_kw=preset["default_solar_kw"],
        efficiency_pct=preset["default_solar_efficiency_pct"],
        weather_forecast=weather_series
    )
    load_res = get_ml_load_forecast(
        weather_forecast_series=weather_series,
        loads=preset["loads"],
        occupants=preset.get("default_occupants", 24),
        operating_mode=preset.get("default_mode", "Normal Operation"),
        p1_config=preset.get("default_p1_config")
    )

    # 3. Get latest sensor state
    latest_db = get_latest_telemetry(st_id)
    energy_curr = latest_db.get("energy", {})

    # 4. Calculate P0 survival timer
    horizon_result = calculate_p0_survival_horizon(
        station_config={
            "battery_capacity_kwh": preset["default_battery_kwh"],
            "battery_soc_pct": energy_curr.get("battery_soc_pct", preset["default_battery_soc_pct"]),
            "battery_min_reserve_pct": preset["default_battery_min_reserve_pct"],
            "battery_max_discharge_kw": preset["default_battery_max_discharge_kw"],
            "diesel_capacity_kw": preset["default_diesel_kw"],
            "diesel_fuel_l": energy_curr.get("fuel_remaining_l", preset["default_diesel_fuel_l"]),
            "diesel_consumption_l_per_kwh": preset["default_diesel_consumption_l_per_kwh"]
        },
        solar_forecast_series=solar_res.get("forecast_series", []),
        load_forecast_series=load_res.get("forecast_series", []),
        current_state=energy_curr
    )

    return {
        "status": "success",
        "station_id": st_id,
        "station_name": preset["name"],
        "p0_horizon": horizon_result
    }
