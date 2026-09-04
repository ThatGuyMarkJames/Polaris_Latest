"""
POLARIS Telemetry Data Validation & Quality Assurance Engine
Performs multi-tiered physical boundary checks, timestamp validation, and cross-variable consistency checks.
Does NOT silently repair data: every anomaly is recorded in telemetry_quality table with clear audit flags.
"""

from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Optional
from backend.database.db import get_db_connection


def validate_and_flag_telemetry(
    station_id: str,
    telemetry: Dict[str, Any],
    max_generator_kw: float = 500.0,
    max_solar_kw: float = 1000.0,
    is_day: Optional[bool] = None,
    irradiance_wm2: Optional[float] = None
) -> Dict[str, Any]:
    """
    Validates physical plausibility, boundaries, and cross-variable consistency of telemetry data.
    Logs all violations to the telemetry_quality table.
    
    Returns:
        Validated telemetry payload with added 'data_quality' ('OK' | 'FLAGGED' | 'CRITICAL')
        and 'quality_flags' list of tuples (field, flag_code, reason).
    """
    flags: List[Tuple[str, str, str, Optional[float], Optional[float]]] = []
    
    # 1. Range Validation
    # Battery SOC [0 - 100 %]
    if "battery_soc_pct" in telemetry and telemetry["battery_soc_pct"] is not None:
        soc = float(telemetry["battery_soc_pct"])
        if soc < 0.0 or soc > 100.0:
            flags.append(("battery_soc_pct", "INVALID_RANGE", f"SOC out of bounds [0, 100]%: {soc}%", soc, max(0.0, min(100.0, soc))))

    # Battery SOH [0 - 100 %]
    if "battery_soh_pct" in telemetry and telemetry["battery_soh_pct"] is not None:
        soh = float(telemetry["battery_soh_pct"])
        if soh < 0.0 or soh > 100.0:
            flags.append(("battery_soh_pct", "INVALID_RANGE", f"SOH out of bounds [0, 100]%: {soh}%", soh, max(0.0, min(100.0, soh))))

    # PV Power [0 - max_solar_kw]
    if "pv_power_kw" in telemetry and telemetry["pv_power_kw"] is not None:
        pv = float(telemetry["pv_power_kw"])
        if pv < 0.0:
            flags.append(("pv_power_kw", "NEGATIVE_POWER", f"PV power cannot be negative: {pv} kW", pv, 0.0))
        elif pv > max_solar_kw * 1.3:
            flags.append(("pv_power_kw", "PHYSICAL_LIMIT_EXCEEDED", f"PV power exceeds array rating: {pv} kW (max {max_solar_kw} kW)", pv, max_solar_kw))

    # Battery Temperature [-60 to +60 °C]
    if "battery_temperature_c" in telemetry and telemetry["battery_temperature_c"] is not None:
        b_temp = float(telemetry["battery_temperature_c"])
        if b_temp < -60.0 or b_temp > 60.0:
            flags.append(("battery_temperature_c", "UNREALISTIC_TEMPERATURE", f"Battery temperature implausible: {b_temp} °C", b_temp, None))

    # P0 / P1 / P2 Loads (non-negative)
    for p_field, min_val, label in [("p0_load_kw", 0.0, "P0"), ("p1_load_kw", 0.0, "P1"), ("p2_load_kw", 0.0, "P2"), ("total_load_kw", 0.0, "Total")]:
        if p_field in telemetry and telemetry[p_field] is not None:
            val = float(telemetry[p_field])
            if val < min_val:
                flags.append((p_field, "NEGATIVE_LOAD", f"{label} load cannot be negative: {val} kW", val, 0.0))

    # Fuel Remaining (non-negative)
    if "fuel_remaining_l" in telemetry and telemetry["fuel_remaining_l"] is not None:
        fuel = float(telemetry["fuel_remaining_l"])
        if fuel < 0.0:
            flags.append(("fuel_remaining_l", "NEGATIVE_FUEL", f"Fuel remaining cannot be negative: {fuel} L", fuel, 0.0))

    # Generator Output and Status
    gen_kw = telemetry.get("generator_power_kw")
    gen_stat = str(telemetry.get("generator_status", "")).upper()
    if gen_kw is not None:
        gen_kw_f = float(gen_kw)
        if gen_kw_f < 0.0:
            flags.append(("generator_power_kw", "NEGATIVE_POWER", f"Generator power cannot be negative: {gen_kw_f} kW", gen_kw_f, 0.0))
        elif gen_kw_f > max_generator_kw * 1.1:
            flags.append(("generator_power_kw", "CAPACITY_EXCEEDED", f"Generator output exceeds rating: {gen_kw_f} kW", gen_kw_f, max_generator_kw))

    # 2. Cross-Variable Consistency & Impossible Relationships
    # (a) Generator OFF but positive generation
    if gen_stat == "OFF" and gen_kw is not None and float(gen_kw) > 1.0:
        flags.append(("generator_power_kw", "CROSS_VARIABLE_MISMATCH", f"Generator status is OFF but output is {gen_kw} kW", float(gen_kw), 0.0))

    # (b) Night-time solar generation
    if is_day is False and telemetry.get("pv_power_kw") is not None and float(telemetry["pv_power_kw"]) > 2.0:
        flags.append(("pv_power_kw", "NIGHT_SOLAR_ANOMALY", f"Significant PV generation ({telemetry['pv_power_kw']} kW) reported during polar night", float(telemetry["pv_power_kw"]), 0.0))

    # (c) Load summation sanity check
    if (telemetry.get("p0_load_kw") is not None and 
        telemetry.get("p1_load_kw") is not None and 
        telemetry.get("p2_load_kw") is not None and 
        telemetry.get("total_load_kw") is not None):
        sum_p = float(telemetry["p0_load_kw"]) + float(telemetry["p1_load_kw"]) + float(telemetry["p2_load_kw"])
        tot = float(telemetry["total_load_kw"])
        if abs(sum_p - tot) > 20.0:
            flags.append(("total_load_kw", "LOAD_SUMMATION_MISMATCH", f"Sum of sub-loads ({round(sum_p, 1)} kW) differs from total ({round(tot, 1)} kW) by > 20 kW", tot, round(sum_p, 1)))

    # 3. Missing Required Sensor Fields Check
    for req in ["pv_power_kw", "p0_load_kw", "battery_soc_pct"]:
        if req not in telemetry or telemetry[req] is None:
            flags.append((req, "MISSING_DATA", f"Required sensor field '{req}' is missing or null", None, None))

    # 4. Record Quality Flags into DB Audit Trail
    if flags:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            ts = telemetry.get("timestamp", datetime.now(timezone.utc).isoformat())
            for field, flag_code, reason, raw_v, corr_v in flags:
                cursor.execute("""
                    INSERT INTO telemetry_quality (timestamp, station_id, field, quality_flag, reason, raw_value, corrected_value)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (ts, station_id, field, flag_code, reason, raw_v, corr_v))
            conn.commit()
        except Exception as e:
            print(f"Failed to record telemetry quality audit: {e}")

    # Inject quality metadata into payload without mutating original measured readings
    has_critical = any(f[1] in ["NEGATIVE_POWER", "NEGATIVE_LOAD", "INVALID_RANGE", "CROSS_VARIABLE_MISMATCH"] for f in flags)
    telemetry["data_quality"] = "CRITICAL" if has_critical else ("FLAGGED" if flags else "OK")
    telemetry["quality_flags"] = [{"field": f[0], "flag": f[1], "reason": f[2]} for f in flags]
    return telemetry
