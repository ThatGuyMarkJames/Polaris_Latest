"""
POLARIS Synthetic Telemetry Engine (Pipeline B)
Generates physically consistent, causally coupled station sensor telemetry.
Incorporates realistic sensor imperfections (Gaussian noise, drift, missing values, flat-lining, calibration bias).
All records are explicitly labeled with source_type='synthetic'.
"""

import math
import random
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from backend.services.data_validator import validate_and_flag_telemetry
from backend.models.p0_p1_p2 import P1Config
from backend.database.db import get_db_connection, insert_energy_telemetry


class SyntheticSensorEngine:
    """
    Simulates real-world polar research station sensors with integrated physical kinetics
    and configurable instrumentation imperfections.
    """
    def __init__(
        self,
        station_id: str,
        station_config: Optional[Dict[str, Any]] = None,
        imperfection_config: Optional[Dict[str, Any]] = None,
        seed: Optional[int] = 42
    ):
        self.station_id = station_id
        self.rng = np.random.RandomState(seed)
        self.seed = seed
        
        # Station equipment specs
        cfg = station_config or {}
        self.solar_capacity_kw = float(cfg.get("solar_capacity_kw", cfg.get("default_solar_kw", 180.0)))
        self.solar_eff = float(cfg.get("solar_efficiency_pct", cfg.get("default_solar_efficiency_pct", 21.5)))
        self.battery_capacity_kwh = float(cfg.get("battery_capacity_kwh", cfg.get("default_battery_kwh", 600.0)))
        self.battery_max_chg_kw = float(cfg.get("battery_max_charge_kw", cfg.get("default_battery_max_charge_kw", 150.0)))
        self.battery_max_dis_kw = float(cfg.get("battery_max_discharge_kw", cfg.get("default_battery_max_discharge_kw", 150.0)))
        self.diesel_capacity_kw = float(cfg.get("diesel_capacity_kw", cfg.get("default_diesel_kw", 250.0)))
        self.diesel_consumption_rate = float(cfg.get("diesel_consumption_l_per_kwh", cfg.get("default_diesel_consumption_l_per_kwh", 0.28)))
        self.occupants = int(cfg.get("occupants", cfg.get("default_occupants", 24)))
        
        p1_data = cfg.get("p1_config", cfg.get("default_p1_config", {}))
        self.p1_cfg = P1Config(**p1_data) if p1_data else P1Config()

        # State Variables (integrated dynamically over time)
        self.current_soc_pct = float(cfg.get("battery_soc_pct", cfg.get("default_battery_soc_pct", 75.0)))
        self.current_soh_pct = float(cfg.get("battery_health_pct", cfg.get("default_battery_health_pct", 98.0)))
        self.battery_temperature_c = 15.0
        self.fuel_remaining_l = float(cfg.get("diesel_fuel_l", cfg.get("default_diesel_fuel_l", 1200.0)))
        self.indoor_temperature_c = 20.0
        
        # Sensor Imperfection Configuration
        self.imperfections = imperfection_config or {
            "noise_std_dev": 1.2,          # Gaussian measurement noise
            "missing_data_prob": 0.015,     # 1.5% sensor dropout rate
            "drift_rate": 0.03,            # Random walk drift rate
            "outlier_prob": 0.005,         # 0.5% outlier spike rate
            "flatline_prob": 0.002,        # 0.2% probability of sensor flatlining
            "bias_pv": 0.0,
            "bias_soc": 0.0
        }
        
        self.drift_accumulators = {
            "pv": 0.0,
            "p0": 0.0,
            "p1": 0.0,
            "p2": 0.0,
            "soc": 0.0,
            "temp": 0.0
        }
        self.flatline_states = {}

    def _apply_sensor_noise(self, field: str, true_value: float) -> Optional[float]:
        """Applies realistic physical instrumentation noise, drift, and dropouts."""
        if true_value is None:
            return None
            
        # 1. Missing data dropout
        if self.rng.rand() < self.imperfections.get("missing_data_prob", 0.01):
            return None
            
        # 2. Sensor Flat-lining
        if self.rng.rand() < self.imperfections.get("flatline_prob", 0.002):
            if field not in self.flatline_states:
                self.flatline_states[field] = true_value
            return round(self.flatline_states[field], 2)
        else:
            self.flatline_states.pop(field, None)

        # 3. Sensor Drift (random walk)
        drift_delta = float(self.rng.normal(0, self.imperfections.get("drift_rate", 0.03)))
        self.drift_accumulators[field] = self.drift_accumulators.get(field, 0.0) + drift_delta
        
        # 4. Gaussian Measurement Noise
        noise = float(self.rng.normal(0, self.imperfections.get("noise_std_dev", 1.2)))
        
        # 5. Outlier Spike
        outlier = 0.0
        if self.rng.rand() < self.imperfections.get("outlier_prob", 0.005):
            outlier = float(self.rng.choice([-1, 1]) * self.rng.uniform(15.0, 35.0))
            
        measured = true_value + self.drift_accumulators[field] + noise + outlier
        return round(measured, 2)

    def generate_step(
        self,
        weather_data: Dict[str, Any],
        scenario_modifiers: Optional[Dict[str, Any]] = None,
        persist: bool = True
    ) -> Dict[str, Any]:
        """
        Generates 1 hour timestep of telemetry causally coupled with environmental state.
        """
        mods = scenario_modifiers or {}
        temp = float(weather_data.get("temperature_c", -15.0)) + float(mods.get("temp_offset_c", 0.0))
        wind = float(weather_data.get("wind_speed_kmh", 25.0)) * float(mods.get("wind_multiplier", 1.0))
        irradiance = float(weather_data.get("solar_irradiance_wm2", weather_data.get("global_tilted_irradiance_wm2", 0.0)))
        irradiance = irradiance * float(mods.get("solar_multiplier", 1.0)) if mods.get("solar_available", True) else 0.0
        is_day = bool(weather_data.get("is_day", irradiance > 2.0))
        
        # --- 1. PHYSICAL PV GENERATION ---
        # Cell temperature gain: +0.4% per degree below 25°C
        temp_gain = 1.0 + (25.0 - temp) * 0.004
        temp_gain = max(0.85, min(1.25, temp_gain))
        snow_loss = 0.90 if weather_data.get("snowfall_cm", 0.0) > 0.5 else 1.0
        raw_pv = self.solar_capacity_kw * (irradiance / 1000.0) * temp_gain * snow_loss * 0.94
        true_pv = round(max(0.0, min(self.solar_capacity_kw * 1.15, raw_pv)), 2)
        if not mods.get("solar_available", True):
            true_pv = 0.0

        # --- 2. PHYSICAL LOAD MODELS (P0, P1, P2) ---
        # P0: Critical Life Support + Habitat Survival Heating
        delta_t_env = max(0.0, 20.0 - temp)
        wind_chill = 1.0 + (wind / 100.0) * 0.15
        p0_heating = (35.0 + (delta_t_env / 35.0) * 20.0) * wind_chill
        p0_life_support = 22.0 + (self.occupants * 0.3)
        true_p0 = round((p0_heating + p0_life_support) * float(mods.get("demand_multiplier", 1.0)), 2)

        # P1: Battery Thermal Jacketing
        true_p1 = self.p1_cfg.calculate_p1_demand(temp, self.battery_temperature_c)

        # P2: General / Science / Deferrable
        hour = datetime.fromisoformat(weather_data.get("timestamp", datetime.now(timezone.utc).isoformat()).replace("Z", "+00:00")).hour if "T" in str(weather_data.get("timestamp", "")) else 12
        is_active = 7 <= hour <= 22
        occupant_p2 = (self.occupants * 0.4) if is_active else (self.occupants * 0.15)
        science_p2 = 35.0 * float(mods.get("demand_multiplier", 1.0))
        true_p2 = round(occupant_p2 + science_p2 + 15.0, 2)
        
        true_total_load = round(true_p0 + true_p1 + true_p2, 2)

        # --- 3. BATTERY DISPATCH & STATE INTEGRATION ---
        net_power = true_pv - true_total_load
        dt = 1.0 # 1 hour
        
        # Generator activation rules
        gen_available = mods.get("generator_available", True)
        true_gen_kw = 0.0
        true_gen_status = "OFF"
        
        if self.current_soc_pct < 30.0 and gen_available and self.fuel_remaining_l > 0:
            true_gen_status = "ON"
            true_gen_kw = min(self.diesel_capacity_kw, max(60.0, true_total_load - true_pv + 50.0))
            fuel_burned = true_gen_kw * self.diesel_consumption_rate * dt
            self.fuel_remaining_l = max(0.0, round(self.fuel_remaining_l - fuel_burned, 2))
            net_power += true_gen_kw

        # Battery kinetics: Arrhenius RTE derating
        eta_rte = 0.92 if temp > -10.0 else max(0.65, 0.92 * math.exp(0.025 * (temp + 10.0)))
        eta_one_way = math.sqrt(eta_rte)

        if net_power > 0: # Charging
            chg_kw = min(net_power, self.battery_max_chg_kw)
            energy_delta = chg_kw * eta_one_way * dt
            self.current_soc_pct = min(98.0, self.current_soc_pct + (energy_delta / self.battery_capacity_kwh) * 100.0)
            batt_power = -chg_kw # negative indicates charging
        else: # Discharging
            dis_kw = min(abs(net_power), self.battery_max_dis_kw)
            energy_delta = (dis_kw / eta_one_way) * dt
            self.current_soc_pct = max(10.0, self.current_soc_pct - (energy_delta / self.battery_capacity_kwh) * 100.0)
            batt_power = dis_kw

        # Battery thermal model: ambient heat loss vs internal self-heating
        i_sq_r_heat = (batt_power / 400.0) ** 2 * 0.05 * 0.001
        jacket_heat = true_p1 * 0.8
        temp_loss_to_ambient = (self.battery_temperature_c - temp) * 0.08
        self.battery_temperature_c = round(self.battery_temperature_c + (jacket_heat + i_sq_r_heat - temp_loss_to_ambient) * 0.5, 1)

        # --- 4. SENSOR MEASUREMENTS & IMPERFECTIONS ---
        timestamp_str = weather_data.get("timestamp", datetime.now(timezone.utc).isoformat())
        
        measured = {
            "timestamp": timestamp_str,
            "station_id": self.station_id,
            "pv_power_kw": self._apply_sensor_noise("pv", true_pv),
            "p0_load_kw": self._apply_sensor_noise("p0", true_p0),
            "p1_load_kw": self._apply_sensor_noise("p1", true_p1),
            "p2_load_kw": self._apply_sensor_noise("p2", true_p2),
            "total_load_kw": self._apply_sensor_noise("total_load", true_total_load),
            "battery_soc_pct": self._apply_sensor_noise("soc", round(self.current_soc_pct, 1)),
            "battery_soh_pct": round(self.current_soh_pct, 1),
            "battery_power_kw": round(batt_power, 2),
            "battery_voltage_v": round(380.0 + (self.current_soc_pct / 100.0) * 45.0, 1),
            "battery_current_a": round((batt_power * 1000.0) / 400.0, 1),
            "battery_temperature_c": self._apply_sensor_noise("temp", self.battery_temperature_c),
            "generator_power_kw": round(true_gen_kw, 2),
            "generator_status": true_gen_status,
            "fuel_remaining_l": round(self.fuel_remaining_l, 1),
            "occupancy": self.occupants,
            "indoor_temperature_c": round(self.indoor_temperature_c, 1),
            "source_type": "synthetic",
            "source_id": f"sim-{mods.get('scenario_id', 'standard')}",
        }

        # --- 5. VALIDATION & QUALITY ASSURANCE ---
        validated = validate_and_flag_telemetry(
            station_id=self.station_id,
            telemetry=measured,
            max_generator_kw=self.diesel_capacity_kw,
            max_solar_kw=self.solar_capacity_kw,
            is_day=is_day,
            irradiance_wm2=irradiance
        )

        # --- 6. DATABASE PERSISTENCE ---
        if persist:
            try:
                insert_energy_telemetry(self.station_id, validated)
            except Exception as e:
                print(f"Failed to persist synthetic telemetry: {e}")

        return validated

    def generate_timeline(
        self,
        weather_forecast: List[Dict[str, Any]],
        scenario_modifiers: Optional[Dict[str, Any]] = None,
        persist: bool = True
    ) -> List[Dict[str, Any]]:
        """Generates multi-hour trajectory of synthetic sensor data."""
        timeline = []
        for step in weather_forecast:
            record = self.generate_step(step, scenario_modifiers, persist=persist)
            timeline.append(record)
        return timeline
