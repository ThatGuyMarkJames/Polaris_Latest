"""
POLARIS XGBoost Solar Residual Model Training Pipeline
Trains hybrid physics + XGBoost model on multi-scenario polar telemetry using walk-forward validation.
"""

import os
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta

from backend.ml.models import HybridSolarForecaster
from backend.services.synthetic_telemetry_engine import SyntheticSensorEngine
from backend.services.weather_service import _generate_realistic_polar_data
from backend.data.station_presets import POLAR_STATIONS


def generate_training_dataset(hours: int = 2160) -> pd.DataFrame:
    """
    Generates 90 days (2,160 hours) of multi-season, multi-scenario telemetry for model training.
    """
    station_cfg = POLAR_STATIONS["bharati"]
    engine = SyntheticSensorEngine("bharati", station_cfg, seed=42)
    
    records = []
    now = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    
    extended_weather = []
    for h in range(hours):
        t = now + timedelta(hours=h)
        day_of_year = t.timetuple().tm_yday
        hour = t.hour
        
        # Diurnal and seasonal weather generation
        diurnal_temp = 4.0 * np.sin(np.radians((hour - 8) * 15))
        seasonal_temp = -15.0 - 10.0 * np.sin(np.radians((day_of_year / 365.0) * 360))
        temp = round(float(seasonal_temp + diurnal_temp + np.random.normal(0, 1.5)), 1)
        
        wind = round(max(5.0, float(25.0 + 15.0 * np.sin(h / 24.0) + np.random.normal(0, 4.0))), 1)
        cloud = int(max(0, min(100, 40 + 35 * np.sin(h / 18.0) + np.random.normal(0, 10))))
        
        # Solar elevation & irradiance
        lat_rad = np.radians(-69.4072)
        dec_rad = np.radians(23.45 * np.sin(np.radians((360 / 365) * (day_of_year - 81))))
        h_rad = np.radians((hour - 12) * 15.0)
        sin_elev = np.sin(lat_rad) * np.sin(dec_rad) + np.cos(lat_rad) * np.cos(dec_rad) * np.cos(h_rad)
        
        if sin_elev > 0:
            dni = max(0.0, 900.0 * (sin_elev ** 1.1) * (1.0 - cloud / 120.0))
            ghi = dni * sin_elev + 60.0 * sin_elev
            gti = ghi * 1.35
            is_day = True
        else:
            dni, ghi, gti = 0.0, 0.0, 0.0
            is_day = False
            
        snow = round(float(max(0.0, 0.3 * (cloud / 100.0) if temp < 0 and cloud > 60 else 0.0)), 2)

        # Storm intervals
        if (h % 300) < 36:
            wind *= 2.2
            temp -= 8.0
            snow += 1.5
            gti *= 0.3

        step = {
            "timestamp": t.isoformat(),
            "temperature_c": temp,
            "apparent_temperature_c": round(temp - (wind * 0.18), 1),
            "wind_speed_kmh": wind,
            "cloud_cover_pct": cloud,
            "snowfall_cm": snow,
            "precipitation_mm": snow * 0.8,
            "solar_irradiance_wm2": round(ghi, 1),
            "global_tilted_irradiance_wm2": round(gti, 1),
            "direct_normal_irradiance_wm2": round(dni, 1),
            "is_day": is_day
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


def train_and_evaluate_solar_model():
    """Executes the solar model training and prints comprehensive evaluation metrics."""
    print("=" * 70)
    print("POLARIS HYBRID SOLAR FORECASTER — XGBOOST RESIDUAL TRAINING")
    print("=" * 70)
    
    print("[1/3] Generating continuous polar training dataset (90 days / 2,160 hours)...")
    df = generate_training_dataset(hours=2160)
    print(f"      Dataset generated with {len(df)} samples and {len(df.columns)} telemetry fields.")
    
    print("[2/3] Fitting Physics Baseline + XGBoost Residual Model (Walk-Forward Validation)...")
    forecaster = HybridSolarForecaster(model_version="2.6.0-prod")
    forecaster.train(df, solar_capacity_kw=180.0, efficiency_pct=21.5)
    
    print("[3/3] Model Trained Successfully. Evaluation Metrics on Holdout Test Partition:")
    for k, v in forecaster.evaluation_metrics.items():
        print(f"      - {k.upper()}: {v}")
    print("=" * 70)
    return forecaster


if __name__ == "__main__":
    train_and_evaluate_solar_model()
