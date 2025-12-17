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


def bin_value(value, width):
    return int(value // width)


def build_bin_id(ambient, wind):
    temp, hum = ambient
    speed, direction = wind
    tbin = bin_value(temp, config.BIN_WIDTH_TEMP)
    hbin = bin_value(hum, config.BIN_WIDTH_HUM)
    sbin = bin_value(speed, config.BIN_WIDTH_WIND_SPEED)
    dbin = bin_value(direction, 360 // config.BIN_WIDTH_WIND_DIR)
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
    while time.time() < end:
        time.sleep(1)


def heat_to_target(mg, thermo, target):
    start = time.time()
    mg.heater_on()
    while True:
        t_now = thermo.read_temp_c()
        if t_now >= target:
            break
        time.sleep(1)
    mg.heater_off()
    elapsed = time.time() - start
    print("target temp reached in", int(elapsed), "seconds")


def run_tilted(suite, mg, st, bin_id, bin_index):
    trial_num = state.next_trial_number(st)
    path = logger.log_path(trial_num, True)
    log = logger.CSVLogger(path)
    angle = min(bin_index * 10, config.TILTED_MAX_ANGLE)
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


def run_non_tilted(suite, mg, st, bin_id, bin_index):
    trial_num = state.next_trial_number(st)
    path = logger.log_path(trial_num, False)
    log = logger.CSVLogger(path)
    targets = config.NON_TILTED_TARGETS
    target = targets[bin_index] if bin_index < len(targets) else targets[0]
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
        print("Bin ID", bin_id, "snow depth", snow)
        if snow >= config.SNOW_THRESHOLD_CM:
            bin_index = state.bump_bin_count(st, bin_id, 4)
            run_tilted(suite, mg, st, bin_id, bin_index)
        else:
            bin_index = state.bump_bin_count(st, bin_id, 6)
            run_non_tilted(suite, mg, st, bin_id, bin_index)

        if config.RUN_ONCE:
            print("RUN_ONCE set, exiting after single trial")
            break


if __name__ == "__main__":
    main_loop()
