"""
POLARIS Data Fusion Module
Merges Pipeline A (Environmental Telemetry) and Pipeline B (Station Sensor Telemetry)
into a unified, physically grounded station state vector.

All units conform strictly to standard engineering/SI definitions:
  - Power: Kilowatts (kW)
  - Energy: Kilowatt-hours (kWh)
  - Temperature: Degrees Celsius (°C)
  - Irradiance: Watts per square meter (W/m²)
  - Wind Speed: Kilometers per hour (km/h)
  - Liquid Fuel: Liters (L)
  - Percentage: Percent (%)
  - Voltage: Volts (V)
  - Current: Amperes (A)
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone


def fuse_telemetry_streams(
    environmental_record: Dict[str, Any],
    energy_record: Dict[str, Any],
    station_id: str
) -> Dict[str, Any]:
    """
    Fuses environmental telemetry (Pipeline A) and sensor measurements (Pipeline B)
    into a single cohesive state vector.
    """
    ts = energy_record.get("timestamp") or environmental_record.get("timestamp") or datetime.now(timezone.utc).isoformat()
    
    # Combined Data Quality Flag (Worst-case aggregation)
    env_quality = environmental_record.get("quality", "OK")
    eng_quality = energy_record.get("data_quality", "OK")
    if "CRITICAL" in [env_quality, eng_quality]:
        overall_quality = "CRITICAL"
    elif "FLAGGED" in [env_quality, eng_quality]:
        overall_quality = "FLAGGED"
    else:
        overall_quality = "OK"

    flags = energy_record.get("quality_flags", [])

    return {
        "timestamp": ts,
        "station_id": station_id,
        
        # --- Atmospheric State (Pipeline A) ---
        "temperature_c": environmental_record.get("temperature_c", environmental_record.get("temperature", -15.0)),
        "apparent_temperature_c": environmental_record.get("apparent_temperature_c", environmental_record.get("apparent_temperature", -18.0)),
        "wind_speed_kmh": environmental_record.get("wind_speed_kmh", environmental_record.get("wind", 25.0)),
        "wind_gusts_kmh": environmental_record.get("wind_gusts_kmh", environmental_record.get("wind_gusts", 32.0)),
        "cloud_cover_pct": environmental_record.get("cloud_cover_pct", environmental_record.get("cloud", 50)),
        "snowfall_cm": environmental_record.get("snowfall_cm", environmental_record.get("snowfall", 0.0)),
        "precipitation_mm": environmental_record.get("precipitation_mm", environmental_record.get("precipitation", 0.0)),
        "solar_irradiance_wm2": environmental_record.get("solar_irradiance_wm2", environmental_record.get("irradiance", 0.0)),
        "global_tilted_irradiance_wm2": environmental_record.get("global_tilted_irradiance_wm2", environmental_record.get("global_tilted_irradiance", 0.0)),
        "direct_normal_irradiance_wm2": environmental_record.get("direct_normal_irradiance_wm2", environmental_record.get("direct_normal_irradiance", 0.0)),
        "is_day": environmental_record.get("is_day", True),
        "is_storm": environmental_record.get("is_storm", False),

        # --- Microgrid Electrical State (Pipeline B) ---
        "pv_power_kw": energy_record.get("pv_power_kw", 0.0),
        "p0_critical_load_kw": energy_record.get("p0_load_kw", 0.0),
        "p1_battery_jacket_kw": energy_record.get("p1_load_kw", 0.0),
        "p2_general_load_kw": energy_record.get("p2_load_kw", 0.0),
        "total_load_kw": energy_record.get("total_load_kw", 0.0),
        
        # --- Energy Storage & Generator State ---
        "battery_soc_pct": energy_record.get("battery_soc_pct", 75.0),
        "battery_soh_pct": energy_record.get("battery_soh_pct", 100.0),
        "battery_power_kw": energy_record.get("battery_power_kw", 0.0),
        "battery_voltage_v": energy_record.get("battery_voltage_v", 400.0),
        "battery_current_a": energy_record.get("battery_current_a", 0.0),
        "battery_temperature_c": energy_record.get("battery_temperature_c", 15.0),
        "generator_power_kw": energy_record.get("generator_power_kw", 0.0),
        "generator_status": energy_record.get("generator_status", "OFF"),
        "fuel_remaining_l": energy_record.get("fuel_remaining_l", 1200.0),
        
        # --- Habitat Environmental State ---
        "occupancy": energy_record.get("occupancy", 24),
        "indoor_temperature_c": energy_record.get("indoor_temperature_c", 20.0),
        
        # --- Metadata & Quality Assurance ---
        "source_type": energy_record.get("source_type", "synthetic"),
        "source_id": energy_record.get("source_id", "live-fused"),
        "environmental_source": environmental_record.get("source", "Open-Meteo"),
        "data_quality": overall_quality,
        "quality_flags": flags
    }
