"""
POLARIS Telemetry & Persistence Database Schema
Supports Dual Pipeline Ingestion (Pipeline A: Environmental, Pipeline B: Station Sensors),
Raw Auditing, Observability, and P1 Configuration.
"""

import sqlite3

def create_schema(conn: sqlite3.Connection):
    cursor = conn.cursor()

    # 1. Stations table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS stations (
        station_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        configuration_version TEXT DEFAULT '2.0.0',
        elevation_m REAL DEFAULT 0.0,
        operator TEXT DEFAULT 'National Polar Program'
    )
    """)

    # 2. Environmental Telemetry (Pipeline A - Normalized Open-Meteo & Weather data)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS environmental_telemetry (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        station_id TEXT NOT NULL,
        temperature REAL,
        apparent_temperature REAL,
        wind REAL,
        wind_gusts REAL,
        wind_direction REAL,
        cloud REAL,
        snowfall REAL,
        precipitation REAL,
        irradiance REAL,
        direct_normal_irradiance REAL,
        global_tilted_irradiance REAL,
        diffuse_radiation REAL,
        surface_pressure REAL,
        humidity REAL,
        source TEXT DEFAULT 'Open-Meteo',
        quality TEXT DEFAULT 'OK',
        raw_payload TEXT,
        ingestion_timestamp TEXT,
        FOREIGN KEY (station_id) REFERENCES stations(station_id)
    )
    """)

    # 3. Energy & Sensor Telemetry (Pipeline B - Station physical measurements)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS energy_telemetry (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        station_id TEXT NOT NULL,
        pv_power_kw REAL,
        p0_load_kw REAL,
        p1_load_kw REAL,
        p2_load_kw REAL,
        total_load_kw REAL,
        battery_soc_pct REAL,
        battery_soh_pct REAL DEFAULT 100.0,
        battery_power_kw REAL,
        battery_voltage_v REAL,
        battery_current_a REAL,
        battery_temperature_c REAL,
        generator_power_kw REAL,
        generator_status TEXT,
        fuel_remaining_l REAL,
        occupancy INTEGER,
        indoor_temperature_c REAL,
        source_type TEXT DEFAULT 'synthetic', -- 'synthetic', 'historical', 'live', 'open_meteo'
        source_id TEXT,
        data_quality TEXT DEFAULT 'OK',
        ingestion_timestamp TEXT,
        FOREIGN KEY (station_id) REFERENCES stations(station_id)
    )
    """)

    # 4. Raw Environmental Payloads (Audit Trail - Never silently overwritten)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS raw_environmental_payloads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        station_id TEXT NOT NULL,
        source TEXT NOT NULL,
        raw_json TEXT NOT NULL,
        ingestion_timestamp TEXT NOT NULL,
        FOREIGN KEY (station_id) REFERENCES stations(station_id)
    )
    """)

    # 5. Telemetry Quality Logs (Validation & Anomaly tracking)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS telemetry_quality (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        station_id TEXT NOT NULL,
        field TEXT NOT NULL,
        quality_flag TEXT NOT NULL, -- 'INVALID_RANGE', 'NEGATIVE_POWER', 'PHYSICS_VIOLATION', 'MISSING_DATA', 'SENSOR_DRIFT', 'CROSS_VARIABLE_MISMATCH'
        reason TEXT NOT NULL,
        raw_value REAL,
        corrected_value REAL,
        FOREIGN KEY (station_id) REFERENCES stations(station_id)
    )
    """)

    # 6. P1 Battery Thermal Jacket Configuration
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS p1_config (
        station_id TEXT PRIMARY KEY,
        nominal_jacket_power_kw REAL DEFAULT 3.0,
        min_battery_temp_c REAL DEFAULT -20.0,
        activation_threshold_c REAL DEFAULT -10.0,
        emergency_shutdown_threshold_c REAL DEFAULT -5.0,
        thermal_protection_mode TEXT DEFAULT 'auto',
        FOREIGN KEY (station_id) REFERENCES stations(station_id)
    )
    """)

    # 7. Forecast & Observability Audit Log
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS forecast_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        station_id TEXT NOT NULL,
        model_version TEXT NOT NULL,
        input_data_version TEXT,
        horizon_hours INTEGER NOT NULL,
        prediction_type TEXT NOT NULL, -- 'solar', 'p0_load', 'hybrid'
        predictions_json TEXT NOT NULL,
        uncertainty_json TEXT NOT NULL,
        optimizer_status TEXT,
        actions_json TEXT,
        safety_decision TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (station_id) REFERENCES stations(station_id)
    )
    """)

    # Create Indexes for high performance temporal querying
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_env_st_ts ON environmental_telemetry(station_id, timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_eng_st_ts ON energy_telemetry(station_id, timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_st_ts ON raw_environmental_payloads(station_id, timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_qual_st_ts ON telemetry_quality(station_id, timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_fc_st_ts ON forecast_log(station_id, timestamp)")

    conn.commit()
