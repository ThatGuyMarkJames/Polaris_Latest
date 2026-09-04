"""
POLARIS XGBoost P0 / Load Residual Model Training Pipeline
Trains hybrid physics + XGBoost model for critical life-support (P0) and total station load.
"""

import os
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta

from backend.ml.models import HybridLoadForecaster
from backend.services.synthetic_telemetry_engine import SyntheticSensorEngine
from backend.data.station_presets import POLAR_STATIONS


def generate_training_dataset(hours: int = 2160) -> pd.DataFrame:
    """Generates 90 days of coupled environmental and load telemetry with continuous variation."""
    station_cfg = POLAR_STATIONS["bharati"]
    engine = SyntheticSensorEngine("bharati", station_cfg, seed=99)
    
    records = []
    now = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    
    extended_weather = []
    for h in range(hours):
        t = now + timedelta(hours=h)
        day_of_year = t.timetuple().tm_yday
        hour = t.hour
        
        # Diurnal + seasonal temperature & wind cycle
        diurnal_temp = 4.5 * np.sin(np.radians((hour - 8) * 15))
        seasonal_temp = -18.0 - 8.0 * np.sin(np.radians((day_of_year / 365.0) * 360))
        temp = round(float(seasonal_temp + diurnal_temp + np.random.normal(0, 1.2)), 1)
        
        wind = round(max(5.0, float(28.0 + 18.0 * np.sin(h / 30.0) + np.random.normal(0, 3.5))), 1)
        cloud = int(max(0, min(100, 45 + 30 * np.sin(h / 20.0) + np.random.normal(0, 8))))
        snow = round(float(max(0.0, 0.4 * (cloud / 100.0) if temp < 0 and cloud > 50 else 0.0)), 2)
        
        if (h % 350) < 48: # Storm / cold event
            temp -= 12.0
            wind *= 2.0
            snow += 2.0

        step = {
            "timestamp": t.isoformat(),
            "temperature_c": temp,
            "apparent_temperature_c": round(temp - (wind * 0.18), 1),
            "wind_speed_kmh": wind,
            "cloud_cover_pct": cloud,
            "snowfall_cm": snow,
            "precipitation_mm": snow * 0.8,
            "solar_irradiance_wm2": 0.0,
            "global_tilted_irradiance_wm2": 0.0,
            "is_day": False
        }
        extended_weather.append(step)
        
    for w in extended_weather:
        rec = engine.generate_step(w, persist=False)
        rec["irradiance"] = w.get("global_tilted_irradiance_wm2", 0.0)
        rec["temperature"] = w.get("temperature_c", -15.0)
        rec["wind"] = w.get("wind_speed_kmh", 25.0)
        rec["cloud"] = w.get("cloud_cover_pct", 50)
        rec["snowfall"] = w.get("snowfall_cm", 0.0)
        records.append(rec)
        
    return pd.DataFrame(records)


def train_and_evaluate_p0_model():
    """Executes the P0/load model training and prints holdout validation metrics."""
    print("=" * 70)
    print("POLARIS HYBRID P0 LOAD FORECASTER — XGBOOST RESIDUAL TRAINING")
    print("=" * 70)
    
    print("[1/3] Generating continuous polar training dataset (90 days / 2,160 hours)...")
    df = generate_training_dataset(hours=2160)
    print(f"      Dataset generated with {len(df)} samples.")
    
    print("[2/3] Fitting Building Thermodynamics + XGBoost P0 Residual Model...")
    forecaster = HybridLoadForecaster(model_version="2.6.0-prod")
    forecaster.train(df, station_loads=POLAR_STATIONS["bharati"]["loads"])
    
    print("[3/3] Model Trained Successfully. Evaluation Metrics on Holdout Test Partition:")
    for k, v in forecaster.evaluation_metrics.items():
        print(f"      - {k.upper()}: {v}")
    print("=" * 70)
    return forecaster


if __name__ == "__main__":
    train_and_evaluate_p0_model()
