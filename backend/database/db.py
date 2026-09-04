"""
POLARIS Database Connection and Data Access Layer
Provides helper functions for inserting, querying, and managing telemetry records.
"""

import sqlite3
import os
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from .schema import create_schema

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "polaris.db")

def get_db_connection() -> sqlite3.Connection:
    """Returns a thread-safe connection to the SQLite database with schemas applied."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    return conn


def insert_raw_payload(station_id: str, source: str, raw_json: str, timestamp: Optional[str] = None):
    """Stores raw untouched payload for immutable audit trail."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()
    ts = timestamp or now_iso
    cursor.execute("""
        INSERT INTO raw_environmental_payloads (timestamp, station_id, source, raw_json, ingestion_timestamp)
        VALUES (?, ?, ?, ?, ?)
    """, (ts, station_id, source, raw_json, now_iso))
    conn.commit()


def insert_environmental_telemetry(station_id: str, record: Dict[str, Any], raw_payload_str: Optional[str] = None):
    """Persists a normalized environmental telemetry record (Pipeline A)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()
    ts = record.get("timestamp", now_iso)
    
    cursor.execute("""
        INSERT INTO environmental_telemetry (
            timestamp, station_id, temperature, apparent_temperature, wind, wind_gusts,
            wind_direction, cloud, snowfall, precipitation, irradiance,
            direct_normal_irradiance, global_tilted_irradiance, diffuse_radiation,
            surface_pressure, humidity, source, quality, raw_payload, ingestion_timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        ts,
        station_id,
        record.get("temperature_c", record.get("temperature")),
        record.get("apparent_temperature_c", record.get("apparent_temperature")),
        record.get("wind_speed_kmh", record.get("wind")),
        record.get("wind_gusts_kmh", record.get("wind_gusts")),
        record.get("wind_direction_deg", record.get("wind_direction")),
        record.get("cloud_cover_pct", record.get("cloud")),
        record.get("snowfall_cm", record.get("snowfall")),
        record.get("precipitation_mm", record.get("precipitation")),
        record.get("solar_irradiance_wm2", record.get("irradiance")),
        record.get("direct_normal_irradiance_wm2", record.get("direct_normal_irradiance")),
        record.get("global_tilted_irradiance_wm2", record.get("global_tilted_irradiance")),
        record.get("diffuse_radiation_wm2", record.get("diffuse_radiation")),
        record.get("surface_pressure_hpa", record.get("surface_pressure")),
        record.get("relative_humidity_pct", record.get("humidity")),
        record.get("source", "Open-Meteo"),
        record.get("quality", "OK"),
        raw_payload_str,
        now_iso
    ))
    conn.commit()


def insert_energy_telemetry(station_id: str, record: Dict[str, Any]):
    """Persists a station sensor telemetry record (Pipeline B)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()
    ts = record.get("timestamp", now_iso)
    
    cursor.execute("""
        INSERT INTO energy_telemetry (
            timestamp, station_id, pv_power_kw, p0_load_kw, p1_load_kw, p2_load_kw,
            total_load_kw, battery_soc_pct, battery_soh_pct, battery_power_kw,
            battery_voltage_v, battery_current_a, battery_temperature_c,
            generator_power_kw, generator_status, fuel_remaining_l, occupancy,
            indoor_temperature_c, source_type, source_id, data_quality, ingestion_timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        ts,
        station_id,
        record.get("pv_power_kw"),
        record.get("p0_load_kw"),
        record.get("p1_load_kw"),
        record.get("p2_load_kw"),
        record.get("total_load_kw"),
        record.get("battery_soc_pct"),
        record.get("battery_soh_pct", 100.0),
        record.get("battery_power_kw", 0.0),
        record.get("battery_voltage_v", 400.0),
        record.get("battery_current_a", 0.0),
        record.get("battery_temperature_c", 15.0),
        record.get("generator_power_kw", 0.0),
        record.get("generator_status", "OFF"),
        record.get("fuel_remaining_l"),
        record.get("occupancy", 24),
        record.get("indoor_temperature_c", 20.0),
        record.get("source_type", "synthetic"),
        record.get("source_id", "sim-default"),
        record.get("data_quality", "OK"),
        now_iso
    ))
    conn.commit()


def get_latest_telemetry(station_id: str) -> Dict[str, Any]:
    """Retrieves the latest fused environmental and sensor state for a station."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM energy_telemetry WHERE station_id = ? ORDER BY id DESC LIMIT 1
    """, (station_id,))
    energy_row = cursor.fetchone()
    
    cursor.execute("""
        SELECT * FROM environmental_telemetry WHERE station_id = ? ORDER BY id DESC LIMIT 1
    """, (station_id,))
    env_row = cursor.fetchone()
    
    energy_dict = dict(energy_row) if energy_row else {}
    env_dict = dict(env_row) if env_row else {}
    
    return {
        "station_id": station_id,
        "energy": energy_dict,
        "environmental": env_dict,
        "timestamp": energy_dict.get("timestamp") or env_dict.get("timestamp") or datetime.now(timezone.utc).isoformat()
    }


def query_telemetry_history(station_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Returns historical energy and environmental records."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT eng.*, env.temperature, env.wind, env.cloud, env.snowfall, env.irradiance
        FROM energy_telemetry eng
        LEFT JOIN environmental_telemetry env ON eng.station_id = env.station_id AND eng.timestamp = env.timestamp
        WHERE eng.station_id = ?
        ORDER BY eng.id DESC LIMIT ?
    """, (station_id, limit))
    
    rows = cursor.fetchall()
    return [dict(r) for r in rows]
