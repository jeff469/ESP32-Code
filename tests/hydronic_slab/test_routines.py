"""Test routines split out of the monolithic prototype script."""
import time

from tests.hydronic_slab.angle_control import NON_TILTED_ANGLE_DEG, set_non_tilt_angle, set_target_angle
from tests.hydronic_slab.data_recorder import SampleRecorder
from tests.hydronic_slab.event_logger import log_event
from tests.hydronic_slab.sensors.ultrasonic import measure_snow_depth_mm
from tests.hydronic_slab.state import (
    ANGLE_BINS,
    SNOW_CLEAR_THRESHOLD,
    bin_non_tilt_env,
    bin_snow_depth,
    ensure_supply_hot,
    get_next_daily_test_number,
    get_adjusted_temp_and_flow_for_combo,
    get_energy_totals_Wh,
    get_next_angle_bin_for_snow_bin,
    get_repetition_count_for_snow_bin,
    mark_angle_tested,
    save_state,
    set_flow_level,
    set_pump_state,
)
from tests.hydronic_slab.thermostat import regulate_water_temp

SIMULATED_MELT_MM_PER_CYCLE = 5.0


def run_tilted_test(env):
    """
    Run a tilted melt-time test when snow is present.
    """
    print("\n===== BEGIN TILTED TEST =====")
    snow_depth = env["snow_depth"]
    start_snow_depth = snow_depth
    snow_idx = bin_snow_depth(snow_depth)
    env_bin = bin_non_tilt_env(
        env.get("air_temp"), env.get("humidity"), env.get("wind_speed"), env.get("wind_dir")
    )
    angle_idx = get_next_angle_bin_for_snow_bin(snow_idx)
    repetition_count = get_repetition_count_for_snow_bin(snow_idx)
    target_ang = ANGLE_BINS[angle_idx]

    print(
        "Tilted test setup -> snow bin",
        snow_idx,
        "angle bin",
        angle_idx,
        "target angle (deg) =",
        target_ang,
        "repetition #",
        repetition_count + 1,
    )

    day_key, test_no = get_next_daily_test_number()
    test_id = "{}_test{}_tilted_{}_{}".format(day_key, test_no, snow_idx, angle_idx)

    extra_start = {
        "test_type": "tilted",
        "test_run_id": test_id,
        "test_no": test_no,
        "test_day": day_key,
        "snow_bin_idx": snow_idx,
        "angle_bin_idx": angle_idx,
        "angle_deg": target_ang,
    }
    env["env_bin"] = env_bin

    log_event("TILTED_START", env, extra_start)

    print(
        "TILTED TEST START -> TEST #{} ANGLE {} DEG | env_bin {} | repetition #{}".format(
            test_no, target_ang, env_bin, repetition_count + 1
        )
    )

    TARGET_WATER_TEMP = 35.0
    ensure_supply_hot(TARGET_WATER_TEMP)

    set_target_angle(target_ang)
    print(
        "Actuating to target angle:",
        target_ang,
        "(repetition #{})".format(repetition_count + 1),
    )

    pump_Wh_start, heater_Wh_start = get_energy_totals_Wh()

    set_pump_state(True)
    print("Tilted test -> pump on")

    start_time = time.time()
    last_log_time = start_time
    last_sample_time = start_time
    MAX_TEST_DURATION_S = 3600

    recorder = SampleRecorder(test_id)

    modeled_snow_depth = None
    time_to_clear_s = None
    end_reason = None

    while True:
        now = time.time()
        elapsed = now - start_time

        measured_snow = measure_snow_depth_mm()
        if modeled_snow_depth is None:
            current_snow = measured_snow
        else:
            if measured_snow >= modeled_snow_depth - 0.01:
                current_snow = max(modeled_snow_depth - SIMULATED_MELT_MM_PER_CYCLE, 0.0)
                print(
                    "Tilted test -> modeling melt: measured",
                    round(measured_snow, 2),
                    "mm -> adjusted",
                    round(current_snow, 2),
                    "mm",
                )
            else:
                current_snow = measured_snow
        modeled_snow_depth = current_snow
        water_temp = regulate_water_temp(TARGET_WATER_TEMP)

        env["snow_depth"] = current_snow
        env["snow_bin_idx"] = snow_idx
        env["angle_bin_idx"] = angle_idx
        env["angle_deg"] = target_ang
        env["water_temp_C"] = water_temp
        env["env_bin"] = env_bin

        if now - last_sample_time >= 10:
            recorder.capture_sample(
                env,
                elapsed,
                water_temp,
                test_meta={
                    "test_no": test_no,
                    "test_day": day_key,
                    "test_type": "tilted",
                    "angle_deg": target_ang,
                },
            )
            pump_Wh_now, heater_Wh_now = get_energy_totals_Wh()
            print(
                "Tilted test status @",
                round(elapsed, 1),
                "s -> TEST #",
                test_no,
                "(repetition #{}), angle =".format(repetition_count + 1),
                target_ang,
                "deg, snow depth =",
                round(current_snow, 2),
                "mm (melted",
                round(start_snow_depth - current_snow, 2),
                "mm), env_bin =",
                env_bin,
                "air =",
                env.get("air_temp"),
                "°C, humidity =",
                env.get("humidity"),
                "%, wind =",
                env.get("wind_speed"),
                "m/s @",
                env.get("wind_dir"),
                "deg, water temp =",
                round(water_temp, 2),
                "°C, pump Wh =",
                round(pump_Wh_now - pump_Wh_start, 3),
                "heater Wh =",
                round(heater_Wh_now - heater_Wh_start, 3),
            )
            last_sample_time = now
            print("Tilted test -> sample captured at", round(elapsed, 1), "s")

        if now - last_log_time >= 30:
            extra_prog = {
                "test_type": "tilted",
                "test_run_id": test_id,
                "elapsed_s": elapsed,
            }
            log_event("TILTED_PROGRESS", env, extra_prog)
            last_log_time = now
            print("Tilted test -> progress log at", round(elapsed, 1), "s")

        if current_snow <= SNOW_CLEAR_THRESHOLD:
            end_reason = "snow depth {} mm <= clear threshold {} mm".format(
                round(current_snow, 2), SNOW_CLEAR_THRESHOLD
            )
            print("Snow melted (depth <= {} mm). Ending test.".format(SNOW_CLEAR_THRESHOLD))
            time_to_clear_s = elapsed
            break

        if elapsed > MAX_TEST_DURATION_S:
            end_reason = "max duration {} s reached".format(MAX_TEST_DURATION_S)
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
        "test_no": test_no,
        "test_day": day_key,
        "snow_bin_idx": snow_idx,
        "angle_bin_idx": angle_idx,
        "angle_deg": target_ang,
        "duration_s": total_dur,
        "snow_depth": current_snow,
        "time_to_clear_s": time_to_clear_s,
        "depth_melted_mm": max(start_snow_depth - current_snow, 0.0),
        "pump_Wh": pump_Wh_used,
        "heater_Wh": heater_Wh_used,
        "end_reason": end_reason,
    }
    log_event("TILTED_END", env, extra_end)

    end_msg = "TILTED TEST END -> TEST #{} ANGLE {} DEG".format(test_no, target_ang)
    if time_to_clear_s is not None:
        end_msg += " | melt_time_s = {:.1f}".format(time_to_clear_s)
        end_msg += " | depth_melted_mm = {:.2f}".format(
            max(start_snow_depth - current_snow, 0.0)
        )
    end_msg += " | duration_s = {:.1f}".format(total_dur)
    if end_reason:
        end_msg += " | end_reason = {}".format(end_reason)
    print(end_msg)
    print("===== END TILTED TEST =====\n")

    recorder.finalize()

    return recorder


def run_energy_test(env):
    """Run a non-tilted energy delivery test when there is no snow."""
    EMBEDDED_CLEAR_TEMP_C = 1.0
    MAX_TEST_DUR = 15 * 60  # 15 minutes

    print("\n===== BEGIN ENERGY TEST =====")
    air_temp = env["air_temp"]
    humidity = env["humidity"]
    wind_speed = env["wind_speed"]
    wind_dir = env["wind_dir"]

    combo_key = bin_non_tilt_env(air_temp, humidity, wind_speed, wind_dir)
    env["env_bin"] = combo_key
    day_key, test_no = get_next_daily_test_number()

    target_temp, flow_level, occur = get_adjusted_temp_and_flow_for_combo(combo_key)

    combo_str = "({}, {}, {}, {})".format(*combo_key)

    test_id = "{}_test{}_energy_{}".format(
        day_key, test_no, combo_str.replace(" ", "")
    )

    extra_start = {
        "test_type": "energy",
        "test_run_id": test_id,
        "test_no": test_no,
        "test_day": day_key,
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

    print(
        "ENERGY TEST START -> TEST #{} ANGLE {} DEG | env_bin {}".format(
            test_no, NON_TILTED_ANGLE_DEG, combo_key
        )
    )
    print("  env bins:", combo_key, "occurrence #", occur)
    print("  target_temp_C =", target_temp, "  flow_level =", flow_level)

    set_non_tilt_angle()

    ensure_supply_hot(target_temp)

    set_flow_level(flow_level)

    pump_Wh_start, heater_Wh_start = get_energy_totals_Wh()

    set_pump_state(True)
    print("Energy test -> pump on")

    start = time.time()

    recorder = SampleRecorder(test_id)
    last_sample = start
    last_log = start
    avg_embedded_temp = None
    time_to_clear_s = None
    last_return_temp = None
    end_reason = None

    while True:
        now = time.time()
        elapsed = now - start
        water_temp = regulate_water_temp(target_temp)
        print("Energy test -> sensor loop elapsed", round(elapsed, 1), "s", "water temp=", water_temp)

        extra_prog = {
            "test_type": "energy",
            "test_run_id": test_id,
            "elapsed_s": elapsed,
            "combo_occurrence": occur,
            "target_temp_C": round(target_temp, 2),
            "target_flow_level": round(flow_level, 3),
            "water_temp_C": water_temp,
            "avg_embedded_temp_C": avg_embedded_temp,
        }
        log_event("ENERGY_PROGRESS", env, extra_prog)

        if now - last_sample >= 10:
            sample = recorder.capture_sample(
                env,
                elapsed,
                water_temp,
                test_meta={
                    "test_no": test_no,
                    "test_day": day_key,
                    "test_type": "energy",
                    "angle_deg": NON_TILTED_ANGLE_DEG,
                },
            )
            last_return_temp = sample.get("return_temp_C")
            embedded = [t for t in sample.get("embedded_temps_C", []) if t is not None]
            avg_embedded_temp = sum(embedded) / len(embedded) if embedded else None
            last_sample = now
            print(
                "Energy test -> TEST #",
                test_no,
                "sample captured at",
                round(elapsed, 1),
                "s; env_bin =",
                combo_key,
                "avg embedded temp =",
                round(avg_embedded_temp, 3) if avg_embedded_temp is not None else None,
                "°C; return temp =",
                last_return_temp,
                "°C",
            )

        if avg_embedded_temp is not None and avg_embedded_temp <= EMBEDDED_CLEAR_TEMP_C:
            time_to_clear_s = elapsed
            end_reason = "avg embedded temp {}°C <= {}°C threshold".format(
                round(avg_embedded_temp, 3), EMBEDDED_CLEAR_TEMP_C
            )
            print(
                "Embedded avg temp <=",
                EMBEDDED_CLEAR_TEMP_C,
                "°C -> ending energy test after",
                round(elapsed, 1),
                "s",
            )
            break

        if now - last_log >= 30:
            print(
                "Energy test status @",
                round(elapsed, 1),
                "s: avg embedded temp =",
                round(avg_embedded_temp, 3) if avg_embedded_temp is not None else None,
            )
            last_log = now

        if elapsed >= MAX_TEST_DUR:
            end_reason = "max duration {} s reached".format(MAX_TEST_DUR)
            print(
                "Energy test hit max duration of",
                MAX_TEST_DUR,
                "seconds; ending run.",
            )
            break

        time.sleep(10)

    set_pump_state(False)
    print("Energy test -> pump off")

    total_dur = time.time() - start
    pump_Wh_end, heater_Wh_end = get_energy_totals_Wh()
    pump_Wh_used = pump_Wh_end - pump_Wh_start
    heater_Wh_used = heater_Wh_end - heater_Wh_start

    extra_end = {
        "test_type": "energy",
        "test_run_id": test_id,
        "test_no": test_no,
        "test_day": day_key,
        "duration_s": total_dur,
        "time_to_clear_s": time_to_clear_s,
        "combo_occurrence": occur,
        "target_temp_C": round(target_temp, 2),
        "target_flow_level": round(flow_level, 3),
        "pump_Wh": pump_Wh_used,
        "heater_Wh": heater_Wh_used,
        "end_reason": end_reason,
    }
    log_event("ENERGY_END", env, extra_end)

    end_msg = "ENERGY TEST END -> TEST #{} ANGLE {} DEG".format(
        test_no, NON_TILTED_ANGLE_DEG
    )
    if time_to_clear_s is not None:
        end_msg += " | time_to_clear_s = {:.1f}".format(time_to_clear_s)
    end_msg += " | duration_s = {:.1f}".format(total_dur)
    end_msg += " | return_temp_C = {}".format(last_return_temp)
    if end_reason:
        end_msg += " | end_reason = {}".format(end_reason)
    print(end_msg)
    print("===== END ENERGY TEST =====\n")

    save_state()

    recorder.finalize()

    return recorder
