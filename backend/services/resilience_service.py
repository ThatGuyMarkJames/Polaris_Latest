"""
POLARIS Resilience & P0 Critical Survival Horizon Service
Calculates exact physical time-to-breach for P0 life-support demand under forecast and operational constraints.
Provides conservative bounds (P10 Solar / P90 P0) for safety guarantees.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple


def calculate_p0_survival_horizon(
    station_config: Dict[str, Any],
    solar_forecast_series: List[Dict[str, Any]],
    load_forecast_series: List[Dict[str, Any]],
    current_state: Optional[Dict[str, Any]] = None,
    generator_available: bool = True,
    solar_available: bool = True
) -> Dict[str, Any]:
    """
    Computes exact physical P0 survival horizon across the forecast window.
    Evaluates both nominal (point forecast) and conservative (lower solar / upper P0) trajectories.
    """
    T = min(len(solar_forecast_series), len(load_forecast_series), 72)
    if T == 0:
        return {
            "survival_hours_remaining": 0.0,
            "operating_mode": "EMERGENCY",
            "is_breached": True,
            "message": "No forecast data available"
        }

    # Station parameters
    batt_cap_kwh = float(station_config.get("battery_capacity_kwh", station_config.get("default_battery_kwh", 600.0)))
    init_soc = float(current_state.get("battery_soc_pct", station_config.get("battery_soc_pct", 75.0))) if current_state else float(station_config.get("battery_soc_pct", 75.0))
    min_reserve_pct = float(station_config.get("battery_min_reserve_pct", 15.0)) # Absolute floor for P0 survival
    max_dis_kw = float(station_config.get("battery_max_discharge_kw", 150.0))
    gen_cap_kw = float(station_config.get("diesel_capacity_kw", 250.0)) if generator_available else 0.0
    fuel_remaining_l = float(current_state.get("fuel_remaining_l", station_config.get("diesel_fuel_l", 1200.0))) if current_state else float(station_config.get("diesel_fuel_l", 1200.0))
    fuel_rate = float(station_config.get("diesel_consumption_l_per_kwh", 0.28))
    
    # 1. NOMINAL TRAJECTORY EVALUATION
    batt_energy_nom = batt_cap_kwh * (init_soc / 100.0)
    fuel_nom = fuel_remaining_l
    min_soc_nom = init_soc
    gen_total_kwh_nom = 0.0
    p1_shed_nom = False
    p2_shed_nom = False
    breach_hour_nom: Optional[int] = None

    for t in range(T):
        sol_item = solar_forecast_series[t]
        load_item = load_forecast_series[t]
        
        p_sol = float(sol_item.get("predicted_kw", 0.0)) if solar_available else 0.0
        p0 = float(load_item.get("p0_load_kw", load_item.get("critical_load_kw", 50.0)))
        p1 = float(load_item.get("p1_load_kw", 3.0))
        p2 = float(load_item.get("p2_load_kw", load_item.get("important_load_kw", 30.0) + load_item.get("deferrable_load_kw", 20.0)))

        # Power available before battery discharge
        # Direct solar covers P0 first
        sol_for_p0 = min(p0, p_sol)
        deficit_p0 = p0 - sol_for_p0
        rem_sol = max(0.0, p_sol - sol_for_p0)

        # Usable battery energy down to safety floor
        usable_batt_energy = max(0.0, batt_energy_nom - (batt_cap_kwh * (min_reserve_pct / 100.0)))
        batt_dis = min(deficit_p0, max_dis_kw, usable_batt_energy * 0.92)
        batt_energy_nom -= (batt_dis / 0.92)
        deficit_p0 -= batt_dis

        # Generator backup if deficit remains
        if deficit_p0 > 0.0 and gen_cap_kw > 0.0 and fuel_nom > 0.0:
            gen_out = min(gen_cap_kw, deficit_p0)
            fuel_burn = gen_out * fuel_rate
            if fuel_nom >= fuel_burn:
                fuel_nom -= fuel_burn
                deficit_p0 -= gen_out
                gen_total_kwh_nom += gen_out
            else:
                gen_out = fuel_nom / fuel_rate
                fuel_nom = 0.0
                deficit_p0 -= gen_out
                gen_total_kwh_nom += gen_out

        soc_t = (batt_energy_nom / batt_cap_kwh) * 100.0
        min_soc_nom = min(min_soc_nom, soc_t)

        # Check if P2 and P1 need to be shed to protect P0
        if deficit_p0 > 0.0: # Even after all sources, P0 cannot be sustained
            breach_hour_nom = t
            break
        elif soc_t < 30.0 or fuel_nom < 150.0:
            p2_shed_nom = True
            if soc_t < 20.0:
                p1_shed_nom = True

    nominal_hours = float(breach_hour_nom) if breach_hour_nom is not None else float(T)

    # 2. CONSERVATIVE TRAJECTORY (P10 Solar / P90 P0)
    batt_energy_cons = batt_cap_kwh * (init_soc / 100.0)
    fuel_cons = fuel_remaining_l
    breach_hour_cons: Optional[int] = None
    min_soc_cons = init_soc

    for t in range(T):
        sol_item = solar_forecast_series[t]
        load_item = load_forecast_series[t]
        
        # Conservative values: Lower bound solar, upper bound P0
        p_sol = float(sol_item.get("lower_bound_kw", sol_item.get("predicted_kw", 0.0) * 0.8)) if solar_available else 0.0
        p0 = float(load_item.get("upper_bound_kw", load_item.get("p0_load_kw", 50.0) * 1.15))
        
        sol_for_p0 = min(p0, p_sol)
        deficit_p0 = p0 - sol_for_p0
        
        usable_batt_energy = max(0.0, batt_energy_cons - (batt_cap_kwh * (min_reserve_pct / 100.0)))
        batt_dis = min(deficit_p0, max_dis_kw, usable_batt_energy * 0.88)
        batt_energy_cons -= (batt_dis / 0.88)
        deficit_p0 -= batt_dis

        if deficit_p0 > 0.0 and gen_cap_kw > 0.0 and fuel_cons > 0.0:
            gen_out = min(gen_cap_kw, deficit_p0)
            fuel_burn = gen_out * fuel_rate
            if fuel_cons >= fuel_burn:
                fuel_cons -= fuel_burn
                deficit_p0 -= gen_out
            else:
                gen_out = fuel_cons / fuel_rate
                fuel_cons = 0.0
                deficit_p0 -= gen_out

        soc_t = (batt_energy_cons / batt_cap_kwh) * 100.0
        min_soc_cons = min(min_soc_cons, soc_t)

        if deficit_p0 > 0.0:
            breach_hour_cons = t
            break

    conservative_hours = float(breach_hour_cons) if breach_hour_cons is not None else float(T)

    # 3. OPERATING MODE CLASSIFICATION
    if conservative_hours < 12.0 or min_soc_cons < 20.0 or (breach_hour_nom is not None and breach_hour_nom <= 24):
        operating_mode = "EMERGENCY"
        mode_color = "#dc2626"
    elif conservative_hours < 36.0 or min_soc_cons < 35.0:
        operating_mode = "WARNING"
        mode_color = "#f59e0b"
    else:
        operating_mode = "NORMAL"
        mode_color = "#10b981"

    now = datetime.now(timezone.utc)
    est_breach_dt = (now + timedelta(hours=nominal_hours)).isoformat() if breach_hour_nom is not None else "NO_BREACH_IN_72H"
    cons_breach_dt = (now + timedelta(hours=conservative_hours)).isoformat() if breach_hour_cons is not None else "NO_BREACH_IN_72H"

    # Explainability narrative
    explainability_reasons = []
    if p2_shed_nom or operating_mode in ["WARNING", "EMERGENCY"]:
        explainability_reasons.append("P2 general load curtailment recommended to preserve critical life-support margin.")
    if p1_shed_nom or operating_mode == "EMERGENCY":
        explainability_reasons.append("P1 battery thermal jacket shed authorized: P0 demand prioritized over thermal battery protection.")
    if not generator_available:
        explainability_reasons.append("Primary diesel generator is offline; station is operating in pure renewable islanded mode.")
    if breach_hour_cons is not None and breach_hour_cons < 48:
        explainability_reasons.append(f"Conservative stress test predicts P0 power deficit in {breach_hour_cons} hours under storm conditions.")

    return {
        "operating_mode": operating_mode,
        "operating_mode_color": mode_color,
        "survival_hours_remaining": round(nominal_hours, 1),
        "conservative_survival_hours": round(conservative_hours, 1),
        "estimated_breach_time": est_breach_dt,
        "conservative_breach_time": cons_breach_dt,
        "confidence_interval_hours": [round(conservative_hours, 1), round(nominal_hours, 1)],
        "current_p0_load_kw": float(load_forecast_series[0].get("p0_load_kw", 50.0)),
        "expected_minimum_soc_pct": round(min_soc_nom, 1),
        "conservative_minimum_soc_pct": round(min_soc_cons, 1),
        "generator_contribution_kwh": round(gen_total_kwh_nom, 1),
        "fuel_remaining_liters": round(fuel_nom, 1),
        "p1_shed_status": "SHED" if p1_shed_nom else "ACTIVE",
        "p2_shed_status": "CURTAILED" if p2_shed_nom else "ACTIVE",
        "p0_status": "BREACHED" if breach_hour_nom == 0 else ("AT_RISK" if operating_mode == "EMERGENCY" else "SECURE"),
        "explainability": explainability_reasons,
        "recommended_actions": [
            "Maintain strict P0 life support priority at all times",
            "Curtail non-essential lab computing and domestic hot water heating (P2)",
            "Engage auxiliary backup generator if available" if operating_mode != "NORMAL" else "Optimal dispatch schedule maintained"
        ]
    }
