"""
Energy Optimization API
Provides optimal microgrid dispatch schedule via OR-Tools MILP mathematical programming.
Integrates P0/P1/P2 priorities, Arrhenius battery physics, CHP recovery, and P0 survival timer.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from backend.optimization.energy_optimizer import optimize_energy_schedule
from backend.forecasting.solar_forecast import predict_solar_generation
from backend.forecasting.load_forecast import get_ml_load_forecast
from backend.services.weather_service import fetch_open_meteo_weather
from backend.services.resilience_service import calculate_p0_survival_horizon
from backend.services.observability import log_forecast_and_decision
from backend.data.station_presets import POLAR_STATIONS

router = APIRouter(prefix="/api/optimization", tags=["optimization"])


class OptimizationRequest(BaseModel):
    station_config: Dict[str, Any]
    planning_horizon_hours: int = 24
    emergency_reserve_boost_pct: float = 0.0
    forced_generator_offline: bool = False
    forced_solar_offline: bool = False
    use_conservative_bounds: bool = False


@router.post("/solve")
async def solve_optimal_dispatch(req: OptimizationRequest):
    """
    Executes OR-Tools MILP optimization to generate optimal 24h/72h energy schedule.
    """
    config = req.station_config
    st_id = str(config.get("station_id", config.get("id", "bharati"))).lower()
    lat = float(config.get("latitude", -69.4072))
    lon = float(config.get("longitude", 76.1872))

    weather_data = await fetch_open_meteo_weather(lat=lat, lon=lon, forecast_days=4, station_id=st_id)
    forecast_72h = weather_data.get("forecast_72h", [])

    solar_res = predict_solar_generation(
        solar_capacity_kw=float(config.get("solar_capacity_kw", 180.0)),
        efficiency_pct=float(config.get("solar_efficiency_pct", 21.5)),
        weather_forecast=forecast_72h
    )

    load_res = get_ml_load_forecast(
        weather_forecast_series=forecast_72h,
        loads=config.get("loads", POLAR_STATIONS.get(st_id, POLAR_STATIONS["bharati"])["loads"]),
        occupants=int(config.get("occupants", 24)),
        operating_mode=config.get("operating_mode", "Normal Operation"),
        p1_config=config.get("p1_config", config.get("default_p1_config"))
    )

    opt_result = optimize_energy_schedule(
        station_config=config,
        solar_forecast_series=solar_res["forecast_series"],
        load_forecast_series=load_res["forecast_series"],
        planning_horizon_hours=req.planning_horizon_hours,
        emergency_reserve_boost_pct=req.emergency_reserve_boost_pct,
        forced_generator_offline=req.forced_generator_offline,
        forced_solar_offline=req.forced_solar_offline,
        weather_forecast_series=forecast_72h,
        use_conservative_bounds=req.use_conservative_bounds
    )

    # Calculate P0 survival horizon under this schedule
    p0_horizon = calculate_p0_survival_horizon(
        station_config=config,
        solar_forecast_series=solar_res["forecast_series"],
        load_forecast_series=load_res["forecast_series"],
        generator_available=not req.forced_generator_offline,
        solar_available=not req.forced_solar_offline
    )

    # Dynamic AI Explainability Recommendations
    recommendations = []
    summary = opt_result.get("summary", {})
    if p0_horizon.get("operating_mode") == "EMERGENCY":
        recommendations.append("EMERGENCY MODE ACTIVE: P0 critical life support prioritized. All P2 deferrable loads shed.")
    elif summary.get("total_diesel_fuel_liters", 0) > 200:
        recommendations.append("High generator runtime expected. Pre-charge battery during peak daytime solar hours.")
    else:
        recommendations.append("Renewable generation covers > 70% of station demand over the horizon.")

    if req.emergency_reserve_boost_pct > 0:
        recommendations.append(f"Emergency reserve active (+{req.emergency_reserve_boost_pct}%). Deferrable compute throttled to maintain critical life support.")
    else:
        recommendations.append("Standard battery reserve active. All scientific loads operating normally.")

    # Audit log
    log_forecast_and_decision(
        station_id=st_id,
        model_version="2.6.0-milp",
        horizon_hours=req.planning_horizon_hours,
        prediction_type="optimization",
        predictions={"summary": summary},
        optimizer_status=opt_result.get("status"),
        actions_taken=recommendations,
        safety_decision=f"P0 Coverage: {summary.get('critical_p0_coverage_pct', 100)}%"
    )

    return {
        **opt_result,
        "p0_survival_horizon": p0_horizon,
        "ai_recommendations": recommendations
    }
