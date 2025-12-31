"""Run sloped and non-sloped snowmelt tests."""

import os
import time
from typing import Dict

import aurora.config as config
from aurora.actuators.heater import Heater
from aurora.actuators.pump import Pump
from aurora.actuators.tilt import Tilt
from aurora.control import stop_conditions
from aurora.control.thermostat import Thermostat
from aurora.logging import csv_logger
from aurora.logging.uploader import retry_upload
from aurora.sensors.ds18b20 import DS18B20Suite


def angle_for_sloped(count):
    return ((count - 1) % 5) * 10


def target_for_nonsloped(count):
    return config.NON_SLOPED_BASE_C + config.NON_SLOPED_STEP_C * ((count - 1) % config.NON_SLOPED_REPEAT)


def build_run_id(mode, suffix):
    return time.strftime("%Y%m%d_%H%M%S_" + mode + "_" + suffix)


def _tick_sleep(start, interval_s=config.LOG_INTERVAL_S):
    elapsed = time.time() - start
    remaining = interval_s - (elapsed % interval_s)
    time.sleep(max(0, remaining))


def _collect_sample(ultra, tempsuite, ambient, weather_client, roles):
    distances = ultra.read_all()
    depths, depth_avg = ultra.depths()
    temps = tempsuite.read_all(roles)
    pav = temps.get("pavement", [])
    pav_avg = DS18B20Suite.avg(pav)
    fluid_out = temps.get("fluid_out")
    fluid_return = temps.get("fluid_return")
    amb_c, rh = ambient.read()
    wind = weather_client.read() or (None, None, None)
    return {
        "distances": distances,
        "depths": depths,
        "depth_avg": depth_avg,
        "pavements": pav,
        "pav_avg": pav_avg,
        "fluid_out": fluid_out,
        "fluid_return": fluid_return,
        "ambient": amb_c,
        "rh": rh,
        "wind": wind,
    }


def _row(run_id, mode, target, slope_deg, heater_state, pump_state, sample: Dict[str, object], event="", melt_time_s=None, pav_time=None, end_reason=""):
    wind_kmh, wind_deg, wind_card = sample.get("wind", (None, None, None))
    pavements = ((sample.get("pavements") or []) + [None] * 10)[:10]
    distances = ((sample.get("distances") or []) + [None] * 4)[:4]
    depths = ((sample.get("depths") or []) + [None] * 4)[:4]
    return {
        "timestamp_ms": csv_logger.timestamp_ms(),
        "run_id": run_id,
        "mode": mode,
        "target_fluid_c": target,
        "slope_deg": slope_deg,
        "heater_on": 1 if heater_state else 0,
        "pump_on": 1 if pump_state else 0,
        "u1_cm": distances[0],
        "u2_cm": distances[1],
        "u3_cm": distances[2],
        "u4_cm": distances[3],
        "depth1_cm": depths[0],
        "depth2_cm": depths[1],
        "depth3_cm": depths[2],
        "depth4_cm": depths[3],
        "depth_avg_cm": sample.get("depth_avg"),
        "pav1_c": pavements[0],
        "pav2_c": pavements[1],
        "pav3_c": pavements[2],
        "pav4_c": pavements[3],
        "pav5_c": pavements[4],
        "pav6_c": pavements[5],
        "pav7_c": pavements[6],
        "pav8_c": pavements[7],
        "pav9_c": pavements[8],
        "pav10_c": pavements[9],
        "pav_avg_c": sample.get("pav_avg"),
        "fluid_out_c": sample.get("fluid_out"),
        "fluid_return_c": sample.get("fluid_return"),
        "ambient_c": sample.get("ambient"),
        "rh_pct": sample.get("rh"),
        "wind_kmh": wind_kmh,
        "wind_dir_deg": wind_deg,
        "wind_card": wind_card,
        "event": event,
        "melt_time_s": melt_time_s,
        "time_to_pav1c_s": pav_time,
        "end_reason": end_reason,
    }


def _log_snapshot(mode, sample):
    print("\n--- ULTRASONICS ---")
    print("[ULTRA] raw cm:", sample.get("distances"))
    print("[ULTRA] depth cm:", sample.get("depths"), " avg:", sample.get("depth_avg"))
    print("\n--- DS18B20 ---")
    print("[DS] fluid_out:", sample.get("fluid_out"), " fluid_return:", sample.get("fluid_return"), " pav_avg:", sample.get("pav_avg"))
    print("\n--- SHT3X ---")
    print("[SHT] ambient_c:", sample.get("ambient"), " rh:", sample.get("rh"))
    print("\n--- WEATHER ---")
    wind_kmh, wind_deg, wind_card = sample.get("wind", (None, None, None))
    print("[WX] wind:", wind_kmh, " km/h dir:", wind_deg, "(", wind_card, ")")
    print("\n=== DECIDE ===")
    print("[DECIDE] depth_avg_cm:", sample.get("depth_avg"), " threshold:", config.DEPTH_THRESHOLD_CM, " -> mode:", mode)


def run_sloped(count, ultra, tempsuite, ambient, weather_client, heater: Heater, pump: Pump, tilt: Tilt, roles):
    angle = angle_for_sloped(count)
    run_id = build_run_id("sloped", f"angle{angle}")
    target = config.SLOPED_TARGET_FLUID_C
    log_path = os.path.join(config.LOG_DIR, f"{run_id}.csv")
    print("\n=== TEST START (SLOPED) ===")
    print("[RUN] id:", run_id, "| sloped_count:", count, "| angle:", angle, "| target_fluid:", target)
    tilt.set_angle(angle)
    thermostat = Thermostat(heater, target)
    log = csv_logger.CSVLogger(log_path)

    # Preheat
    print("\n--- PREHEAT ---")
    while True:
        sample = _collect_sample(ultra, tempsuite, ambient, weather_client, roles)
        thermostat.update(sample.get("fluid_out"))
        if sample.get("fluid_out") is None and config.ABORT_IF_NO_FLUID:
            print("[ABORT] NO_FLUID_OUT_SENSOR -> heater OFF, pump OFF, end run")
            log.append(_row(run_id, "sloped", target, angle, heater.state, pump.state, sample, event="END", end_reason="NO_FLUID_OUT_SENSOR"))
            log.close()
            return log_path
        if sample.get("fluid_out") is not None and sample.get("fluid_out") >= target:
            break
        time.sleep(1)

    pump.on()
    start = time.time()
    streak = 0
    while True:
        loop_start = time.time()
        sample = _collect_sample(ultra, tempsuite, ambient, weather_client, roles)
        thermostat.update(sample.get("fluid_out"))
        log.append(_row(run_id, "sloped", target, angle, heater.state, pump.state, sample))
        streak, done = stop_conditions.melt_complete(sample.get("depth_avg"), streak)
        print("[TICK] t+%ds depth=%.2f pav=%.2f out=%.2f ret=%.2f amb=%.1f rh=%.0f H=%d P=%d" % (
            int(time.time() - start),
            sample.get("depth_avg") or 0,
            sample.get("pav_avg") or 0,
            sample.get("fluid_out") or 0,
            sample.get("fluid_return") or 0,
            (sample.get("ambient") or 0),
            (sample.get("rh") or 0),
            heater.state,
            pump.state,
        ))
        if done:
            melt_time = int(time.time() - start)
            print("[STOP] melt complete. melt_time_s:", melt_time)
            log.append(_row(run_id, "sloped", target, angle, heater.state, pump.state, sample, event="END", melt_time_s=melt_time, end_reason="MELT_COMPLETE"))
            break
        _tick_sleep(loop_start)

    pump.off()
    heater.off()
    tilt.home_flat()
    log.close()
    retry_upload(log_path)
    return log_path


def run_nonsloped(count, ultra, tempsuite, ambient, weather_client, heater: Heater, pump: Pump, tilt: Tilt, roles):
    target = target_for_nonsloped(count)
    run_id = build_run_id("nonsloped", f"target{int(target)}")
    log_path = os.path.join(config.LOG_DIR, f"{run_id}.csv")
    print("\n=== TEST START (NON-SLOPED) ===")
    print("[RUN] id:", run_id, "| nonsloped_count:", count, "| target_fluid:", target)
    tilt.home_flat()
    thermostat = Thermostat(heater, target)
    log = csv_logger.CSVLogger(log_path)

    # Preheat
    print("\n--- PREHEAT ---")
    while True:
        sample = _collect_sample(ultra, tempsuite, ambient, weather_client, roles)
        thermostat.update(sample.get("fluid_out"))
        if sample.get("fluid_out") is None and config.ABORT_IF_NO_FLUID:
            print("[ABORT] NO_FLUID_OUT_SENSOR -> heater OFF, pump OFF, end run")
            log.append(_row(run_id, "nonsloped", target, 0, heater.state, pump.state, sample, event="END", end_reason="NO_FLUID_OUT_SENSOR"))
            log.close()
            return log_path
        if sample.get("fluid_out") is not None and sample.get("fluid_out") >= target:
            break
        time.sleep(1)

    pump.on()
    start = time.time()
    streak = 0
    while True:
        loop_start = time.time()
        sample = _collect_sample(ultra, tempsuite, ambient, weather_client, roles)
        thermostat.update(sample.get("fluid_out"))
        log.append(_row(run_id, "nonsloped", target, 0, heater.state, pump.state, sample))
        streak, done = stop_conditions.pavement_ready(sample.get("pav_avg"), streak)
        print("[TICK] t+%ds depth=%.2f pav=%.2f out=%.2f ret=%.2f amb=%.1f rh=%.0f H=%d P=%d" % (
            int(time.time() - start),
            sample.get("depth_avg") or 0,
            sample.get("pav_avg") or 0,
            sample.get("fluid_out") or 0,
            sample.get("fluid_return") or 0,
            (sample.get("ambient") or 0),
            (sample.get("rh") or 0),
            heater.state,
            pump.state,
        ))
        if done:
            pav_time = int(time.time() - start)
            print("[STOP] pav target reached. time_to_pav1c_s:", pav_time)
            log.append(_row(run_id, "nonsloped", target, 0, heater.state, pump.state, sample, event="END", pav_time=pav_time, end_reason="PAVEMENT_WARM"))
            break
        _tick_sleep(loop_start)

    pump.off()
    heater.off()
    log.close()
    retry_upload(log_path)
    return log_path
