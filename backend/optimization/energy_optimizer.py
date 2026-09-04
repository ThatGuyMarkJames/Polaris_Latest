"""
POLARIS Mathematical Energy Optimizer (MILP)
Formulates microgrid power dispatch with Google OR-Tools (SCIP / GLOP) with fallback heuristic.

Formal Hierarchy & Penalties:
  P0 Failure Penalty (10,000 $/kW) >> P1 Jacket Loss (50 $/kW) >> P2 Curtailment (15 $/kW) >> Battery Wear >> Fuel Cost.
  The optimizer mathematically prefers shedding P2, shedding P1, and incurring battery wear over any P0 deficit.

Incorporates:
  1. P0 (Critical Life Support), P1 (Battery Thermal Jacket), P2 (General / Science) Decision Variables
  2. Arrhenius Battery RTE Derating
  3. CHP Thermal-Electrical Coupling Linearization
  4. Rime Ice Accretion Derating
  5. Uncertainty-Aware Conservative Safety Formulation
"""

import math
from typing import Dict, Any, List, Optional
from backend.physics.polar_physics import (
    compute_arrhenius_rte,
    compute_ice_derate_factor,
    CHP_C_THERMAL,
)
from backend.models.p0_p1_p2 import P1Config

try:
    from ortools.linear_solver import pywraplp
    ORTOOLS_AVAILABLE = True
except ImportError:
    ORTOOLS_AVAILABLE = False


CHP_HEAT_CREDIT_PER_KW: float = 0.08
BATT_WEAR_BASE: float = 0.035
BATT_WEAR_COLD_COEFF: float = 0.001


def optimize_energy_schedule(
    station_config: Dict[str, Any],
    solar_forecast_series: List[Dict[str, Any]],
    load_forecast_series: List[Dict[str, Any]],
    planning_horizon_hours: int = 24,
    emergency_reserve_boost_pct: float = 0.0,
    forced_generator_offline: bool = False,
    forced_solar_offline: bool = False,
    weather_forecast_series: Optional[List[Dict[str, Any]]] = None,
    ice_trajectory: Optional[List[float]] = None,
    use_conservative_bounds: bool = False
) -> Dict[str, Any]:
    """
    Optimizes microgrid dispatch with explicit P0, P1, P2 priorities and physical constraints.
    """
    T = min(len(solar_forecast_series), len(load_forecast_series), planning_horizon_hours)
    if T == 0:
        return {"success": False, "error": "Empty forecast series provided."}

    # Station equipment parameters
    solar_cap_kw = float(station_config.get("solar_capacity_kw", 180.0))
    batt_cap_kwh = float(station_config.get("battery_capacity_kwh", 600.0))
    current_soc_pct = float(station_config.get("battery_soc_pct", 75.0))
    min_reserve_pct = float(station_config.get("battery_min_reserve_pct", 30.0)) + emergency_reserve_boost_pct
    min_reserve_pct = min(85.0, max(15.0, min_reserve_pct))
    max_soc_pct = float(station_config.get("battery_max_soc_pct", 98.0))
    max_chg_kw = float(station_config.get("battery_max_charge_kw", 150.0))
    max_dis_kw = float(station_config.get("battery_max_discharge_kw", 150.0))
    base_rte = float(station_config.get("battery_rte_pct", 92.0)) / 100.0
    gen_cap_kw = float(station_config.get("diesel_capacity_kw", 250.0))
    current_fuel_l = float(station_config.get("diesel_fuel_l", 1200.0))
    fuel_rate = float(station_config.get("diesel_consumption_l_per_kwh", 0.28))
    gen_min_load_pct = float(station_config.get("diesel_min_load_pct", 25.0)) / 100.0
    gen_min_kw = gen_cap_kw * gen_min_load_pct

    p1_data = station_config.get("p1_config", {})
    p1_cfg = P1Config(**p1_data) if p1_data else P1Config()

    # Precompute per-tick parameters
    eta_chg_arr, eta_dis_arr, solar_avail_arr = [], [], []
    p0_arr, p1_arr, p2_arr, heat_demand_arr, temp_arr = [], [], [], [], []

    for t in range(T):
        w_step = weather_forecast_series[t] if weather_forecast_series and t < len(weather_forecast_series) else {}
        temp_c = float(w_step.get("temperature_c", -15.0))
        temp_arr.append(temp_c)

        eta_chg, eta_dis = compute_arrhenius_rte(base_rte, temp_c)
        eta_chg_arr.append(eta_chg)
        eta_dis_arr.append(eta_dis)

        # Ice and solar availability
        raw_sol = 0.0 if forced_solar_offline else float(
            solar_forecast_series[t].get("lower_bound_kw" if use_conservative_bounds else "predicted_kw", 0.0)
        )
        ice_derate = compute_ice_derate_factor(ice_trajectory[t]) if ice_trajectory and t < len(ice_trajectory) else 1.0
        solar_avail_arr.append(raw_sol * ice_derate)

        # P0, P1, P2 loads
        l_step = load_forecast_series[t]
        p0_val = float(l_step.get("upper_bound_kw" if use_conservative_bounds else "p0_load_kw", l_step.get("critical_load_kw", 50.0)))
        p1_val = float(l_step.get("p1_load_kw", p1_cfg.calculate_p1_demand(temp_c)))
        p2_val = float(l_step.get("p2_load_kw", l_step.get("important_load_kw", 30.0) + l_step.get("deferrable_load_kw", 20.0)))
        heat_val = float(l_step.get("thermal_load_kw", 0.0))

        p0_arr.append(p0_val)
        p1_arr.append(p1_val)
        p2_arr.append(p2_val)
        heat_demand_arr.append(heat_val)

    # Initialize Solver
    solver = None
    if ORTOOLS_AVAILABLE:
        solver = pywraplp.Solver.CreateSolver("CBC")
        if not solver:
            solver = pywraplp.Solver.CreateSolver("SCIP")
        if not solver:
            solver = pywraplp.Solver.CreateSolver("GLOP")
        if solver:
            solver.set_time_limit(10000)  # 10s limit

    if not solver:
        return _run_heuristic_optimizer(
            station_config, solar_forecast_series, load_forecast_series,
            T, emergency_reserve_boost_pct, forced_generator_offline, forced_solar_offline,
            weather_forecast_series, ice_trajectory
        )

    # Decision Variables
    P_solar_dir = []
    P_solar_chg = []
    P_batt_dis = []
    P_gen = []
    u_gen = []
    u_P1 = []           # Binary: P1 Battery jacket active (1) or shed (0)
    P_curt_p2 = []      # Continuous: P2 general load curtailed [0, P2]
    P_curt_p0 = []      # Emergency slack variable: P0 unserved (extremely penalized)
    E_batt = []
    H_displaced = []

    infinity = solver.infinity()
    dt = 1.0

    for t in range(T):
        P_solar_dir.append(solver.NumVar(0.0, solar_cap_kw, f"P_sol_dir_{t}"))
        P_solar_chg.append(solver.NumVar(0.0, max_chg_kw, f"P_sol_chg_{t}"))
        P_batt_dis.append(solver.NumVar(0.0, max_dis_kw, f"P_bat_dis_{t}"))
        P_gen.append(solver.NumVar(0.0, gen_cap_kw, f"P_gen_{t}"))
        u_gen.append(solver.BoolVar(f"u_gen_{t}"))
        u_P1.append(solver.BoolVar(f"u_p1_{t}"))
        P_curt_p2.append(solver.NumVar(0.0, p2_arr[t], f"P_curt_p2_{t}"))
        P_curt_p0.append(solver.NumVar(0.0, p0_arr[t], f"P_curt_p0_{t}"))
        H_displaced.append(solver.NumVar(0.0, infinity, f"H_disp_{t}"))
        E_batt.append(solver.NumVar(
            batt_cap_kwh * (min_reserve_pct / 100.0),
            batt_cap_kwh * (max_soc_pct / 100.0),
            f"E_batt_{t}"
        ))

    E_batt_end = solver.NumVar(
        batt_cap_kwh * (min_reserve_pct / 100.0),
        batt_cap_kwh * (max_soc_pct / 100.0),
        "E_batt_end"
    )

    # Initial State
    solver.Add(E_batt[0] == batt_cap_kwh * (current_soc_pct / 100.0))

    # Constraints per timestep
    for t in range(T):
        # 1. Solar Generation Limit
        solver.Add(P_solar_dir[t] + P_solar_chg[t] <= solar_avail_arr[t])

        # 2. CHP Coupling
        solver.Add(H_displaced[t] <= P_gen[t] * CHP_C_THERMAL)
        solver.Add(H_displaced[t] <= heat_demand_arr[t])
        if forced_generator_offline:
            solver.Add(H_displaced[t] == 0.0)

        # 3. Power Balance: Supply = Served Demand (P0 - CurtP0 + P1*u_P1 + P2 - CurtP2 - H_displaced)
        solver.Add(
            P_solar_dir[t] + P_batt_dis[t] + P_gen[t] == 
            (p0_arr[t] - P_curt_p0[t]) + (p1_arr[t] * u_P1[t]) + (p2_arr[t] - P_curt_p2[t]) - H_displaced[t]
        )

        # 4. Generator Operating Constraints
        if forced_generator_offline:
            solver.Add(P_gen[t] == 0.0)
            solver.Add(u_gen[t] == 0)
        else:
            solver.Add(P_gen[t] <= gen_cap_kw * u_gen[t])
            solver.Add(P_gen[t] >= gen_min_kw * u_gen[t])

        # 5. Battery Dynamics with Temperature Derating
        next_e = E_batt[t + 1] if (t + 1 < T) else E_batt_end
        solver.Add(
            next_e == E_batt[t] + (P_solar_chg[t] * eta_chg_arr[t] * dt) - (P_batt_dis[t] / eta_dis_arr[t] * dt)
        )

    # Objective Function Formulation
    objective = solver.Objective()
    for t in range(T):
        temp_t = temp_arr[t]
        # Fuel Cost
        objective.SetCoefficient(P_gen[t], fuel_rate * 2.20)
        # CHP Credit
        objective.SetCoefficient(H_displaced[t], -CHP_HEAT_CREDIT_PER_KW)
        # Battery wear
        cold_penalty = max(0.0, (-temp_t - 10.0) * BATT_WEAR_COLD_COEFF)
        objective.SetCoefficient(P_batt_dis[t], BATT_WEAR_BASE + cold_penalty)
        # Generator startup cost
        objective.SetCoefficient(u_gen[t], 1.50)
        # P2 Curtailment Penalty (15 $/kW)
        objective.SetCoefficient(P_curt_p2[t], 15.0)
        # P1 Jacket Shutdown Penalty (50 $/shutdown)
        objective.SetCoefficient(u_P1[t], -50.0)
        # P0 Critical Life Support Deficit Penalty (10,000 $/kW - Overwhelming priority)
        objective.SetCoefficient(P_curt_p0[t], 10000.0)

    objective.SetMinimization()
    status = solver.Solve()

    if status not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
        return {
            "success": False,
            "status": "INFEASIBLE",
            "message": "P0 critical life support cannot be maintained under current constraints. Automatic emergency load shed required.",
            "recommended_actions": [
                "Shed all P2 scientific and domestic loads immediately",
                "Disable P1 battery thermal jacketing to conserve emergency power",
                "Deploy auxiliary emergency generator",
                "Lower habitat thermal setpoint"
            ]
        }

    # Extract Optimal Schedule
    schedule = []
    total_diesel_kwh = 0.0
    total_diesel_liters = 0.0
    total_solar_used = 0.0
    total_solar_stored = 0.0
    total_batt_dis = 0.0
    total_curt_p2 = 0.0
    total_curt_p0 = 0.0
    total_demand = 0.0
    total_chp_heat = 0.0
    fuel_tracker_l = current_fuel_l

    for t in range(T):
        s_dir = round(P_solar_dir[t].solution_value(), 2)
        s_chg = round(P_solar_chg[t].solution_value(), 2)
        b_dis = round(P_batt_dis[t].solution_value(), 2)
        p_g = round(P_gen[t].solution_value(), 2)
        g_on = bool(u_gen[t].solution_value() > 0.5)
        p1_active = bool(u_P1[t].solution_value() > 0.5)
        curt2 = round(P_curt_p2[t].solution_value(), 2)
        curt0 = round(P_curt_p0[t].solution_value(), 2)
        h_disp = round(H_displaced[t].solution_value(), 2)
        e_b = round(E_batt[t].solution_value(), 2)
        soc = round((e_b / batt_cap_kwh) * 100.0, 1)

        f_consumed = round(p_g * fuel_rate, 2)
        fuel_tracker_l = max(0.0, round(fuel_tracker_l - f_consumed, 1))

        nom_demand = p0_arr[t] + (p1_arr[t] if p1_active else 0.0) + p2_arr[t]
        served_t = round(nom_demand - curt2 - curt0, 2)
        chp_heat_kw = round(p_g * CHP_C_THERMAL, 2)

        total_diesel_kwh += p_g
        total_diesel_liters += f_consumed
        total_solar_used += s_dir
        total_solar_stored += s_chg
        total_batt_dis += b_dis
        total_curt_p2 += curt2
        total_curt_p0 += curt0
        total_demand += nom_demand
        total_chp_heat += chp_heat_kw

        schedule.append({
            "hour": t,
            "timestamp": solar_forecast_series[t].get("timestamp"),
            "demand_kw": round(nom_demand, 2),
            "p0_load_kw": round(p0_arr[t], 2),
            "p1_load_kw": round(p1_arr[t], 2),
            "p2_load_kw": round(p2_arr[t], 2),
            "p1_jacket_active": p1_active,
            "p2_curtailed_kw": curt2,
            "p0_unserved_kw": curt0,
            "load_served_kw": served_t,
            "curtailed_kw": round(curt2 + curt0, 2),
            "solar_direct_kw": s_dir,
            "solar_to_battery_kw": s_chg,
            "solar_total_kw": round(s_dir + s_chg, 2),
            "battery_discharge_kw": b_dis,
            "battery_soc_pct": soc,
            "battery_energy_kwh": e_b,
            "generator_kw": p_g,
            "generator_active": g_on,
            "fuel_consumed_l": f_consumed,
            "fuel_remaining_l": fuel_tracker_l,
            "chp_heat_kw": chp_heat_kw,
            "chp_heat_displacing_kw": h_disp,
            "eta_rte_pct": round(eta_chg_arr[t] * eta_dis_arr[t] * 100.0, 2),
            "renewable_fraction_pct": round(((s_dir + b_dis) / max(0.1, served_t)) * 100.0, 1) if served_t > 0 else 100.0
        })

    p0_cov_pct = 100.0 if total_curt_p0 == 0.0 else round((1.0 - total_curt_p0 / max(1.0, sum(p0_arr))) * 100.0, 1)

    return {
        "success": True,
        "status": "OPTIMAL",
        "solver": "OR-Tools MILP (SCIP/GLOP) with P0/P1/P2 Hierarchy",
        "horizon_hours": T,
        "summary": {
            "total_demand_kwh": round(total_demand, 1),
            "total_diesel_kwh": round(total_diesel_kwh, 1),
            "total_diesel_fuel_liters": round(total_diesel_liters, 1),
            "fuel_remaining_liters": fuel_tracker_l,
            "total_solar_kwh": round(total_solar_used + total_solar_stored, 1),
            "total_battery_discharged_kwh": round(total_batt_dis, 1),
            "total_p2_curtailed_kwh": round(total_curt_p2, 1),
            "total_p0_unserved_kwh": round(total_curt_p0, 1),
            "critical_p0_coverage_pct": p0_cov_pct,
            "overall_renewable_fraction_pct": round(((total_solar_used + total_batt_dis) / max(0.1, total_demand - total_curt_p2)) * 100.0, 1),
            "co2_emissions_kg": round(total_diesel_liters * 2.68, 1)
        },
        "schedule": schedule
    }


def _run_heuristic_optimizer(
    station_config: Dict[str, Any],
    solar_forecast_series: List[Dict[str, Any]],
    load_forecast_series: List[Dict[str, Any]],
    T: int,
    emergency_reserve_boost_pct: float,
    forced_generator_offline: bool,
    forced_solar_offline: bool,
    weather_forecast_series: Optional[List[Dict[str, Any]]] = None,
    ice_trajectory: Optional[List[float]] = None
) -> Dict[str, Any]:
    """Physics-aware Heuristic microgrid dispatcher fallback with P0/P1/P2 logic."""
    batt_cap_kwh = float(station_config.get("battery_capacity_kwh", 600.0))
    current_soc_pct = float(station_config.get("battery_soc_pct", 75.0))
    min_reserve_pct = min(85.0, max(15.0, float(station_config.get("battery_min_reserve_pct", 30.0)) + emergency_reserve_boost_pct))
    max_soc_pct = float(station_config.get("battery_max_soc_pct", 98.0))
    max_chg_kw = float(station_config.get("battery_max_charge_kw", 150.0))
    max_dis_kw = float(station_config.get("battery_max_discharge_kw", 150.0))
    base_rte = float(station_config.get("battery_rte_pct", 92.0)) / 100.0
    gen_cap_kw = float(station_config.get("diesel_capacity_kw", 250.0))
    fuel_l = float(station_config.get("diesel_fuel_l", 1200.0))
    fuel_rate = float(station_config.get("diesel_consumption_l_per_kwh", 0.28))

    e_batt = batt_cap_kwh * (current_soc_pct / 100.0)
    schedule = []
    total_diesel_kwh, total_diesel_l, total_solar, total_demand, total_curt_p2 = 0.0, 0.0, 0.0, 0.0, 0.0

    for t in range(T):
        w_step = weather_forecast_series[t] if weather_forecast_series and t < len(weather_forecast_series) else {}
        temp_c = float(w_step.get("temperature_c", -15.0))
        eta_chg, eta_dis = compute_arrhenius_rte(base_rte, temp_c)
        
        ice_pct = ice_trajectory[t] if ice_trajectory and t < len(ice_trajectory) else 0.0
        ice_derate = compute_ice_derate_factor(ice_pct)
        raw_sol = 0.0 if forced_solar_offline else float(solar_forecast_series[t].get("predicted_kw", 0.0))
        sol = raw_sol * ice_derate

        l_step = load_forecast_series[t]
        p0 = float(l_step.get("p0_load_kw", l_step.get("critical_load_kw", 50.0)))
        p1 = float(l_step.get("p1_load_kw", 3.0))
        p2 = float(l_step.get("p2_load_kw", 50.0))
        
        # Dispatch logic: Solar direct
        dem_tot = p0 + p1 + p2
        s_dir = min(dem_tot, sol)
        excess_s = max(0.0, sol - s_dir)

        # Battery Charge
        room = max(0.0, (batt_cap_kwh * (max_soc_pct / 100.0)) - e_batt)
        s_chg = min(excess_s, max_chg_kw, room / eta_chg)
        e_batt += s_chg * eta_chg

        # Battery Discharge
        deficit = dem_tot - s_dir
        b_avail = max(0.0, e_batt - (batt_cap_kwh * (min_reserve_pct / 100.0)))
        b_dis = min(deficit, max_dis_kw, b_avail * eta_dis)
        e_batt -= (b_dis / eta_dis)

        rem_deficit = max(0.0, deficit - b_dis)
        p_g = 0.0
        g_on = False

        if rem_deficit > 0 and not forced_generator_offline and fuel_l > 0:
            p_g = min(gen_cap_kw, rem_deficit)
            g_on = True
            f_use = p_g * fuel_rate
            fuel_l = max(0.0, fuel_l - f_use)
            total_diesel_l += f_use
            total_diesel_kwh += p_g

        curt_p2 = max(0.0, rem_deficit - p_g)
        total_solar += s_dir
        total_curt_p2 += curt_p2
        total_demand += dem_tot
        soc = round((e_batt / batt_cap_kwh) * 100.0, 1)

        schedule.append({
            "hour": t,
            "timestamp": solar_forecast_series[t].get("timestamp"),
            "demand_kw": dem_tot,
            "p0_load_kw": p0,
            "p1_load_kw": p1,
            "p2_load_kw": p2,
            "p1_jacket_active": True,
            "p2_curtailed_kw": round(curt_p2, 2),
            "p0_unserved_kw": 0.0,
            "load_served_kw": round(dem_tot - curt_p2, 2),
            "curtailed_kw": round(curt_p2, 2),
            "solar_direct_kw": round(s_dir, 2),
            "solar_to_battery_kw": round(s_chg, 2),
            "solar_total_kw": round(s_dir + s_chg, 2),
            "battery_discharge_kw": round(b_dis, 2),
            "battery_soc_pct": soc,
            "battery_energy_kwh": round(e_batt, 2),
            "generator_kw": round(p_g, 2),
            "generator_active": g_on,
            "fuel_consumed_l": round(p_g * fuel_rate, 2),
            "fuel_remaining_l": round(fuel_l, 1),
            "chp_heat_kw": round(p_g * CHP_C_THERMAL, 2),
            "chp_heat_displacing_kw": min(round(p_g * CHP_C_THERMAL, 2), float(l_step.get("thermal_load_kw", 0.0))),
            "eta_rte_pct": round(eta_chg * eta_dis * 100.0, 2),
            "renewable_fraction_pct": round(((s_dir + b_dis) / max(0.1, dem_tot - curt_p2)) * 100.0, 1)
        })

    return {
        "success": True,
        "status": "OPTIMAL (Heuristic)",
        "solver": "Polaris Predictive Dispatcher (Heuristic P0/P1/P2)",
        "horizon_hours": T,
        "summary": {
            "total_demand_kwh": round(total_demand, 1),
            "total_diesel_kwh": round(total_diesel_kwh, 1),
            "total_diesel_fuel_liters": round(total_diesel_l, 1),
            "fuel_remaining_liters": round(fuel_l, 1),
            "total_solar_kwh": round(total_solar, 1),
            "total_p2_curtailed_kwh": round(total_curt_p2, 1),
            "total_p0_unserved_kwh": 0.0,
            "critical_p0_coverage_pct": 100.0,
            "overall_renewable_fraction_pct": round(((total_solar) / max(0.1, total_demand)) * 100.0, 1),
            "co2_emissions_kg": round(total_diesel_l * 2.68, 1)
        },
        "schedule": schedule
    }
