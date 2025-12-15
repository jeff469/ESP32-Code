"""
============================================================
GLACIAL Rooftop Prototype - ESP32 MASTER (MicroPython)
------------------------------------------------------------
High-level responsibilities of this script:

- Talk to an Arduino Mega over UART2.
  * Mega is the "muscle": H-bridge, pump, heater, solenoids, lights,
    and some sensors (water temp, flow, angle, pump current).

- ESP32 is the "brain":
  * Reads snow depth from a 6-sensor ultrasonic array.
  * Every 20 minutes, starts a new "cycle":
      - Reads local environment (snow, temp, humidity, wind, etc.).
      - If snow present -> run a TILTED MELT TIME TEST.
      - If no snow     -> run a NON-TILTED ENERGY TEST.
  * Tracks which (snow_depth_bin, angle_bin) tests have been done.
  * Estimates energy used by pump + heater in Wh (based on runtime and power ratings).
  * Logs events to CSV in /logs/test_log.csv.
  * Stores state (test coverage) in test_state.json so it survives reboot.

NOTES:
- Many sensors other than snow depth are still stubs; you will replace them
  with real readings once you wire them (or request them from the Mega).
- All communication with the Mega uses simple line-based commands:
    e.g., "ACT:UP", "PUMP:ON", "READ:WATER_TEMP", etc.
"""

import time             # timekeeping, delays
import os               # filesystem operations (for logs + state)
import ujson            # JSON for saving state
import machine          # hardware (Pins, UART, time_pulse_us)
from machine import Pin, UART


# ============================================================
# ========== 1. UART COMMUNICATION WITH MEGA =================
# ============================================================

# --- UART pin selection on ESP32 ---
# GPIO17 will transmit from ESP32 to Mega (goes into Mega RX1, pin 19).
ESP32_TX_PIN = 17

# GPIO16 will receive from Mega TX1 (pin 18).
ESP32_RX_PIN = 16

# UART baud rate (must match Mega's Serial1 baud)
MEGA_BAUD = 115200

# Create UART2 object for ESP32 <-> Mega link.
#   id=2  -> UART2
#   baudrate -> communication speed
#   tx=Pin(...) / rx=Pin(...) -> which pins to use
#   timeout=100 -> read timeout in ms for blocking reads
uart = UART(
    2,
    baudrate=MEGA_BAUD,
    tx=Pin(ESP32_TX_PIN),
    rx=Pin(ESP32_RX_PIN),
    timeout=100
)


def send_command_to_mega(cmd):
    """
    Send a command string to the Arduino Mega via UART, with newline.
    e.g., send_command_to_mega("PUMP:ON")
    """
    line = (cmd + "\n").encode("utf-8")
    uart.write(line)
    print("-> MEGA:", cmd)


def read_line_from_mega(timeout_ms=200):
    """
    Attempt to read one line from the Mega within timeout_ms.

    Returns:
      The decoded line (without trailing newline) or None if no data is received.
    """
    start = time.ticks_ms()
    buf = b""
    while time.ticks_diff(time.ticks_ms(), start) < timeout_ms:
        if uart.any():
            ch = uart.read(1)
            if ch in (b"\n", b"\r"):
                if buf:
                    try:
                        line = buf.decode("utf-8").strip()
                    except UnicodeError:
                        line = ""
                    print("<- MEGA:", line)
                    return line
                else:
                    continue
            else:
                buf += ch
        else:
            time.sleep_ms(5)
    return None


# ============================================================
# ========== 2. ULTRASONIC SNOW DEPTH ARRAY ==================
# ============================================================

# Example GPIO pin assignments for 6 ultrasonic sensors.
# Adjust as needed for your wiring.
ULTRA_PINS = [
    {"trig": 4,  "echo": 5},
    {"trig": 18, "echo": 19},
    {"trig": 21, "echo": 22},
    {"trig": 23, "echo": 32},
    {"trig": 33, "echo": 25},
    {"trig": 26, "echo": 27},
]

# Speed of sound in air, in m/s (approx; can refine based on temperature)
SPEED_OF_SOUND = 343.0


class UltrasonicSensor:
    """
    Simple ultrasonic distance sensor wrapper using a trig/echo pair.

    NOTE: In MicroPython on ESP32, you might use machine.time_pulse_us
    to measure echo pulse duration.
    """

    def __init__(self, trig_pin, echo_pin):
        self.trig = Pin(trig_pin, Pin.OUT)
        self.echo = Pin(echo_pin, Pin.IN)

    def measure_distance_m(self):
        """
        Measure distance in meters.

        This is a placeholder implementation. For a real ultrasonic,
        you should implement the trigger and echo timing using
        machine.time_pulse_us(...) or similar. Here we just return a
        dummy value.
        """
        # Example stub: return a fake distance
        # Replace with real timing logic.
        # e.g.,
        #   self.trig.value(0)
        #   time.sleep_us(2)
        #   self.trig.value(1)
        #   time.sleep_us(10)
        #   self.trig.value(0)
        #   duration = machine.time_pulse_us(self.echo, 1, timeout)
        #   distance = (SPEED_OF_SOUND * (duration / 1_000_000.0)) / 2
        #   return distance
        return 0.15  # 15 cm as placeholder


# Create an array of sensor objects.
ultra_sensors = [
    UltrasonicSensor(cfg["trig"], cfg["echo"]) for cfg in ULTRA_PINS
]


def measure_snow_depth_mm():
    """
    Measure snow depth by averaging distances from all ultrasonic sensors.

    For now, we assume each sensor is mounted at a fixed height above the slab,
    say, MOUNT_HEIGHT_M. Then:

        snow_depth = MOUNT_HEIGHT - measured_distance

    We'll clamp to 0 if we get a negative depth.

    This is still a stub: it uses a placeholder mount height and
    the UltrasonicSensor class uses a fake distance.
    """
    MOUNT_HEIGHT_M = 0.5  # 50 cm above the slab (example)

    distances = []
    for sensor in ultra_sensors:
        d = sensor.measure_distance_m()
        distances.append(d)

    avg_distance = sum(distances) / len(distances)

    raw_depth_m = MOUNT_HEIGHT_M - avg_distance
    if raw_depth_m < 0:
        raw_depth_m = 0.0

    depth_mm = raw_depth_m * 1000.0
    return depth_mm


# ============================================================
# ========== 3. OTHER ENVIRONMENT SENSORS (STUBS) ============
# ============================================================

def read_air_temperature_C():
    """
    Stub for reading air temperature in °C.
    Replace with real sensor reading.
    """
    return -5.0  # placeholder


def read_relative_humidity():
    """
    Stub for reading relative humidity in %.
    Replace with real sensor reading.
    """
    return 80.0  # placeholder


def read_wind_speed_mps():
    """
    Stub for reading wind speed in m/s.
    Replace with real sensor reading.
    """
    return 3.0  # placeholder


def read_wind_direction_deg():
    """
    Stub for reading wind direction in degrees (0-360).
    Replace with real sensor reading.
    """
    return 180.0  # placeholder


# ============================================================
# ========== 4. MEGA-CONTROLLED ACTUATORS ====================
# ============================================================

def actuators_move_up():
    """
    Tell the Mega to move the slab angle up (increase angle).
    The Mega will implement the actual H-bridge control.
    """
    send_command_to_mega("ACT:UP")


def actuators_move_down():
    """
    Tell the Mega to move the slab angle down (decrease angle).
    """
    send_command_to_mega("ACT:DOWN")


def actuators_stop():
    """
    Tell the Mega to stop actuators (no movement).
    """
    send_command_to_mega("ACT:STOP")


def pump_on():
    """
    Turn the hydronic pump ON via the Mega.
    """
    send_command_to_mega("PUMP:ON")


def pump_off():
    """
    Turn the hydronic pump OFF via the Mega.
    """
    send_command_to_mega("PUMP:OFF")


def heater_on():
    """
    Turn the inline water heater ON via the Mega.
    """
    send_command_to_mega("HEATER:ON")


def heater_off():
    """
    Turn the inline water heater OFF via the Mega.
    """
    send_command_to_mega("HEATER:OFF")


def solA_open():
    """
    Open solenoid valve A via the Mega (e.g., feed loop A).
    """
    send_command_to_mega("SOL_A:OPEN")


def solA_close():
    """
    Close solenoid valve A via the Mega.
    """
    send_command_to_mega("SOL_A:CLOSE")


def solB_open():
    """
    Open solenoid valve B via the Mega (e.g., feed loop B).
    """
    send_command_to_mega("SOL_B:OPEN")


def solB_close():
    """
    Close solenoid valve B via the Mega.
    """
    send_command_to_mega("SOL_B:CLOSE")


def lights_on():
    """
    Turn the LED strip / lights ON via the Mega.
    """
    send_command_to_mega("LIGHTS:ON")


def lights_off():
    """
    Turn the LED strip / lights OFF via the Mega.
    """
    send_command_to_mega("LIGHTS:OFF")


# ============================================================
# ========== 5. MEGA SENSORS (REQUESTS) ======================
# ============================================================

def request_water_temp_C():
    """
    Request water (supply) temperature in °C from the Mega.

    The Mega is expected to respond with a line like "WATER_TEMP:23.5".
    """
    send_command_to_mega("READ:WATER_TEMP")
    line = read_line_from_mega()
    if line and line.startswith("WATER_TEMP:"):
        try:
            return float(line.split(":", 1)[1])
        except ValueError:
            pass
    # Fallback / debug
    return None


def request_flow_rate_L_min():
    """
    Request flow rate in L/min from the Mega.

    The Mega is expected to respond with "FLOW:1.23".
    """
    send_command_to_mega("READ:FLOW")
    line = read_line_from_mega()
    if line and line.startswith("FLOW:"):
        try:
            return float(line.split(":", 1)[1])
        except ValueError:
            pass
    return None


def request_slab_angle_deg():
    """
    Request slab angle in degrees from the Mega.

    The Mega is expected to respond with "ANGLE:12.3".
    """
    send_command_to_mega("READ:ANGLE")
    line = read_line_from_mega()
    if line and line.startswith("ANGLE:"):
        try:
            return float(line.split(":", 1)[1])
        except ValueError:
            pass
    return None


def request_pump_current_A():
    """
    Request pump current in amps from the Mega.

    The Mega is expected to respond with "PUMP_I:0.80".
    """
    send_command_to_mega("READ:PUMP_I")
    line = read_line_from_mega()
    if line and line.startswith("PUMP_I:"):
        try:
            return float(line.split(":", 1)[1])
        except ValueError:
            pass
    return None


# ============================================================
# ========== 6. ANGLE CONTROL LOGIC ==========================
# ============================================================

# Angle tolerance for "close enough" in degrees.
ANGLE_TOLERANCE = 0.5


def set_target_angle(angle_deg, timeout_s=60):
    """
    Ask the Mega to move the slab to a target angle (in degrees),
    using feedback from request_slab_angle_deg().

    For now, we implement a simple on/off control:
      - If current angle < target - tol -> move up
      - If current angle > target + tol -> move down
      - Else -> stop and done
    """
    start_time = time.time()
    while True:
        current_angle = request_slab_angle_deg()
        if current_angle is None:
            print("Angle read failed; continuing to move up a bit...")
            actuators_move_up()
            time.sleep(0.5)
            continue

        error = angle_deg - current_angle
        if abs(error) <= ANGLE_TOLERANCE:
            actuators_stop()
            print("Angle reached:", current_angle)
            return

        if error > 0:
            actuators_move_up()
        else:
            actuators_move_down()

        if time.time() - start_time > timeout_s:
            print("Timeout while trying to reach angle", angle_deg)
            actuators_stop()
            return

        time.sleep(0.2)


def set_non_tilt_angle():
    """
    Move slab to the default "non-tilted" angle used in energy tests.
    """
    set_target_angle(NON_TILTED_ANGLE_DEG)


# ============================================================
# ========== 7. ENERGY ESTIMATION CONFIG =====================
# ============================================================

# --- Snow detection thresholds & bins ---
SNOW_PRESENT_THRESHOLD = 5.0  # mm; above this we consider "snow present"

# Snow depth bins (in mm) for grouping tests.
# Example bins: [0-5), [5-20), [20-50), [50-100), [100-200), [200-400)
SNOW_DEPTH_BINS = [0, 5, 20, 50, 100, 200, 400]

# Angle bins from 0 to 45 degrees in 4-degree steps.
ANGLE_BIN_SIZE = 4
MAX_ANGLE_DEG = 45
ANGLE_BINS = list(range(0, MAX_ANGLE_DEG + 1, ANGLE_BIN_SIZE))

# This is the default non-tilt angle used in "energy" tests (slight tilt).
NON_TILTED_ANGLE_DEG = 5.0

# --- Non-tilted energy test: environment bins + base settings ---

# How many bins to use for each environmental variable
N_BINS_ENV = 10

# Range for air temperature (°C) to bin over
AIR_TEMP_MIN = -30.0
AIR_TEMP_MAX =  10.0

# Range for relative humidity (%) to bin over
HUMIDITY_MIN = 0.0
HUMIDITY_MAX = 100.0

# Range for wind speed (m/s) to bin over
WIND_SPEED_MIN = 0.0
WIND_SPEED_MAX = 20.0

# Range for wind direction (degrees) to bin over
WIND_DIR_MIN = 0.0
WIND_DIR_MAX = 360.0

# Baseline hydronic settings for non-tilted energy tests
BASE_WATER_TEMP_C = 30.0   # baseline supply temperature setpoint
BASE_FLOW_LEVEL   = 0.7    # baseline relative flow level (0..1)

# For the fancy pattern, we track how many times we've seen each
# (air_bin, hum_bin, wind_bin, dir_bin) combo.
# combo_counts[(air_bin, hum_bin, wind_bin, dir_bin)] -> int count
combo_counts = {}

# --- Optional PWM for pump speed control (flow level) on ESP32 ---
# Connect this pin to a MOSFET or driver that modulates pump speed.
PUMP_PWM_PIN = 25  # choose a free GPIO on ESP32

# Create a PWM object at 1 kHz on that pin.
pump_pwm = machine.PWM(Pin(PUMP_PWM_PIN), freq=1000)
# Start with 0 duty (off). The relay on the Mega still controls main power.
pump_pwm.duty(0)


def set_flow_level(flow_level):
    """
    Set pump flow level (0..1) using PWM on the ESP32.

    NOTE:
      - The Mega still turns the pump relay ON/OFF.
      - This PWM controls *how hard* the pump is driven (assuming you wire it).
      - If you do not have variable-speed hardware yet, you can leave it
        wired to nothing for now—this will just do nothing physically.
    """
    # Clamp to valid range [0, 1]
    if flow_level < 0.0:
        flow_level = 0.0
    if flow_level > 1.0:
        flow_level = 1.0

    # Map 0..1 -> 0..1023 (10-bit PWM duty for ESP32)
    duty = int(flow_level * 1023)
    pump_pwm.duty(duty)

    print("Set flow PWM level =", flow_level, "(duty =", duty, ")")

# --- Energy estimation constants ---
# Nameplate power ratings (adjust to your real pump + heater).
PUMP_POWER_W = 100.0    # e.g., 100 W pump
HEATER_POWER_W = 600.0 # e.g., 600 W heater

# Global accumulators for energy usage (in Watt-hours).
pump_energy_Wh_total = 0.0
heater_energy_Wh_total = 0.0

# Track whether the pump and heater are "currently on".
pump_is_on = False
heater_is_on = False

# Last timestamp (seconds) when energy counters were updated.
_last_energy_update_time = time.time()

# Global water temperature setpoint for "during test" heater control (if used).
current_water_setpoint = 0.0


def _update_energy_counters():
    """
    Update the energy usage counters based on how long the pump/heater
    have been ON since the last update.

    This functions as a simple time * power integration.
    """
    global pump_energy_Wh_total, heater_energy_Wh_total
    global _last_energy_update_time

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
    """
    Turn pump ON or OFF and update energy counters accordingly.
    """
    global pump_is_on
    _update_energy_counters()
    if on:
        pump_on()
        pump_is_on = True
    else:
        pump_off()
        pump_is_on = False


def set_heater_state(on):
    """
    Turn heater ON or OFF and update energy counters accordingly.
    """
    global heater_is_on
    _update_energy_counters()
    if on:
        heater_on()
        heater_is_on = True
    else:
        heater_off()
        heater_is_on = False


def get_energy_totals_Wh():
    """
    Return the current totals (pump_Wh, heater_Wh).
    """
    _update_energy_counters()
    return pump_energy_Wh_total, heater_energy_Wh_total


# ============================================================
# ========== 8. WATER TEMPERATURE CONTROL (PREHEAT) ==========
# ============================================================

def ensure_supply_hot(target_temp_C, timeout_s=900):
    """
    Simple preheat routine:

      - Turn the heater ON.
      - Periodically read water supply temperature from Mega.
      - Stop when water_temp >= target_temp_C or timeout.
    """
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


# ============================================================
# ========== 9. SNOW PRESENCE DECISION =======================
# ============================================================

def is_snow_present(snow_depth_mm):
    """
    Return True if we consider "snow present" for the purpose of selecting
    which test to run.
    """
    return snow_depth_mm >= SNOW_PRESENT_THRESHOLD


# ============================================================
# ========== 10. STATE: TILT COVERAGE & BINNING ==============
# ============================================================

def init_tilt_coverage():
    """
    Initialize tilt_coverage as a 2D list of booleans:

        tilt_coverage[snow_bin_idx][angle_bin_idx]

    All entries start as False (meaning "not tested yet").
    """
    global tilt_coverage

    # Number of snow bins is len(SNOW_DEPTH_BINS) - 1.
    n_snow = len(SNOW_DEPTH_BINS) - 1
    # Number of angle bins is len(ANGLE_BINS) - 1 (if using intervals).
    n_angle = len(ANGLE_BINS) - 1

    tilt_coverage = [
        [False for _ in range(n_angle)]  # one row per snow bin
        for _ in range(n_snow)           # repeat for each snow bin
    ]


def load_state():
    """
    Load tilt_coverage and combo_counts from STATE_FILE (test_state.json)
    if it exists. If the file doesn't exist or is corrupted, we start fresh.
    """
    global tilt_coverage, combo_counts

    # Start with fresh defaults.
    init_tilt_coverage()
    combo_counts = {}

    try:
        if STATE_FILE not in os.listdir():
            print("No state file found; starting with fresh coverage.")
            return

        with open(STATE_FILE, "r") as f:
            data = ujson.load(f)
    except Exception as e:
        print("Error loading state:", e)
        return

    # --- Tilt coverage ---
    tilt_data = data.get("tilt_coverage")
    if tilt_data:
        try:
            if len(tilt_data) == len(SNOW_DEPTH_BINS) - 1:
                if len(tilt_data[0]) == len(ANGLE_BINS) - 1:
                    tilt_coverage = tilt_data
                    print("Loaded tilt coverage from state file.")
        except Exception:
            print("Tilt coverage shape mismatch; ignoring saved coverage.")

    # --- Combo counts ---
    combo_data = data.get("combo_counts")
    if combo_data:
        try:
            for k_str, cnt in combo_data.items():
                parts = k_str.split(",")
                if len(parts) == 4:
                    key = (int(parts[0]), int(parts[1]),
                           int(parts[2]), int(parts[3]))
                    combo_counts[key] = int(cnt)
            print("Loaded combo_counts with", len(combo_counts), "entries.")
        except Exception as e:
            print("Error parsing combo_counts:", e)


def save_state():
    """
    Save tilt_coverage and combo_counts to STATE_FILE as JSON,
    so we remember which tests are done and how many times each
    weather combo has occurred across reboots.
    """
    # Serialize combo_counts dict with string keys for JSON.
    combo_data = {}
    for key, cnt in combo_counts.items():
        # key is a 4-tuple (air_bin, hum_bin, wind_bin, dir_bin)
        key_str = "{},{},{},{}".format(*key)
        combo_data[key_str] = cnt

    data = {
        "tilt_coverage": tilt_coverage,
        "combo_counts": combo_data,
    }

    try:
        with open(STATE_FILE, "w") as f:
            ujson.dump(data, f)
    except Exception as e:
        print("Error saving state:", e)


def find_bin_index(value, edges):
    """
    Given a list of edges [e0, e1, ..., en], return bin index i such that:

        edges[i] <= value < edges[i+1]

    If value is >= last edge, we place it in the last bin.
    """
    for i in range(len(edges) - 1):
        if edges[i] <= value < edges[i + 1]:
            return i
    # If we reach here, value is above or equal to last edge.
    return len(edges) - 2


def bin_snow_depth(snow_depth_mm):
    """
    Return the snow depth bin index for a given snow_depth_mm.
    """
    return find_bin_index(snow_depth_mm, SNOW_DEPTH_BINS)


def bin_angle(angle_deg):
    """
    Return the angle bin index for a given angle_deg.
    """
    return find_bin_index(angle_deg, ANGLE_BINS)


def get_next_angle_bin_for_snow_bin(snow_bin_idx):
    """
    Find the next angle bin index for a given snow bin that has not yet
    been tested. If all angles for this snow bin have been tested, we
    wrap around (for now).
    """
    global tilt_coverage

    row = tilt_coverage[snow_bin_idx]
    for angle_idx, tested in enumerate(row):
        if not tested:
            return angle_idx

    return 0


def mark_angle_tested(snow_idx, angle_idx):
    """
    Mark that the test for (snow_bin_idx, angle_bin_idx) has been completed.
    """
    tilt_coverage[snow_idx][angle_idx] = True


# ============================================================
# ========== 11. CSV LOGGING ================================
# ============================================================

STATE_FILE = "test_state.json"    # persistent state file
LOG_DIR = "/logs"                 # directory for CSV logs
LOG_FILE = LOG_DIR + "/test_log.csv"


def ensure_log_dir():
    """
    Make sure the log directory exists.
    If mkdir fails because it already exists, we ignore the error.
    """
    try:
        os.mkdir(LOG_DIR)
    except OSError:
        pass


def init_log_file():
    """
    Create the CSV log file with a header row if it does not already exist.
    """
    ensure_log_dir()
    if LOG_FILE not in os.listdir(LOG_DIR):
        with open(LOG_FILE, "w") as f:
            header = (
                "timestamp,event_type,"
                "snow_depth_mm,air_temp_C,humidity_pct,wind_speed_mps,wind_dir_deg,"
                "snow_bin_idx,angle_bin_idx,angle_deg,"
                "test_run_id,test_type,"
                "pump_Wh,heater_Wh,"
                "extra\n"
            )
            f.write(header)


def log_event(event_type, env, extra=None):
    """
    Append one line to the log CSV.

    env should be a dict with keys:
      - snow_depth
      - air_temp
      - humidity
      - wind_speed
      - wind_dir

    extra is an optional dict of additional fields to append as JSON.
    """
    ensure_log_dir()
    try:
        f = open(LOG_FILE, "a")
    except OSError:
        print("Failed to open log file for append.")
        return

    ts = time.time()

    snow_depth = env.get("snow_depth", 0.0)
    air_temp = env.get("air_temp", 0.0)
    humidity = env.get("humidity", 0.0)
    wind_speed = env.get("wind_speed", 0.0)
    wind_dir = env.get("wind_dir", 0.0)

    snow_bin_idx = env.get("snow_bin_idx", -1)
    angle_bin_idx = env.get("angle_bin_idx", -1)
    angle_deg = env.get("angle_deg", 0.0)

    pump_Wh, heater_Wh = get_energy_totals_Wh()

    extra_json = ""
    if extra is not None:
        try:
            extra_json = ujson.dumps(extra)
        except Exception:
            extra_json = ""

    line = (
        "{:.3f},{},"
        "{:.3f},{:.3f},{:.3f},{:.3f},{:.3f},"
        "{},{},{:.3f},"
        "{},{},"
        "{:.3f},{:.3f},"
        "{}\n"
    ).format(
        ts, event_type,
        snow_depth, air_temp, humidity, wind_speed, wind_dir,
        snow_bin_idx, angle_bin_idx, angle_deg,
        extra.get("test_run_id", "") if extra else "",
        extra.get("test_type", "") if extra else "",
        pump_Wh, heater_Wh,
        extra_json
    )

    try:
        f.write(line)
        f.close()
    except Exception:
        print("Error writing to log file.")


# ============================================================
# ========== 12. TEST ROUTINES ===============================
# ============================================================

def run_tilted_test(env):
    """
    Run a tilted melt-time test when snow is present.

    Steps:
      1) Determine which snow bin we are in and which angle bin is next.
      2) Log TILTED_START.
      3) Preheat water to a target temp (e.g., 35°C).
      4) Move slab to target angle.
      5) Turn pump ON.
      6) In a loop:
           - periodically log TILTED_PROGRESS with current snow depth.
           - stop when snow_depth < some threshold or timeout.
      7) Log TILTED_END with total time and energy usage.
      8) Mark (snow_bin, angle_bin) as tested and save state.
    """
    snow_depth = env["snow_depth"]
    snow_idx = bin_snow_depth(snow_depth)
    angle_idx = get_next_angle_bin_for_snow_bin(snow_idx)
    target_ang = ANGLE_BINS[angle_idx]

    test_id = "tilted_{}_{}_{}".format(snow_idx, angle_idx, int(time.time()))

    extra_start = {
        "test_type": "tilted",
        "test_run_id": test_id,
        "snow_bin_idx": snow_idx,
        "angle_bin_idx": angle_idx,
        "angle_deg": target_ang,
    }
    log_event("TILTED_START", env, extra_start)

    print("TILTED TEST:")
    print("  snow bin index:", snow_idx, "angle bin index:", angle_idx)
    print("  target angle:", target_ang, "deg")

    TARGET_WATER_TEMP = 35.0
    ensure_supply_hot(TARGET_WATER_TEMP)

    set_target_angle(target_ang)

    pump_Wh_start, heater_Wh_start = get_energy_totals_Wh()

    set_pump_state(True)

    start_time = time.time()
    last_log_time = start_time
    MAX_TEST_DURATION_S = 3600

    while True:
        now = time.time()
        elapsed = now - start_time

        current_snow = measure_snow_depth_mm()

        env["snow_depth"] = current_snow
        env["snow_bin_idx"] = snow_idx
        env["angle_bin_idx"] = angle_idx
        env["angle_deg"] = target_ang

        if now - last_log_time >= 30:
            extra_prog = {
                "test_type": "tilted",
                "test_run_id": test_id,
                "elapsed_s": elapsed,
            }
            log_event("TILTED_PROGRESS", env, extra_prog)
            last_log_time = now

        if current_snow < SNOW_PRESENT_THRESHOLD:
            print("Snow melted (depth < threshold). Ending test.")
            break

        if elapsed > MAX_TEST_DURATION_S:
            print("Tilted test max duration reached. Ending test.")
            break

        time.sleep(5)

    set_pump_state(False)

    total_dur = time.time() - start_time
    pump_Wh_end, heater_Wh_end = get_energy_totals_Wh()
    pump_Wh_used = pump_Wh_end - pump_Wh_start
    heater_Wh_used = heater_Wh_end - heater_Wh_start

    mark_angle_tested(snow_idx, angle_idx)
    save_state()

    extra_end = {
        "test_type": "tilted",
        "test_run_id": test_id,
        "snow_bin_idx": snow_idx,
        "angle_bin_idx": angle_idx,
        "angle_deg": target_ang,
        "duration_s": total_dur,
        "snow_depth": current_snow,
        "pump_Wh": pump_Wh_used,
        "heater_Wh": heater_Wh_used,
    }
    log_event("TILTED_END", env, extra_end)


# ============================================================
#  FANCY NON-TILTED COMBO LOGIC
# ============================================================

def bin_env_variable(value, vmin, vmax, n_bins):
    """
    Convert a numeric value into an integer bin index 0..(n_bins-1).

    - Clamps values outside [vmin, vmax] into the edge bins.
    - Assumes uniform bin width.
    """
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
    """
    Convert the continuous environment variables to discrete bins:

      - air temperature bin
      - humidity bin
      - wind speed bin
      - wind direction bin

    Returns:
      (air_bin, hum_bin, wind_bin, dir_bin)
    """
    b_air  = bin_env_variable(air_temp,   AIR_TEMP_MIN,   AIR_TEMP_MAX,   N_BINS_ENV)
    b_hum  = bin_env_variable(humidity,   HUMIDITY_MIN,   HUMIDITY_MAX,   N_BINS_ENV)
    b_wind = bin_env_variable(wind_speed, WIND_SPEED_MIN, WIND_SPEED_MAX, N_BINS_ENV)
    b_dir  = bin_env_variable(wind_dir,   WIND_DIR_MIN,   WIND_DIR_MAX,   N_BINS_ENV)
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
    """
    Given how many times we've seen this combo (1, 2, 3, ...),
    return multiplicative factors (temp_factor, flow_factor).

    Pattern:
      - Counts 1..7  : use BASE_PATTERN as +% adjustments.
      - Counts 8..14 : repeat the same pattern but NEGATIVE (cooling / slower).
      - Counts >14   : wrap around (modulo 14).
    """
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
    """
    Given a binned environment combo key:
        combo_key = (air_bin, hum_bin, wind_bin, dir_bin)

    - Increment its occurrence count in combo_counts.
    - Use that count to determine temp & flow adjustment factors.
    - Return:
        (target_temp_C, effective_flow_level, count)
    """
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


def run_energy_test(env):
    """
    Run a non-tilted energy delivery test when there is no snow,
    using the fancy combo-based logic:

      - Bin (air_temp, humidity, wind_speed, wind_dir) into discrete bins.
      - Use that 4D bin combo as a key into combo_counts.
      - Based on how many times this combo has occurred, adjust:
          * water temperature setpoint (±5/10%)
          * flow level (±5/10%)
        according to the 7-step positive + 7-step negative pattern.

    For this prototype:
      - Flow level is applied via PWM on ESP32 (set_flow_level),
        assuming you wire it to a variable-speed pump driver.
      - Pump relay on the Mega still turns pump power ON/OFF.
    """
    air_temp   = env["air_temp"]
    humidity   = env["humidity"]
    wind_speed = env["wind_speed"]
    wind_dir   = env["wind_dir"]

    combo_key = bin_non_tilt_env(air_temp, humidity, wind_speed, wind_dir)

    target_temp, flow_level, occur = get_adjusted_temp_and_flow_for_combo(combo_key)

    combo_str = "({}, {}, {}, {})".format(*combo_key)

    test_id = "energy_{}_{}".format(combo_str.replace(" ", ""), int(time.time()))

    extra_start = {
        "test_type": "energy",
        "test_run_id": test_id,
        "angle_deg": NON_TILTED_ANGLE_DEG,
        "air_bin": combo_key[0],
        "hum_bin": combo_key[1],
        "wind_bin": combo_key[2],
        "dir_bin": combo_key[3],
        "combo_occurrence": occur,
        "target_temp_C": round(target_temp, 2),
        "target_flow_level": round(flow_level, 3),
    }
    log_event("ENERGY_START", env, extra_start)

    print("ENERGY TEST")
    print("  env bins:", combo_key, "occurrence #", occur)
    print("  target_temp_C =", target_temp, "  flow_level =", flow_level)

    set_non_tilt_angle()

    ensure_supply_hot(target_temp)

    set_flow_level(flow_level)

    pump_Wh_start, heater_Wh_start = get_energy_totals_Wh()

    pump_on()

    TEST_DUR = 10 * 60
    start = time.time()

    while True:
        elapsed = time.time() - start

        extra_prog = {
            "test_type": "energy",
            "test_run_id": test_id,
            "elapsed_s": elapsed,
            "combo_occurrence": occur,
            "target_temp_C": round(target_temp, 2),
            "target_flow_level": round(flow_level, 3),
        }
        log_event("ENERGY_PROGRESS", env, extra_prog)

        if elapsed >= TEST_DUR:
            break

        time.sleep(10)

    pump_off()

    total_dur = time.time() - start
    pump_Wh_end, heater_Wh_end = get_energy_totals_Wh()
    pump_Wh_used = pump_Wh_end - pump_Wh_start
    heater_Wh_used = heater_Wh_end - heater_Wh_start

    extra_end = {
        "test_type": "energy",
        "test_run_id": test_id,
        "duration_s": total_dur,
        "combo_occurrence": occur,
        "target_temp_C": round(target_temp, 2),
        "target_flow_level": round(flow_level, 3),
        "pump_Wh": pump_Wh_used,
        "heater_Wh": heater_Wh_used,
    }
    log_event("ENERGY_END", env, extra_end)

    save_state()


# ============================================================
# ========== 13. MAIN CONTROL LOOP ===========================
# ============================================================

def main():
    """
    Main control loop of the ESP32 master.

    On startup:
      - Load tilt coverage state.
      - Initialize log file.
      - Determine initial angle from sensor if possible.

    Then, every 20 minutes:
      - Measure environment (snow depth, air temp, humidity, wind).
      - Decide which test to run (tilted vs energy).
      - Run that test.

    For debugging, you can shorten the cycle or force certain behavior.
    """
    load_state()
    init_log_file()

    initial_angle = request_slab_angle_deg()
    if initial_angle is not None:
        print("Initial slab angle from sensor:", initial_angle)
    else:
        print("Could not read initial slab angle; leaving actuators stopped.")
        actuators_stop()

    CYCLE_PERIOD_S = 20 * 60

    while True:
        cycle_start = time.time()

        snow_depth = measure_snow_depth_mm()
        air_temp = read_air_temperature_C()
        humidity = read_relative_humidity()
        wind_speed = read_wind_speed_mps()
        wind_dir = read_wind_direction_deg()

        env = {
            "snow_depth": snow_depth,
            "air_temp": air_temp,
            "humidity": humidity,
            "wind_speed": wind_speed,
            "wind_dir": wind_dir,
        }

        print("New cycle: snow_depth = {:.1f} mm, air_temp = {:.1f} °C".format(
            snow_depth, air_temp
        ))

        if is_snow_present(snow_depth):
            print("Snow present -> running tilted melt-time test.")
            run_tilted_test(env)
        else:
            print("No snow -> running non-tilted energy test.")
            run_energy_test(env)

        cycle_end = time.time()
        elapsed = cycle_end - cycle_start
        remaining = CYCLE_PERIOD_S - elapsed
        if remaining > 0:
            print("Cycle complete. Sleeping for", remaining, "seconds.")
            time.sleep(remaining)
        else:
            print("Cycle overran 20 minutes; starting next cycle now.")


# ============================================================
# ========== 14. ENTRY POINT =================================
# ============================================================

main()
