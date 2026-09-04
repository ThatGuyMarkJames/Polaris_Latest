"""
Unit tests for POLARIS Dual Telemetry Pipeline and Data Validator
"""

import pytest
from backend.services.data_validator import validate_and_flag_telemetry
from backend.services.synthetic_telemetry_engine import SyntheticSensorEngine
from backend.database.db import get_db_connection, insert_environmental_telemetry, insert_energy_telemetry
from backend.data.station_presets import POLAR_STATIONS


def test_validator_detects_negative_pv():
    invalid_record = {"pv_power_kw": -10.5, "p0_load_kw": 50.0, "battery_soc_pct": 80.0}
    validated = validate_and_flag_telemetry("bharati", invalid_record)
    assert validated["data_quality"] in ["FLAGGED", "CRITICAL"]
    flags = [f["flag"] for f in validated["quality_flags"]]
    assert "NEGATIVE_POWER" in flags


def test_validator_detects_impossible_generator_state():
    # Generator is OFF but producing 150 kW
    invalid_record = {
        "pv_power_kw": 50.0,
        "p0_load_kw": 60.0,
        "battery_soc_pct": 75.0,
        "generator_status": "OFF",
        "generator_power_kw": 150.0
    }
    validated = validate_and_flag_telemetry("bharati", invalid_record)
    flags = [f["flag"] for f in validated["quality_flags"]]
    assert "CROSS_VARIABLE_MISMATCH" in flags


def test_validator_detects_soc_out_of_bounds():
    invalid_record = {"pv_power_kw": 20.0, "p0_load_kw": 40.0, "battery_soc_pct": 115.0}
    validated = validate_and_flag_telemetry("bharati", invalid_record)
    flags = [f["flag"] for f in validated["quality_flags"]]
    assert "INVALID_RANGE" in flags


def test_synthetic_sensor_engine_reproducibility():
    station = POLAR_STATIONS["bharati"]
    weather = {"temperature_c": -20.0, "wind_speed_kmh": 35.0, "solar_irradiance_wm2": 450.0, "is_day": True}
    
    eng1 = SyntheticSensorEngine("bharati", station, seed=42)
    step1 = eng1.generate_step(weather, persist=False)
    
    eng2 = SyntheticSensorEngine("bharati", station, seed=42)
    step2 = eng2.generate_step(weather, persist=False)
    
    assert step1["pv_power_kw"] == step2["pv_power_kw"]
    assert step1["p0_load_kw"] == step2["p0_load_kw"]
    assert step1["source_type"] == "synthetic"
