"""
POLARIS Dual Telemetry API Router
Provides endpoints for querying live/historical telemetry, fused state vectors, and simulating synthetic feeds.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from backend.database.db import get_latest_telemetry, query_telemetry_history
from backend.services.synthetic_telemetry_engine import SyntheticSensorEngine
from backend.services.weather_service import fetch_open_meteo_weather
from backend.services.data_fusion import fuse_telemetry_streams
from backend.data.station_presets import POLAR_STATIONS

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])


class SimulateTelemetryRequest(BaseModel):
    station_id: str = "bharati"
    scenario_id: str = "normal"
    hours: int = 24
    imperfection_config: Optional[Dict[str, Any]] = None


@router.get("/current/{station_id}")
async def get_current_telemetry(station_id: str):
    """
    Returns the latest fused environmental + sensor telemetry state for a station.
    """
    st_id = station_id.lower()
    preset = POLAR_STATIONS.get(st_id, POLAR_STATIONS["bharati"])
    
    # 1. Fetch live Open-Meteo weather
    weather_resp = await fetch_open_meteo_weather(lat=preset["latitude"], lon=preset["longitude"], forecast_days=1, station_id=st_id)
    curr_weather = weather_resp.get("current", {})
    
    # 2. Query or generate latest sensor telemetry
    db_state = get_latest_telemetry(st_id)
    energy_state = db_state.get("energy")
    
    if not energy_state:
        # Generate on the fly using synthetic engine
        engine = SyntheticSensorEngine(st_id, preset)
        energy_state = engine.generate_step(curr_weather, persist=True)

    # 3. Fuse streams
    fused = fuse_telemetry_streams(curr_weather, energy_state, st_id)
    return {
        "status": "success",
        "station_id": st_id,
        "station_name": preset["name"],
        "fused_state": fused,
        "source_label": f"Pipeline A: {fused.get('environmental_source')} | Pipeline B: {fused.get('source_type').upper()}"
    }


@router.get("/history/{station_id}")
async def get_telemetry_history(
    station_id: str,
    limit: int = Query(default=48, ge=1, le=500)
):
    """
    Returns historical telemetry records from SQLite database.
    """
    history = query_telemetry_history(station_id.lower(), limit=limit)
    return {
        "status": "success",
        "station_id": station_id,
        "count": len(history),
        "history": history
    }


@router.post("/simulate")
async def simulate_sensor_telemetry(req: SimulateTelemetryRequest):
    """
    Generates multi-hour synthetic telemetry trajectory for digital twin scenarios.
    """
    st_id = req.station_id.lower()
    preset = POLAR_STATIONS.get(st_id, POLAR_STATIONS["bharati"])
    
    weather_resp = await fetch_open_meteo_weather(lat=preset["latitude"], lon=preset["longitude"], forecast_days=max(1, req.hours // 24 + 1), station_id=st_id)
    weather_series = weather_resp.get("forecast_72h", [])[:req.hours]

    engine = SyntheticSensorEngine(
        station_id=st_id,
        station_config=preset,
        imperfection_config=req.imperfection_config
    )
    
    timeline = engine.generate_timeline(
        weather_forecast=weather_series,
        scenario_modifiers={"scenario_id": req.scenario_id},
        persist=True
    )
    
    return {
        "status": "success",
        "station_id": st_id,
        "scenario_id": req.scenario_id,
        "generated_hours": len(timeline),
        "source_type": "synthetic",
        "label": "Synthetic telemetry — simulation mode",
        "timeline": timeline
    }
