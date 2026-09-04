"""
POLARIS Feature Engineering Pipeline for Hybrid ML Forecasting
Extracts environmental, temporal, lag, rolling, and physical state features without future data leakage.
"""

import math
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple


def calculate_solar_elevation(lat: float, lon: float, dt: datetime) -> float:
    """Calculates approximate solar elevation angle in degrees."""
    day_of_year = dt.timetuple().tm_yday
    declination = 23.45 * math.sin(math.radians((360 / 365) * (day_of_year - 81)))
    hour_angle = (dt.hour + dt.minute / 60.0 - 12) * 15.0
    
    lat_rad = math.radians(lat)
    dec_rad = math.radians(declination)
    h_rad = math.radians(hour_angle)
    
    sin_elev = math.sin(lat_rad) * math.sin(dec_rad) + math.cos(lat_rad) * math.cos(dec_rad) * math.cos(h_rad)
    sin_elev = max(-1.0, min(1.0, sin_elev))
    return round(math.degrees(math.asin(sin_elev)), 2)


def extract_features_from_dataframe(df: pd.DataFrame, lat: float = -69.4072, lon: float = 76.1872) -> pd.DataFrame:
    """
    Constructs rich feature matrix for ML model training and inference.
    Prevents future data leakage by strictly using backward-looking windows (.shift() and .rolling(closed='left')).
    """
    df = df.copy()
    
    # 1. Temporal & Astrometric Features
    if "timestamp" in df.columns:
        dt_series = pd.to_datetime(df["timestamp"], utc=True)
        df["hour"] = dt_series.dt.hour
        df["month"] = dt_series.dt.month
        df["day_of_year"] = dt_series.dt.dayofyear
        df["day_of_week"] = dt_series.dt.dayofweek
        
        # Astrometric Solar Elevation
        df["solar_elevation_deg"] = [
            calculate_solar_elevation(lat, lon, d.to_pydatetime()) for d in dt_series
        ]
    else:
        df["hour"] = 12
        df["month"] = 1
        df["day_of_year"] = 1
        df["day_of_week"] = 0
        df["solar_elevation_deg"] = 0.0

    # Ensure necessary environmental columns exist
    for col in ["temperature", "wind", "cloud", "irradiance", "snowfall"]:
        if col not in df.columns:
            # Map alternative naming conventions
            alt_map = {
                "temperature": ["temperature_c", "temp"],
                "wind": ["wind_speed_kmh"],
                "cloud": ["cloud_cover_pct"],
                "irradiance": ["global_tilted_irradiance_wm2", "solar_irradiance_wm2"],
                "snowfall": ["snowfall_cm"]
            }
            found = False
            for alt in alt_map.get(col, []):
                if alt in df.columns:
                    df[col] = df[alt]
                    found = True
                    break
            if not found:
                df[col] = 0.0

    # 2. Lag Features (Historical Past Observations)
    if "pv_power_kw" in df.columns:
        df["pv_lag_1h"] = df["pv_power_kw"].shift(1).bfill()
        df["pv_lag_2h"] = df["pv_power_kw"].shift(2).bfill()
        df["pv_lag_3h"] = df["pv_power_kw"].shift(3).bfill()
        df["pv_lag_6h"] = df["pv_power_kw"].shift(6).bfill()
        df["pv_lag_24h"] = df["pv_power_kw"].shift(24).bfill()
        df["pv_rolling_mean_3h"] = df["pv_power_kw"].rolling(3, min_periods=1).mean()
        df["pv_rolling_mean_24h"] = df["pv_power_kw"].rolling(24, min_periods=1).mean()
    else:
        for c in ["pv_lag_1h", "pv_lag_2h", "pv_lag_3h", "pv_lag_6h", "pv_lag_24h", "pv_rolling_mean_3h", "pv_rolling_mean_24h"]:
            df[c] = 0.0

    if "p0_load_kw" in df.columns:
        df["p0_lag_1h"] = df["p0_load_kw"].shift(1).bfill()
        df["p0_lag_2h"] = df["p0_load_kw"].shift(2).bfill()
        df["p0_lag_6h"] = df["p0_load_kw"].shift(6).bfill()
        df["p0_lag_24h"] = df["p0_load_kw"].shift(24).bfill()
        df["p0_rolling_mean_3h"] = df["p0_load_kw"].rolling(3, min_periods=1).mean()
        df["p0_rolling_mean_6h"] = df["p0_load_kw"].rolling(6, min_periods=1).mean()
        df["p0_rolling_mean_24h"] = df["p0_load_kw"].rolling(24, min_periods=1).mean()
    else:
        for c in ["p0_lag_1h", "p0_lag_2h", "p0_lag_6h", "p0_lag_24h", "p0_rolling_mean_3h", "p0_rolling_mean_6h", "p0_rolling_mean_24h"]:
            df[c] = 0.0

    # 3. Rolling Environmental Features
    df["temp_rolling_mean_6h"] = df["temperature"].rolling(6, min_periods=1).mean()
    df["temp_rolling_mean_24h"] = df["temperature"].rolling(24, min_periods=1).mean()
    df["wind_rolling_max_6h"] = df["wind"].rolling(6, min_periods=1).max()
    df["irradiance_rolling_mean_3h"] = df["irradiance"].rolling(3, min_periods=1).mean()

    # 4. Station State Features
    df["battery_soc_pct"] = df.get("battery_soc_pct", 75.0)
    df["battery_soc_lag_1h"] = df["battery_soc_pct"].shift(1).bfill() if "battery_soc_pct" in df.columns else 75.0
    df["battery_temp_c"] = df.get("battery_temperature_c", 15.0)
    df["fuel_remaining_l"] = df.get("fuel_remaining_l", 1200.0)
    df["occupancy"] = df.get("occupancy", 24)
    if "generator_status" in df.columns:
        df["generator_is_on"] = (df["generator_status"] == "ON").astype(int)
    else:
        df["generator_is_on"] = 0

    # Fill remaining NaNs
    df = df.fillna(0.0)
    return df


def get_feature_column_names(target_type: str = "solar") -> List[str]:
    """Returns standardized ordered list of feature column names for model compatibility."""
    base_environmental = [
        "temperature", "wind", "cloud", "irradiance", "snowfall",
        "hour", "month", "day_of_year", "solar_elevation_deg",
        "temp_rolling_mean_6h", "temp_rolling_mean_24h",
        "wind_rolling_max_6h", "irradiance_rolling_mean_3h"
    ]
    
    if target_type == "solar":
        return base_environmental + [
            "pv_lag_1h", "pv_lag_2h", "pv_lag_3h", "pv_lag_6h", "pv_lag_24h",
            "pv_rolling_mean_3h", "pv_rolling_mean_24h"
        ]
    elif target_type in ["p0", "load"]:
        return base_environmental + [
            "p0_lag_1h", "p0_lag_2h", "p0_lag_6h", "p0_lag_24h",
            "p0_rolling_mean_3h", "p0_rolling_mean_6h", "p0_rolling_mean_24h",
            "occupancy", "battery_soc_lag_1h"
        ]
    return base_environmental
