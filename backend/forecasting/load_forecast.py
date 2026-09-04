"""
POLARIS AI Load & Demand Forecasting Engine
Predicts future P0, P1, P2, and total microgrid demand using
Physics Thermodynamics Baseline + XGBoost Residuals with Quantile Prediction Intervals.
All metrics are derived dynamically from model evaluation.
"""

from typing import Dict, Any, List, Optional
from backend.ml.models import HybridLoadForecaster
from backend.data.station_presets import POLAR_STATIONS

# Lazy-loaded singleton forecaster
_LOAD_FORECASTER: Optional[HybridLoadForecaster] = None


def get_load_forecaster() -> HybridLoadForecaster:
    """Returns singleton load forecaster, loading from disk if present."""
    global _LOAD_FORECASTER
    if _LOAD_FORECASTER is None:
        _LOAD_FORECASTER = HybridLoadForecaster()
        if not _LOAD_FORECASTER.load():
            from backend.ml.train_p0 import generate_training_dataset
            df = generate_training_dataset(hours=720)
            _LOAD_FORECASTER.train(df, station_loads=POLAR_STATIONS["bharati"]["loads"])
    return _LOAD_FORECASTER


def get_ml_load_forecast(
    weather_forecast_series: List[Dict[str, Any]],
    loads: Optional[List[Dict[str, Any]]] = None,
    occupants: int = 24,
    operating_mode: str = "Normal Operation",
    p1_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generates multi-horizon hybrid load forecast for total, critical (P0), P1 jacket, and P2 demand.
    """
    forecaster = get_load_forecaster()
    active_loads = loads if loads else POLAR_STATIONS["bharati"]["loads"]
    
    result = forecaster.predict(
        weather_forecast=weather_forecast_series,
        loads=active_loads,
        occupants=occupants,
        operating_mode=operating_mode,
        p1_config=p1_config
    )
    return result
