"""
Unit tests for POLARIS Polar Physics and P0/P1/P2 Load Models
"""

import pytest
from backend.services.solar_service import calculate_solar_output
from backend.services.load_service import calculate_station_load
from backend.physics.polar_physics import compute_arrhenius_rte, compute_ice_derate_factor, CHP_C_THERMAL
from backend.models.p0_p1_p2 import P1Config, categorize_loads, reallocate_emergency_power
from backend.data.station_presets import POLAR_STATIONS


def test_arrhenius_battery_derating():
    # At standard -10°C, RTE should equal baseline 0.92
    eta_chg_norm, eta_dis_norm = compute_arrhenius_rte(0.92, -10.0)
    assert round(eta_chg_norm * eta_dis_norm, 2) == 0.92

    # At -30°C, internal resistance increases -> RTE decays exponentially
    eta_chg_cold, eta_dis_cold = compute_arrhenius_rte(0.92, -30.0)
    rte_cold = eta_chg_cold * eta_dis_cold
    assert rte_cold < 0.92
    assert rte_cold >= 0.60 # Above physical floor


def test_p1_battery_thermal_jacket_scaling():
    cfg = P1Config(nominal_jacket_power_kw=3.0, activation_threshold_c=-10.0)
    
    # Warm weather: jacket off
    assert cfg.calculate_p1_demand(0.0) == 0.0
    assert cfg.calculate_p1_demand(-5.0) == 0.0

    # Cold weather: jacket turns on and scales with delta-T
    p1_cold = cfg.calculate_p1_demand(-25.0)
    assert p1_cold >= 3.0
    assert p1_cold <= 4.5 # Capped at 1.5x nominal


def test_p0_p1_p2_emergency_reallocation():
    # Scenario: 100 kW generation available, demand is P0=60kW, P1=5kW, P2=50kW (Total 115kW)
    # Under EMERGENCY mode, P2 is shed (0 kW), P1 is kept (5 kW), P0 is served (60 kW)
    served_p0, served_p1, served_p2, u_p1, u_p2 = reallocate_emergency_power(
        p0_kw=60.0, p1_kw=5.0, p2_kw=50.0, available_generation_kw=100.0, operating_mode="EMERGENCY"
    )
    assert served_p0 == 60.0
    assert served_p1 == 5.0
    assert served_p2 == 0.0
    assert u_p2 == 0
    assert u_p1 == 1

    # Extreme Deficit Scenario: only 50 kW available for P0=60kW, P1=5kW, P2=50kW
    # Both P2 and P1 are shed so all 50 kW is dedicated to P0
    served_p0, served_p1, served_p2, u_p1, u_p2 = reallocate_emergency_power(
        p0_kw=60.0, p1_kw=5.0, p2_kw=50.0, available_generation_kw=50.0, operating_mode="EMERGENCY"
    )
    assert served_p0 == 50.0
    assert served_p1 == 0.0
    assert served_p2 == 0.0
    assert u_p1 == 0
    assert u_p2 == 0
