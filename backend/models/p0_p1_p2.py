"""
POLARIS P0 / P1 / P2 Emergency Power Abstraction & Reallocation Model

Formal Hierarchy:
  P0 = Critical Life-Support-Only Demand (life support, habitat survival heating, critical satcom, scrubbers).
       Highest mathematical priority; CANNOT be curtailed unless physically impossible.
  P1 = Battery Thermal-Jacketing Electrical Demand (configurable heating blankets/immersion heaters in kW).
       Protects battery bank against sub-zero lithium plating and internal resistance surge.
       Can be deactivated (u_P1 = 0) in emergency mode to reallocate electrical demand to sustain P0.
  P2 = General / Non-Critical Station Consumption (scientific computing, auxiliary lighting, EV/skidoo charging, domestic hot water).
       First to be shed or heavily curtailed (u_P2 = 0) during warning or blackout risks.

Mathematical Reallocation:
  u_P1(t) in {0, 1} : Battery jacket control binary
  u_P2(t) in {0, 1} : General load control binary (or continuous [0, 1] curtailment factor)
  released_P1(t) = (1 - u_P1(t)) * P1_nominal(t)
  released_P2(t) = (1 - u_P2(t)) * P2_nominal(t)
  P_available(t) = P_solar(t) + P_battery(t) + P_generator(t) + released_P1(t) + released_P2(t)
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple


@dataclass
class P1Config:
    """Configuration for P1 Battery Thermal-Jacketing Subsystem."""
    nominal_jacket_power_kw: float = 3.0       # Configurable nominal jacket power in kW
    min_battery_temp_c: float = -20.0          # Minimum battery temperature before severe derating
    activation_threshold_c: float = -10.0      # Ambient/battery temp below which jacket activates
    emergency_shutdown_threshold_c: float = -5.0 # Max temp where jacket can be safely shed in emergency
    thermal_protection_mode: str = "auto"      # "auto", "forced_on", "forced_off", "emergency_shed"

    def calculate_p1_demand(self, ambient_temp_c: float, battery_temp_c: Optional[float] = None) -> float:
        """
        Calculates electrical power demand for battery thermal jacketing (kW).
        Increases as temperature drops below activation threshold.
        """
        if self.thermal_protection_mode == "forced_off":
            return 0.0
        if self.thermal_protection_mode == "forced_on":
            return self.nominal_jacket_power_kw

        temp = battery_temp_c if battery_temp_c is not None else ambient_temp_c
        if temp >= self.activation_threshold_c:
            return 0.0

        # Demand scales with delta-T below threshold, capped at 1.5x nominal
        delta_t = self.activation_threshold_c - temp
        scale = min(1.5, 1.0 + (delta_t / 20.0) * 0.5)
        return round(self.nominal_jacket_power_kw * scale, 2)


@dataclass
class P0P1P2Breakdown:
    """Detailed categorization of station electrical loads."""
    p0_critical_kw: float
    p1_battery_jacket_kw: float
    p2_general_kw: float
    total_nominal_kw: float
    p0_items: List[Dict[str, Any]] = field(default_factory=list)
    p1_items: List[Dict[str, Any]] = field(default_factory=list)
    p2_items: List[Dict[str, Any]] = field(default_factory=list)


def categorize_loads(
    loads: List[Dict[str, Any]],
    ambient_temp_c: float,
    p1_cfg: Optional[P1Config] = None,
    battery_temp_c: Optional[float] = None,
    heating_intensity: float = 1.0,
    research_intensity: float = 1.0,
) -> P0P1P2Breakdown:
    """
    Categorizes station loads into P0 (Life-support/Critical), P1 (Battery Jacket), and P2 (General).
    Preserves backward compatibility with CRITICAL, IMPORTANT, and DEFERRABLE priority classifications.
    """
    cfg = p1_cfg or P1Config()
    p0_kw = 0.0
    p2_kw = 0.0
    p0_items = []
    p2_items = []

    # Indoor thermal delta-T
    delta_t = max(0.0, 20.0 - ambient_temp_c)
    thermal_mult = (1.0 + (delta_t / 35.0) * 0.45) * heating_intensity

    for item in loads:
        p_id = item.get("id", "").lower()
        base_p = float(item.get("power_kw", item.get("current_kw", 10.0)))
        priority = item.get("priority", "IMPORTANT").upper()

        is_heating = "heat" in p_id or "thermal" in p_id
        is_life_support = "life" in p_id or "satcom" in p_id or "water_purif" in p_id or "comms" in p_id or "air" in p_id

        if is_heating:
            actual_kw = round(base_p * thermal_mult, 2)
        elif "lab" in p_id or "research" in p_id or "atmos" in p_id or "computing" in p_id:
            actual_kw = round(base_p * research_intensity, 2)
        else:
            actual_kw = round(base_p, 2)

        # Mapping rule: CRITICAL or life support -> P0
        if priority == "CRITICAL" or is_life_support or (is_heating and priority != "DEFERRABLE"):
            p0_kw += actual_kw
            p0_items.append({**item, "effective_kw": actual_kw, "category": "P0"})
        else:
            # IMPORTANT + DEFERRABLE -> P2
            p2_kw += actual_kw
            p2_items.append({**item, "effective_kw": actual_kw, "category": "P2"})

    # P1 is computed from P1Config
    p1_kw = cfg.calculate_p1_demand(ambient_temp_c, battery_temp_c)
    p1_items = [{
        "id": "battery_thermal_jacket_p1",
        "name": "Battery Thermal Jacketing (P1)",
        "nominal_kw": cfg.nominal_jacket_power_kw,
        "effective_kw": p1_kw,
        "priority": "P1_THERMAL_PROTECTION",
        "category": "P1"
    }]

    total_nominal = round(p0_kw + p1_kw + p2_kw, 2)
    return P0P1P2Breakdown(
        p0_critical_kw=round(p0_kw, 2),
        p1_battery_jacket_kw=round(p1_kw, 2),
        p2_general_kw=round(p2_kw, 2),
        total_nominal_kw=total_nominal,
        p0_items=p0_items,
        p1_items=p1_items,
        p2_items=p2_items
    )


def reallocate_emergency_power(
    p0_kw: float,
    p1_kw: float,
    p2_kw: float,
    available_generation_kw: float,
    operating_mode: str = "NORMAL"
) -> Tuple[float, float, float, int, int]:
    """
    Calculates actual dispatched power for P0, P1, P2 under generation constraints.
    
    Returns:
        (served_p0_kw, served_p1_kw, served_p2_kw, u_p1, u_p2)
    """
    avail = available_generation_kw
    
    if operating_mode == "EMERGENCY":
        # P2 shed completely
        u_p2 = 0
        served_p2 = 0.0
        
        # Check if generation can sustain P0 + P1
        if avail >= (p0_kw + p1_kw):
            u_p1 = 1
            served_p1 = p1_kw
            served_p0 = p0_kw
        elif avail >= p0_kw:
            # Shed P1 to guarantee P0
            u_p1 = 0
            served_p1 = 0.0
            served_p0 = p0_kw
        else:
            # Extreme deficit: all available power given to P0
            u_p1 = 0
            served_p1 = 0.0
            served_p0 = min(p0_kw, avail)
            
    elif operating_mode == "WARNING":
        # Curtail P2 if necessary, keep P1 active
        if avail >= (p0_kw + p1_kw + p2_kw):
            u_p1, u_p2 = 1, 1
            served_p0, served_p1, served_p2 = p0_kw, p1_kw, p2_kw
        else:
            u_p1 = 1
            served_p0 = p0_kw
            served_p1 = p1_kw
            served_p2 = max(0.0, avail - (p0_kw + p1_kw))
            u_p2 = 1 if served_p2 > (0.2 * p2_kw) else 0
    else: # NORMAL
        u_p1 = 1 if p1_kw > 0 else 1
        u_p2 = 1
        served_p0 = min(p0_kw, avail)
        rem = max(0.0, avail - served_p0)
        served_p1 = min(p1_kw, rem)
        rem = max(0.0, rem - served_p1)
        served_p2 = min(p2_kw, rem)

    return (round(served_p0, 2), round(served_p1, 2), round(served_p2, 2), u_p1, u_p2)
