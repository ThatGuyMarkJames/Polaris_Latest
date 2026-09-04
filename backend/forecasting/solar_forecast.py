"""
POLARIS AI Solar Forecasting Engine
Predicts future solar generation across 1h, 6h, 24h, 48h, and 72h horizons using
Physics Baseline + XGBoost Residual Hybrid Architecture with Quantile Uncertainty Bounds.
All metrics are derived dynamically from model evaluation.
"""

from typing import Dict, Any, List, Optional
import pandas as pd
from backend.ml.models import HybridSolarForecaster

# Lazy-loaded singleton forecaster
_SOLAR_FORECASTER: Optional[HybridSolarForecaster] = None


def get_solar_forecaster() -> HybridSolarForecaster:
    """Returns singleton forecaster, loading from disk if present."""
    global _SOLAR_FORECASTER
    if _SOLAR_FORECASTER is None:
        _SOLAR_FORECASTER = HybridSolarForecaster()
        if not _SOLAR_FORECASTER.load():
            # If not yet pre-trained on disk, train on initial dataset
            from backend.ml.train_solar import generate_training_dataset
            df = generate_training_dataset(hours=720) # 30 days fast init
            _SOLAR_FORECASTER.train(df, solar_capacity_kw=180.0, efficiency_pct=21.5)
    return _SOLAR_FORECASTER


def predict_solar_generation(
    solar_capacity_kw: float,
    efficiency_pct: float,
    weather_forecast: List[Dict[str, Any]],
    snow_coverage_pct: float = 0.0,
    recent_telemetry_history: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Generates multi-horizon hybrid solar PV forecast with statistically-grounded uncertainty bounds.
    """
    forecaster = get_solar_forecaster()
    recent_df = pd.DataFrame(recent_telemetry_history) if recent_telemetry_history else None
    
    result = forecaster.predict(
        weather_forecast=weather_forecast,
        solar_capacity_kw=solar_capacity_kw,
        efficiency_pct=efficiency_pct,
        recent_telemetry_df=recent_df
    )
    return result
