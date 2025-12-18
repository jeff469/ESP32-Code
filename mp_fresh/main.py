import time

try:
    import ujson as json
except Exception:
    import json

import config
import sensors
import glacial_state as state
import logger
from mega import MegaController


PRESET = config.PRESET_CLEAR_DISTANCE_CM


def avg(values):
    if not values:
        return 0
    return sum(values) / len(values)


def bin_value(value, width, max_value):
    bin_idx = int(value // width)
    if bin_idx > max_value:
        bin_idx = max_value
    if bin_idx < 0:
        bin_idx = 0
    return bin_idx


def build_bin_id(ambient, wind):
    temp, hum = ambient
    speed, direction = wind
    tbin = bin_value(temp, config.BIN_WIDTH_TEMP, config.BIN_MAX_TEMP)
    hbin = bin_value(hum, config.BIN_WIDTH_HUM, config.BIN_MAX_HUM)
    sbin = bin_value(speed, config.BIN_WIDTH_WIND_SPEED, config.BIN_MAX_WIND_SPEED)
    dbin = bin_value(direction, 360 // config.BIN_WIDTH_WIND_DIR, config.BIN_MAX_WIND_DIR)
    return "%d,%d,%d,%d" % (tbin, hbin, sbin, dbin)


def upload_stub(path):
    print("Upload stub for", path)


def snow_depth_cm(distances):
    d_avg = avg(distances)
    depth = PRESET - d_avg
    if depth < 0:
        depth = 0
    return depth


def wait_for_rest(seconds):
    if config.RUN_ONCE:
        print("RUN_ONCE enabled, skipping rest period")
        return
    print("Resting for", seconds, "seconds")
    end = time.time() + seconds
    next_report = time.time()
    while time.time() < end:
        if time.time() >= next_report:
            remaining = int(end - time.time())
            print("Rest remaining", remaining, "s")
            next_report = time.time() + 10
        time.sleep(1)


def heat_to_target(mg, thermo, target):
    start = time.time()
    mg.heater_on()
    print("Heating to target", target)
    while True:
        t_now = thermo.read_temp_c()
        elapsed = time.time() - start
        print("Heating status temp", t_now, "elapsed", int(elapsed), "s")
        if t_now >= target:
            break
        if elapsed >= config.HEAT_TIMEOUT_SECONDS:
            print(
                "heater timeout at",
                int(config.HEAT_TIMEOUT_SECONDS),
                "s; current temp",
                t_now,
                "continuing",
            )
            break
        time.sleep(1)
    mg.heater_off()
    elapsed = time.time() - start
    print("target temp reached or timeout in", int(elapsed), "seconds")


def print_sensor_sources(suite):
    print("Sensor sources:")
    print("  Ultrasonic[0] REAL trig", config.ULTRASONIC_PINS["trig"], "echo", config.ULTRASONIC_PINS["echo"])
    print("  Ultrasonic[1-3] STUB values", config.STUB_ULTRASONIC_CM)
    print("  Fluid temp[0] REAL pin", config.DS18B20_PIN, "temp[1] STUB", config.STUB_FLUID_TEMP_C)
    print("  Ambient[0] REAL I2C1 SDA", config.I2C_SDA, "SCL", config.I2C_SCL, "others STUB")
    print("  Flow[0] REAL pin", config.FLOW_PIN, "others STUB")
    print("  Wind STUB", config.STUB_WIND)
    print("  Pavement STUB count 10 value", config.STUB_PAVEMENT_TEMP_C)
    print("RUN_ONCE", config.RUN_ONCE, "SMOKE_TEST", config.SMOKE_TEST, "DIAGNOSTIC_TEST", config.DIAGNOSTIC_TEST)


def run_tilted(suite, mg, st, bin_id, bin_index, bin_count):
    trial_num = state.next_trial_number(st)
    path = logger.log_path(trial_num, True)
    log = logger.CSVLogger(path)
    angle = min(bin_index * 10, config.TILTED_MAX_ANGLE)
    print(
        "Starting tilted trial",
        trial_num,
        "bin",
        bin_id,
        "index",
        bin_index,
        "angle",
        angle,
        "log",
        path,
    )
    print("Initial BIN ID", bin_id, "current repetition count", bin_count)
    heat_to_target(mg, suite.thermo_real, config.TARGET_TEMP_C)
    mg.set_angle_deg(angle)
    mg.pump_on()
    start = time.time()
    print("Tilted test starting at angle", angle)
    while True:
        distances = suite.read_ultrasonics()
        snow = snow_depth_cm(distances)
        temps = suite.read_temps()
        amb = suite.ambient_real.read()
        wind = suite.read_wind()
        flows = suite.read_flows()
        pav = suite.read_pavement()
        ts = logger.timestamp()
        log.log(
            {
                "ts": ts,
                "snow_depth_cm": snow,
                "distances": distances,
                "ambient": amb,
                "wind": wind,
                "flows": flows,
                "fluid_temps": temps,
                "pavement_avg": avg(pav),
                "angle": angle,
                "pump": "on",
                "heater": "off",
            }
        )
        remaining = int(config.TRIAL_MAX_SECONDS - (time.time() - start))
        print(
            "Tilted tick ts",
            ts,
            "snow",
            snow,
            "raw distances",
            distances,
            "temps",
            temps,
            "ambient",
            amb,
            "wind",
            wind,
            "flows",
            flows,
            "pav_avg",
            avg(pav),
            "remaining",
            remaining,
            "s",
        )
        if snow <= config.SNOW_CLEAR_CM:
            print("Tilted test ended: snow clear")
            break
        if time.time() - start >= config.TRIAL_MAX_SECONDS:
            print("Tilted test ended: time limit")
            break
        time.sleep(config.LOG_INTERVAL_SECONDS)
    mg.set_angle_deg(5)
    mg.pump_off()
    mg.heater_off()
    upload_stub(path)
    wait_for_rest(config.TRIAL_REST_SECONDS)


def run_non_tilted(suite, mg, st, bin_id, bin_index, bin_count):
    trial_num = state.next_trial_number(st)
    path = logger.log_path(trial_num, False)
    log = logger.CSVLogger(path)
    targets = config.NON_TILTED_TARGETS
    target = targets[bin_index] if bin_index < len(targets) else targets[0]
    print(
        "Starting non-tilted trial",
        trial_num,
        "bin",
        bin_id,
        "index",
        bin_index,
        "target",
        target,
        "log",
        path,
    )
    print("Initial BIN ID", bin_id, "current repetition count", bin_count)
    heat_to_target(mg, suite.thermo_real, target)
    mg.set_angle_deg(0)
    mg.pump_on()
    start = time.time()
    print("Non-tilted test starting at target", target)
    while True:
        distances = suite.read_ultrasonics()
        snow = snow_depth_cm(distances)
        temps = suite.read_temps()
        amb = suite.ambient_real.read()
        wind = suite.read_wind()
        flows = suite.read_flows()
        pav = suite.read_pavement()
        pav_avg = avg(pav)
        ts = logger.timestamp()
        log.log(
            {
                "ts": ts,
                "snow_depth_cm": snow,
                "distances": distances,
                "ambient": amb,
                "wind": wind,
                "flows": flows,
                "fluid_temps": temps,
                "pavement_avg": pav_avg,
                "angle": 0,
                "pump": "on",
                "heater": "off",
            }
        )
        remaining = int(config.TRIAL_MAX_SECONDS - (time.time() - start))
        print(
            "Non-tilted tick ts",
            ts,
            "snow",
            snow,
            "raw distances",
            distances,
            "pav_avg",
            pav_avg,
            "temps",
            temps,
            "ambient",
            amb,
            "wind",
            wind,
            "flows",
            flows,
            "remaining",
            remaining,
            "s",
        )
        if pav_avg >= config.PAVEMENT_CLEAR_C:
            print("Non-tilted test ended: pavement warm")
            break
        if time.time() - start >= config.TRIAL_MAX_SECONDS:
            print("Non-tilted test ended: time limit")
            break
        time.sleep(config.LOG_INTERVAL_SECONDS)
    mg.set_angle_deg(5)
    mg.pump_off()
    mg.heater_off()
    upload_stub(path)
    wait_for_rest(config.TRIAL_REST_SECONDS)


def smoke_test(suite, mg):
    print("Running SMOKE_TEST")
    print("Ambient real:", suite.ambient_real.read())
    print("Ultrasonic real:", suite.ultrasonic_real.measure_distance_cm())
    print("Flow real:", suite.flow_real.read_l_min())
    print("Fluid temp real:", suite.thermo_real.read_temp_c())
    mg.heater_on()
    mg.heater_off()
    mg.pump_on()
    mg.pump_off()
    mg.act_up()
    mg.act_stop()
    mg.act_down()
    mg.act_stop()
    print("Smoke test complete")


def diagnostic_test(suite, mg, st):
    print("Running DIAGNOSTIC_TEST")
    print("glacial_state file:", getattr(state, "__file__", None))
    print("State keys:", st)
    for i in range(config.DIAG_SAMPLE_COUNT):
        distances = suite.read_ultrasonics()
        snow = snow_depth_cm(distances)
        amb = suite.ambient_real.read()
        wind = suite.read_wind()
        bin_id = build_bin_id(amb, wind)
        flows = suite.read_flows()
        temps = suite.read_temps()
        pav = suite.read_pavement()
        pav_avg = avg(pav)
        print(
            "Sample",
            i + 1,
            "bin",
            bin_id,
            "snow",
            snow,
            "ambient",
            amb,
            "wind",
            wind,
            "flows",
            flows,
            "fluid_temps",
            temps,
            "pav_avg",
            pav_avg,
        )
        time.sleep(config.DIAG_SAMPLE_DELAY_S)
    smoke_test(suite, mg)
    print("DIAGNOSTIC_TEST complete")


def main_loop():
    logger.ensure_dirs()
    st = state.load_state()
    suite = sensors.SensorSuite()
    mg = MegaController()

    print_sensor_sources(suite)

    if config.DIAGNOSTIC_TEST:
        diagnostic_test(suite, mg, st)
        return

    if config.SMOKE_TEST:
        smoke_test(suite, mg)
        return

    while True:
        distances = suite.read_ultrasonics()
        snow = snow_depth_cm(distances)
        amb = suite.ambient_real.read()
        wind = suite.read_wind()
        bin_id = build_bin_id(amb, wind)
        current_count = state.get_bin_count(st, bin_id)
        print(
            "Bin ID",
            bin_id,
            "snow depth",
            snow,
            "raw distances",
            distances,
            "ambient",
            amb,
            "wind",
            wind,
            "prev count",
            current_count,
        )
        if snow >= config.SNOW_THRESHOLD_CM:
            bin_index = state.bump_bin_count(st, bin_id, 4)
            print("Tilted path selected; using bin index", bin_index)
            print("Updated bin count now", state.get_bin_count(st, bin_id))
            run_tilted(suite, mg, st, bin_id, bin_index, state.get_bin_count(st, bin_id))
        else:
            bin_index = state.bump_bin_count(st, bin_id, 6)
            print("Non-tilted path selected; using bin index", bin_index)
            print("Updated bin count now", state.get_bin_count(st, bin_id))
            run_non_tilted(suite, mg, st, bin_id, bin_index, state.get_bin_count(st, bin_id))

        if config.RUN_ONCE:
            print("RUN_ONCE set, exiting after single trial")
            break


if __name__ == "__main__":
    main_loop()
