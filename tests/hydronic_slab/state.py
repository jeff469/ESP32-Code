"""Shared state, binning, and energy tracking helpers."""
import os
import time
import ujson
import machine
from machine import Pin

from tests.hydronic_slab.actuators import heater_off, heater_on, pump_off, pump_on
from tests.hydronic_slab.sensors.mega import request_water_temp_C

SNOW_PRESENT_THRESHOLD = 5.0
SNOW_CLEAR_THRESHOLD = 1.0
SNOW_DEPTH_BINS = [0, 5, 20, 50, 100, 200, 400]
MAX_ANGLE_DEG = 40
ANGLE_BINS = [0, 10, 20, 30, 40]

ANGLE_TOLERANCE = 0.5
NON_TILTED_ANGLE_DEG = 5.0

# Environment bin counts (per variable)
AIR_TEMP_BINS = 6
HUMIDITY_BINS = 4
WIND_SPEED_BINS = 6
WIND_DIR_BINS = 6
N_BINS_ENV = 10
AIR_TEMP_MIN = -30.0
AIR_TEMP_MAX = 10.0
HUMIDITY_MIN = 0.0
HUMIDITY_MAX = 100.0
WIND_SPEED_MIN = 0.0
WIND_SPEED_MAX = 20.0
WIND_DIR_MIN = 0.0
WIND_DIR_MAX = 360.0

BASE_WATER_TEMP_C = 30.0
BASE_FLOW_LEVEL = 0.7

combo_counts = {}
daily_test_counts = {}
last_angle_deg = None

PUMP_PWM_PIN = 25
pump_pwm = machine.PWM(Pin(PUMP_PWM_PIN), freq=1000)
pump_pwm.duty(0)

PUMP_POWER_W = 100.0
HEATER_POWER_W = 600.0

pump_energy_Wh_total = 0.0
heater_energy_Wh_total = 0.0
pump_is_on = False
heater_is_on = False
_last_energy_update_time = time.time()

current_water_setpoint = 0.0

STATE_FILE = "test_state.json"
LOG_DIR = "/logs"
LOG_FILE = LOG_DIR + "/test_log.csv"


def set_flow_level(flow_level):
    """Set pump flow level (0..1) using PWM on the ESP32."""
    if flow_level < 0.0:
        flow_level = 0.0
    if flow_level > 1.0:
        flow_level = 1.0

    duty = int(flow_level * 1023)
    pump_pwm.duty(duty)
    print("Set flow PWM level =", flow_level, "(duty =", duty, ")")


def _update_energy_counters():
    global pump_energy_Wh_total, heater_energy_Wh_total, _last_energy_update_time
    now = time.time()
    dt_s = now - _last_energy_update_time
    if dt_s < 0:
        dt_s = 0
    dt_h = dt_s / 3600.0
    if pump_is_on:
        pump_energy_Wh_total += PUMP_POWER_W * dt_h
    if heater_is_on:
        heater_energy_Wh_total += HEATER_POWER_W * dt_h
    _last_energy_update_time = now


def set_pump_state(on):
    global pump_is_on
    _update_energy_counters()
    if on:
        pump_on()
        pump_is_on = True
        print("PUMP STATE -> ON")
    else:
        pump_off()
        pump_is_on = False
        print("PUMP STATE -> OFF")


def set_heater_state(on):
    global heater_is_on
    _update_energy_counters()
    if on:
        heater_on()
        heater_is_on = True
    else:
        heater_off()
        heater_is_on = False


def get_energy_totals_Wh():
    _update_energy_counters()
    return pump_energy_Wh_total, heater_energy_Wh_total


def ensure_supply_hot(target_temp_C, timeout_s=900):
    """Preheat the water loop to at least ``target_temp_C``."""
    global current_water_setpoint
    current_water_setpoint = target_temp_C
    print("Preheat: target supply temp =", target_temp_C)
    start = time.time()
    set_heater_state(True)
    while True:
        temp = request_water_temp_C()
        now = time.time()
        if temp is not None:
            print("  Water temp =", temp, "°C")
            if temp >= target_temp_C:
                print("Preheat done.")
                break
        else:
            print("  Water temp read failed; continuing...")
        if now - start > timeout_s:
            print("Preheat timeout reached.")
            break
        time.sleep(5)
    set_heater_state(False)


def is_snow_present(snow_depth_mm):
    present = snow_depth_mm >= SNOW_PRESENT_THRESHOLD
    print(
        "Decision -> snow present?",
        present,
        "(depth =", snow_depth_mm,
        "threshold =",
        SNOW_PRESENT_THRESHOLD,
        ")",
    )
    return present


def init_tilt_coverage():
    global tilt_coverage
    n_snow = len(SNOW_DEPTH_BINS) - 1
    n_angle = len(ANGLE_BINS)
    tilt_coverage = [[False for _ in range(n_angle)] for _ in range(n_snow)]


def load_state():
    global tilt_coverage, combo_counts, daily_test_counts, last_angle_deg
    init_tilt_coverage()
    combo_counts = {}
    daily_test_counts = {}
    last_angle_deg = None
    try:
        if STATE_FILE not in os.listdir():
            print("No state file found; starting with fresh coverage.")
            return
        with open(STATE_FILE, "r") as f:
            data = ujson.load(f)
    except Exception as e:
        print("Error loading state:", e)
        return

    tilt_data = data.get("tilt_coverage")
    if tilt_data:
        try:
            if len(tilt_data) == len(SNOW_DEPTH_BINS) - 1:
                if len(tilt_data[0]) == len(ANGLE_BINS):
                    tilt_coverage = tilt_data
                    print("Loaded tilt coverage from state file.")
        except Exception:
            print("Tilt coverage shape mismatch; ignoring saved coverage.")

    combo_data = data.get("combo_counts")
    if combo_data:
        try:
            for k_str, cnt in combo_data.items():
                parts = k_str.split(",")
                if len(parts) == 4:
                    key = (int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]))
                    combo_counts[key] = int(cnt)
            print("Loaded combo_counts with", len(combo_counts), "entries.")
        except Exception as e:
            print("Error parsing combo_counts:", e)

    daily_data = data.get("daily_test_counts")
    if daily_data:
        try:
            for day_key, cnt in daily_data.items():
                daily_test_counts[day_key] = int(cnt)
            print("Loaded daily_test_counts with", len(daily_test_counts), "days tracked.")
        except Exception as e:
            print("Error parsing daily_test_counts:", e)

    if "last_angle_deg" in data:
        try:
            last_angle_deg = float(data.get("last_angle_deg"))
            print("Loaded last known angle:", last_angle_deg)
        except Exception as e:
            print("Error parsing last_angle_deg:", e)


def save_state():
    combo_data = {}
    for key, cnt in combo_counts.items():
        key_str = "{},{},{},{}".format(*key)
        combo_data[key_str] = cnt
    data = {
        "tilt_coverage": tilt_coverage,
        "combo_counts": combo_data,
        "daily_test_counts": daily_test_counts,
        "last_angle_deg": last_angle_deg,
    }
    try:
        with open(STATE_FILE, "w") as f:
            ujson.dump(data, f)
    except Exception as e:
        print("Error saving state:", e)


def find_bin_index(value, edges):
    for i in range(len(edges) - 1):
        if edges[i] <= value < edges[i + 1]:
            return i
    return len(edges) - 2


def bin_snow_depth(snow_depth_mm):
    return find_bin_index(snow_depth_mm, SNOW_DEPTH_BINS)


def bin_angle(angle_deg):
    if not ANGLE_BINS:
        return 0
    closest_idx = min(range(len(ANGLE_BINS)), key=lambda i: abs(angle_deg - ANGLE_BINS[i]))
    return closest_idx


def get_next_angle_bin_for_snow_bin(snow_bin_idx):
    row = tilt_coverage[snow_bin_idx]
    for angle_idx, tested in enumerate(row):
        if not tested:
            return angle_idx
    return 0


def get_repetition_count_for_snow_bin(snow_bin_idx):
    """Return how many times the given snow bin has been tested."""

    row = tilt_coverage[snow_bin_idx]
    return sum(1 for tested in row if tested)


def mark_angle_tested(snow_idx, angle_idx):
    tilt_coverage[snow_idx][angle_idx] = True


def bin_env_variable(value, vmin, vmax, n_bins):
    if value is None:
        return n_bins // 2
    if value <= vmin:
        return 0
    if value >= vmax:
        return n_bins - 1
    width = (vmax - vmin) / n_bins
    pos = (value - vmin) / width
    idx = int(pos)
    if idx < 0:
        idx = 0
    if idx >= n_bins:
        idx = n_bins - 1
    return idx


def bin_non_tilt_env(air_temp, humidity, wind_speed, wind_dir):
    b_air = bin_env_variable(air_temp, AIR_TEMP_MIN, AIR_TEMP_MAX, AIR_TEMP_BINS)
    b_hum = bin_env_variable(humidity, HUMIDITY_MIN, HUMIDITY_MAX, HUMIDITY_BINS)
    b_wind = bin_env_variable(wind_speed, WIND_SPEED_MIN, WIND_SPEED_MAX, WIND_SPEED_BINS)
    b_dir = bin_env_variable(wind_dir, WIND_DIR_MIN, WIND_DIR_MAX, WIND_DIR_BINS)
    b_air = bin_env_variable(air_temp, AIR_TEMP_MIN, AIR_TEMP_MAX, N_BINS_ENV)
    b_hum = bin_env_variable(humidity, HUMIDITY_MIN, HUMIDITY_MAX, N_BINS_ENV)
    b_wind = bin_env_variable(wind_speed, WIND_SPEED_MIN, WIND_SPEED_MAX, N_BINS_ENV)
    b_dir = bin_env_variable(wind_dir, WIND_DIR_MIN, WIND_DIR_MAX, N_BINS_ENV)
    return (b_air, b_hum, b_wind, b_dir)

BASE_PATTERN = [
    (0.05, 0.00),
    (0.00, 0.05),
    (0.05, 0.05),
    (0.05, 0.05),
    (0.10, 0.05),
    (0.05, 0.10),
    (0.10, 0.10),
]


def get_temp_flow_adjustments_for_occurrence(count):
    cycle_len = 2 * len(BASE_PATTERN)
    idx = (count - 1) % cycle_len
    if idx < len(BASE_PATTERN):
        temp_pct, flow_pct = BASE_PATTERN[idx]
    else:
        base_idx = idx - len(BASE_PATTERN)
        temp_pct, flow_pct = BASE_PATTERN[base_idx]
        temp_pct = -temp_pct
        flow_pct = -flow_pct
    temp_factor = 1.0 + temp_pct
    flow_factor = 1.0 + flow_pct
    return temp_factor, flow_factor


def get_adjusted_temp_and_flow_for_combo(combo_key):
    global combo_counts
    count = combo_counts.get(combo_key, 0) + 1
    combo_counts[combo_key] = count
    temp_factor, flow_factor = get_temp_flow_adjustments_for_occurrence(count)
    target_temp = BASE_WATER_TEMP_C * temp_factor
    flow_level = BASE_FLOW_LEVEL * flow_factor
    if flow_level < 0.0:
        flow_level = 0.0
    if flow_level > 1.0:
        flow_level = 1.0
    return target_temp, flow_level, count


def update_last_angle(angle_deg):
    """Store the most recent measured or commanded slab angle."""

    global last_angle_deg
    if angle_deg is None:
        return
    last_angle_deg = float(angle_deg)
    print("Recorded last angle =", last_angle_deg)


def get_last_known_angle(default=NON_TILTED_ANGLE_DEG):
    """Return the last recorded angle, or a sane default if unknown."""

    if last_angle_deg is not None:
        return last_angle_deg
    return default


def _current_day_key():
    today = time.localtime()
    return f"{today.tm_year:04d}-{today.tm_mon:02d}-{today.tm_mday:02d}"


def get_next_daily_test_number():
    """Return (day_str, count) for the next test of the current day."""

    day_key = _current_day_key()
    count = daily_test_counts.get(day_key, 0) + 1
    daily_test_counts[day_key] = count
    return day_key, count
