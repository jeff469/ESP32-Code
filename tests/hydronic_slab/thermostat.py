"""Simple thermostat control for the heater and mixing solenoids."""
import time

from tests.hydronic_slab.actuators import (
    solA_close,
    solA_open,
    solB_close,
    solB_open,
)
from tests.hydronic_slab.state import set_heater_state
from tests.hydronic_slab.sensors.mega import request_water_temp_C

# Track the last mode to avoid spamming relay commands on every sample.
_last_mode = None
_last_change_ts = 0.0


def _apply_mode(mode):
    global _last_mode, _last_change_ts

    if mode == _last_mode:
        return

    if mode == "heating":
        solA_close()
        solB_open()
        set_heater_state(True)
    elif mode == "cooling":
        solB_close()
        solA_open()
        set_heater_state(False)
    elif mode == "idle":
        solA_close()
        solB_close()
        set_heater_state(False)
    else:
        return

    _last_mode = mode
    _last_change_ts = time.time()
    print("Thermostat mode ->", mode)


def regulate_water_temp(setpoint_C, deadband_C=1.0):
    """Maintain water temperature using heater and solenoid mix valves.

    Heater ON + solenoid B OPEN when below (setpoint - deadband).
    Heater OFF + solenoid A OPEN when above (setpoint + deadband).
    Within the deadband, keep the previous mode to reduce chatter.
    """

    temp = request_water_temp_C()
    if temp is None:
        print("Thermostat: water temp unavailable; keeping previous mode")
        return None

    lower = setpoint_C - deadband_C
    upper = setpoint_C + deadband_C

    print(
        "Thermostat reading:",
        temp,
        "°C (setpoint =",
        setpoint_C,
        "deadband ±",
        deadband_C,
        ")",
    )

    if temp < lower:
        _apply_mode("heating")
    elif temp > upper:
        _apply_mode("cooling")
    else:
        _apply_mode("idle")

    return temp
