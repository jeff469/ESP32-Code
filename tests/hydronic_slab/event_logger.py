"""CSV logging helpers for hydronic slab tests."""
import os
import time
import ujson

from tests.hydronic_slab.state import LOG_DIR, LOG_FILE, get_energy_totals_Wh


def ensure_log_dir():
    try:
        os.mkdir(LOG_DIR)
    except OSError:
        pass


def init_log_file():
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
        extra_json,
    )

    try:
        f.write(line)
        f.close()
    except Exception:
        print("Error writing to log file.")
