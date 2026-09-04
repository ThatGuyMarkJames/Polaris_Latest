"""
AI Hybrid Forecasting API
Provides ML-powered multi-horizon forecasts for demand and solar generation with uncertainty intervals.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from backend.forecasting.solar_forecast import predict_solar_generation
from backend.forecasting.load_forecast import get_ml_load_forecast
from backend.services.weather_service import fetch_open_meteo_weather
from backend.services.observability import log_forecast_and_decision
from backend.data.station_presets import POLAR_STATIONS

router = APIRouter(prefix="/api/forecast", tags=["forecast"])


class ForecastRequest(BaseModel):
    station_id: Optional[str] = "bharati"
    latitude: float = -69.4072
    longitude: float = 76.1872
    solar_capacity_kw: float = 180.0
    solar_efficiency_pct: float = 21.5
    battery_capacity_kwh: float = 600.0
    battery_soc_pct: float = 75.0
    occupants: int = 24
    operating_mode: str = "Normal Operation"
    research_intensity: float = 1.0
    heating_intensity: float = 1.0
    p1_config: Optional[Dict[str, Any]] = None
    loads: Optional[List[Dict[str, Any]]] = None


@router.post("/run")
async def run_forecasting_pipeline(req: ForecastRequest):
    """
    Executes parallel AI load and solar hybrid forecasts using live atmospheric data.
    """
    st_id = (req.station_id or "bharati").lower()
    weather_data = await fetch_open_meteo_weather(lat=req.latitude, lon=req.longitude, forecast_days=4, station_id=st_id)
    forecast_72h = weather_data.get("forecast_72h", [])

    loads_list = req.loads if req.loads else POLAR_STATIONS.get(st_id, POLAR_STATIONS["bharati"])["loads"]
    p1_cfg = req.p1_config or POLAR_STATIONS.get(st_id, POLAR_STATIONS["bharati"]).get("default_p1_config")

    # 1. AI Hybrid Solar Forecast
    solar_res = predict_solar_generation(
        solar_capacity_kw=req.solar_capacity_kw,
        efficiency_pct=req.solar_efficiency_pct,
        weather_forecast=forecast_72h
    )

    # 2. Surrogate Hybrid Load Forecast (P0, P1, P2)
    load_res = get_ml_load_forecast(
        weather_forecast_series=forecast_72h,
        loads=loads_list,
        occupants=req.occupants,
        operating_mode=req.operating_mode,
        p1_config=p1_cfg
    )

    # 3. Calculate Multi-Factor Resilience Risk Score
    curr = weather_data.get("current", {})
    temp = curr.get("temperature_c", -18.0)
    wind = curr.get("wind_speed_kmh", 35.0)
    snow = curr.get("snowfall_cm", 0.0)
    storm_prob = curr.get("storm_probability_pct", 50)
    soc = req.battery_soc_pct

    temp_risk = max(0.0, min(30.0, (-temp - 10.0) * 0.8))
    wind_risk = min(25.0, (wind / 80.0) * 25.0)
    batt_risk = max(0.0, (50.0 - soc) * 0.5)
    storm_risk = (storm_prob / 100.0) * 25.0

    total_risk_score = min(100, int(temp_risk + wind_risk + batt_risk + storm_risk))
    if total_risk_score < 30:
        risk_level = "LOW"
        risk_color = "#10b981"
    elif total_risk_score < 60:
        risk_level = "MODERATE"
        risk_color = "#f59e0b"
    elif total_risk_score < 85:
        risk_level = "HIGH"
        risk_color = "#f97316"
    else:
        risk_level = "CRITICAL"
        risk_color = "#ef4444"

    # 4. Observability Audit Log
    log_forecast_and_decision(
        station_id=st_id,
        model_version="2.6.0-hybrid",
        horizon_hours=72,
        prediction_type="hybrid",
        predictions={"solar": solar_res.get("horizon_predictions"), "load": load_res.get("horizon_predictions")},
        uncertainty={"solar_metrics": solar_res.get("metrics"), "load_metrics": load_res.get("metrics")}
    )

    return {
        "weather_summary": {
            "source": weather_data.get("source"),
            "temperature_c": temp,
            "apparent_temp_c": curr.get("apparent_temperature_c", temp),
            "wind_speed_kmh": wind,
            "snowfall_cm": snow,
            "cloud_cover_pct": curr.get("cloud_cover_pct", 50),
            "storm_probability_pct": storm_prob
        },
        "solar_forecast": solar_res,
        "load_forecast": load_res,
        "resilience_risk": {
            "score": total_risk_score,
            "level": risk_level,
            "color": risk_color,
            "breakdown": {
                "thermal_stress": round(temp_risk, 1),
                "wind_severity": round(wind_risk, 1),
                "battery_margin": round(batt_risk, 1),
                "atmospheric_instability": round(storm_risk, 1)
            }
        }
    }


@router.get("/hybrid/{station_id}")
async def get_hybrid_forecast_endpoint(station_id: str):
    """
    Dedicated endpoint returning hybrid physics + XGBoost forecast for a given station preset.
    """
    st_id = station_id.lower()
    preset = POLAR_STATIONS.get(st_id, POLAR_STATIONS["bharati"])
    req = ForecastRequest(
        station_id=st_id,
        latitude=preset["latitude"],
        longitude=preset["longitude"],
        solar_capacity_kw=preset["default_solar_kw"],
        solar_efficiency_pct=preset["default_solar_efficiency_pct"],
        battery_capacity_kwh=preset["default_battery_kwh"],
        battery_soc_pct=preset["default_battery_soc_pct"],
        occupants=preset.get("default_occupants", 24),
        operating_mode=preset.get("default_mode", "Normal Operation"),
        p1_config=preset.get("default_p1_config"),
        loads=preset["loads"]
    )
    return await run_forecasting_pipeline(req)
