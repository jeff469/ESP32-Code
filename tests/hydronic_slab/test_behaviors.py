import csv
import os
import random
import time
import ujson

import pytest

from tests.hydronic_slab import state


class FakeTime:
    def __init__(self):
        self.current = 0.0

    def time(self):
        return self.current

    def sleep(self, seconds):
        self.current += seconds

    def localtime(self, *args, **kwargs):
        """Mirror ``time.localtime`` using the fake clock."""

        return time.localtime(self.current)


class FakeRecorder:
    def __init__(self, test_id):
        self.test_id = test_id
        self.samples = []
        self.finalized = False

    def capture_sample(self, env, elapsed_s, water_temp_C=None, test_meta=None):
        sample = {
            "elapsed_s": elapsed_s,
            "embedded_temps_C": env.get("embedded_temps_C", []),
            "water_temp_C": water_temp_C,
        }
        self.samples.append(sample)
        return sample

    def finalize(self):
        self.finalized = True


class EmbeddedFakeRecorder(FakeRecorder):
    """Recorder that returns a fixed embedded-temperature set for fast exits."""

    def __init__(self, test_id, embedded_temp=0.5):
        super().__init__(test_id)
        self.embedded_temp = embedded_temp

    def capture_sample(self, env, elapsed_s, water_temp_C=None, test_meta=None):
        sample = {
            "elapsed_s": elapsed_s,
            "embedded_temps_C": [self.embedded_temp for _ in range(9)],
            "water_temp_C": water_temp_C,
        }
        self.samples.append(sample)
        return sample


def test_is_snow_present_respects_threshold():
    assert not state.is_snow_present(state.SNOW_PRESENT_THRESHOLD - 0.1)
    assert state.is_snow_present(state.SNOW_PRESENT_THRESHOLD)


def test_sample_recorder_persists_bin_ids(monkeypatch, tmp_path):
    from tests.hydronic_slab import data_recorder
    from tests.hydronic_slab import event_logger

    rng = random.Random(123)

    log_dir = tmp_path / "logs"
    monkeypatch.setattr(state, "LOG_DIR", str(log_dir))
    monkeypatch.setattr(data_recorder, "LOG_DIR", str(log_dir))
    monkeypatch.setattr(event_logger, "LOG_FILE", str(log_dir / "events.csv"), raising=False)

    monkeypatch.setattr(event_logger, "ensure_log_dir", lambda: os.makedirs(log_dir, exist_ok=True))
    monkeypatch.setattr(data_recorder, "ensure_log_dir", lambda: os.makedirs(log_dir, exist_ok=True))

    monkeypatch.setattr(
        data_recorder,
        "request_embedded_thermometer_temps_C",
        lambda expected=9: [round(rng.uniform(25.0, 35.0), 1) for _ in range(expected)],
    )
    monkeypatch.setattr(
        data_recorder,
        "request_return_water_temp_C",
        lambda: round(rng.uniform(20.0, 35.0), 1),
    )
    monkeypatch.setattr(
        data_recorder,
        "request_bin_id_states",
        lambda expected=4: [rng.choice([0, 1]) for _ in range(expected)],
    )
    monkeypatch.setattr(
        data_recorder,
        "measure_all_snow_depths_mm",
        lambda: [round(rng.uniform(1.0, 5.0), 1) for _ in range(3)],
    )

    recorder = data_recorder.SampleRecorder("sample_test")
    env = {"air_temp": -5.0, "humidity": 70.0, "wind_speed": 2.5, "wind_dir": 90.0, "snow_depth": 3.1}

    recorder.capture_sample(env, elapsed_s=12.3, water_temp_C=32.1)
    csv_path = recorder.save_excel_friendly_csv()

    assert csv_path is not None
    with open(csv_path, "r") as f:
        rows = list(csv.reader(f))

    assert len(rows) == 2
    header, sample = rows
    assert "embedded_temps_C" in header

    row = dict(zip(header, sample))
    embedded = ujson.loads(row["embedded_temps_C"])
    snow_depths = ujson.loads(row["snow_depths_mm"])
    bin_ids = ujson.loads(row["bin_ids"])

    assert len(embedded) == 9
    assert len(snow_depths) == 3
    assert len(bin_ids) == 4

    embedded_labels = [
        "embedded_temp_A_C",
        "embedded_temp_B_C",
        "embedded_temp_C_C",
        "embedded_temp_D_C",
        "embedded_temp_E_C",
        "embedded_temp_F_C",
        "embedded_temp_G_C",
        "embedded_temp_H_C",
        "embedded_temp_I_C",
    ]

    for idx, label in enumerate(embedded_labels):
        assert float(row[label]) == embedded[idx]


def test_energy_occurrence_counts_persist(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(state, "STATE_FILE", "state.json")
    state.combo_counts.clear()
    state.init_tilt_coverage()

    key = (1, 2, 3, 4)
    _, _, occurrence1 = state.get_adjusted_temp_and_flow_for_combo(key)
    _, _, occurrence2 = state.get_adjusted_temp_and_flow_for_combo(key)
    assert occurrence1 == 1
    assert occurrence2 == 2

    state.save_state()
    state.combo_counts.clear()
    state.load_state()
    assert state.combo_counts[key] == 2


def test_energy_occurrence_survives_power_cycle(monkeypatch, tmp_path):
    from tests.hydronic_slab import test_routines, thermostat

    monkeypatch.chdir(tmp_path)
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(state, "STATE_FILE", "state.json")

    fake_time = FakeTime()
    for module in (test_routines, thermostat):
        monkeypatch.setattr(module, "time", fake_time)

    state.combo_counts.clear()
    state.init_tilt_coverage()
    monkeypatch.setattr(state, "_last_energy_update_time", fake_time.time())

    monkeypatch.setattr(test_routines, "ensure_supply_hot", lambda target: None)
    monkeypatch.setattr(test_routines, "set_flow_level", lambda level: None)
    monkeypatch.setattr(test_routines, "set_non_tilt_angle", lambda: None)
    monkeypatch.setattr(test_routines, "set_pump_state", lambda on: None)
    monkeypatch.setattr(test_routines, "get_energy_totals_Wh", lambda: (0.0, 0.0))
    monkeypatch.setattr(test_routines, "log_event", lambda *_, **__: None)
    monkeypatch.setattr(test_routines, "regulate_water_temp", lambda target: target)

    monkeypatch.setattr(test_routines, "SampleRecorder", lambda test_id: EmbeddedFakeRecorder(test_id))

    env = {
        "air_temp": -5.0,
        "humidity": 60.0,
        "wind_speed": 3.0,
        "wind_dir": 90.0,
        "snow_depth": 0.0,
    }
    combo_key = state.bin_non_tilt_env(
        env["air_temp"], env["humidity"], env["wind_speed"], env["wind_dir"]
    )

    first_recorder = test_routines.run_energy_test(dict(env))
    assert first_recorder.finalized
    assert os.path.exists(state.STATE_FILE)
    assert state.combo_counts[combo_key] == 1

    state.combo_counts.clear()
    state.init_tilt_coverage()
    state.load_state()
    assert state.combo_counts[combo_key] == 1

    second_recorder = test_routines.run_energy_test(dict(env))
    assert second_recorder.finalized
    assert state.combo_counts[combo_key] == 2


def test_power_use_estimator_tracks_pump_and_heater(monkeypatch):
    fake_time = FakeTime()
    monkeypatch.setattr(state, "time", fake_time)
    monkeypatch.setattr(state, "pump_on", lambda: None)
    monkeypatch.setattr(state, "pump_off", lambda: None)
    monkeypatch.setattr(state, "heater_on", lambda: None)
    monkeypatch.setattr(state, "heater_off", lambda: None)

    monkeypatch.setattr(state, "pump_energy_Wh_total", 0.0)
    monkeypatch.setattr(state, "heater_energy_Wh_total", 0.0)
    monkeypatch.setattr(state, "pump_is_on", False)
    monkeypatch.setattr(state, "heater_is_on", False)
    monkeypatch.setattr(state, "_last_energy_update_time", fake_time.time())

    state.set_pump_state(True)
    fake_time.sleep(1800)  # pump on for 30 minutes

    state.set_heater_state(True)
    fake_time.sleep(900)  # pump + heater on for 15 minutes

    pump_Wh, heater_Wh = state.get_energy_totals_Wh()

    assert pump_Wh == pytest.approx(state.PUMP_POWER_W * (1800 + 900) / 3600.0, rel=1e-3)
    assert heater_Wh == pytest.approx(state.HEATER_POWER_W * 900 / 3600.0, rel=1e-3)


def test_energy_test_stops_when_embedded_hits_one(monkeypatch, tmp_path):
    from tests.hydronic_slab import data_recorder, event_logger, test_routines, thermostat

    fake_time = FakeTime()

    for module in (test_routines, thermostat, data_recorder):
        monkeypatch.setattr(module, "time", fake_time)

    log_dir = tmp_path / "logs"
    monkeypatch.setattr(state, "LOG_DIR", str(log_dir))
    monkeypatch.setattr(data_recorder, "LOG_DIR", str(log_dir))
    monkeypatch.setattr(event_logger, "LOG_FILE", str(log_dir / "events.csv"), raising=False)
    monkeypatch.setattr(event_logger, "ensure_log_dir", lambda: os.makedirs(log_dir, exist_ok=True))
    monkeypatch.setattr(data_recorder, "ensure_log_dir", lambda: os.makedirs(log_dir, exist_ok=True))

    monkeypatch.setattr(test_routines, "ensure_supply_hot", lambda target: None)
    monkeypatch.setattr(test_routines, "set_flow_level", lambda level: None)
    monkeypatch.setattr(test_routines, "set_non_tilt_angle", lambda: None)
    monkeypatch.setattr(test_routines, "set_pump_state", lambda on: None)
    monkeypatch.setattr(test_routines, "log_event", lambda *_, **__: None)
    monkeypatch.setattr(test_routines, "get_energy_totals_Wh", lambda: (0.0, 0.0))
    monkeypatch.setattr(test_routines, "regulate_water_temp", lambda target: target)

    monkeypatch.setattr(state, "_last_energy_update_time", fake_time.time())

    embedded_sequences = iter(
        [
            [5.0 for _ in range(9)],
            [2.0 for _ in range(9)],
            [0.5 for _ in range(9)],
        ]
    )

    def embedded_source(expected=9):
        try:
            vals = next(embedded_sequences)
        except StopIteration:
            vals = [0.5 for _ in range(expected)]
        return vals

    monkeypatch.setattr(data_recorder, "request_embedded_thermometer_temps_C", embedded_source)
    monkeypatch.setattr(data_recorder, "request_return_water_temp_C", lambda: 10.0)
    monkeypatch.setattr(data_recorder, "request_bin_id_states", lambda expected=4: [0, 0, 0, 0])
    monkeypatch.setattr(data_recorder, "measure_all_snow_depths_mm", lambda: [0.0, 0.0, 0.0])

    env = {"air_temp": 2.0, "humidity": 40.0, "wind_speed": 1.5, "wind_dir": 90.0, "snow_depth": 0.0}

    recorder = test_routines.run_energy_test(env)

    assert len(recorder.samples) == 3
    avg_last = sum(recorder.samples[-1]["embedded_temps_C"]) / 9
    assert avg_last <= 1.0
    assert fake_time.time() >= 30.0

def test_tilted_test_samples_every_ten_seconds(monkeypatch):
    from tests.hydronic_slab import test_routines, thermostat

    state.init_tilt_coverage()

    fake_time = FakeTime()
    monkeypatch.setattr(test_routines, "time", fake_time)
    monkeypatch.setattr(thermostat, "time", fake_time)
    monkeypatch.setattr(state, "_last_energy_update_time", fake_time.time())

    monkeypatch.setattr(test_routines, "regulate_water_temp", lambda target: target)
    monkeypatch.setattr(test_routines, "SampleRecorder", FakeRecorder)

    monkeypatch.setattr(state, "SNOW_PRESENT_THRESHOLD", 5.0)
    monkeypatch.setattr(state, "get_energy_totals_Wh", lambda: (0.0, 0.0))
    monkeypatch.setattr(test_routines, "set_pump_state", lambda on: None)
    monkeypatch.setattr(test_routines, "ensure_supply_hot", lambda target: None)
    monkeypatch.setattr(test_routines, "set_target_angle", lambda ang: None)
    monkeypatch.setattr(state, "save_state", lambda: None)
    monkeypatch.setattr(test_routines, "mark_angle_tested", lambda s, a: None)
    monkeypatch.setattr(test_routines, "log_event", lambda *_, **__: None)

    rng = random.Random(321)
    snow_values = [rng.uniform(12.0, 35.0) for _ in range(12)] + [0.0]
    snow_sequence = iter(snow_values)
    monkeypatch.setattr(test_routines, "measure_snow_depth_mm", lambda: next(snow_sequence))

    env = {"snow_depth": 20.0, "air_temp": -1, "humidity": 50, "wind_speed": 2, "wind_dir": 90}
    recorder = test_routines.run_tilted_test(env)

    assert isinstance(recorder, FakeRecorder)
    assert [sample["elapsed_s"] for sample in recorder.samples] == [
        10.0,
        20.0,
        30.0,
        40.0,
        50.0,
        60.0,
    ]


def test_tilted_test_stops_once_snow_within_clear_threshold(monkeypatch):
    from tests.hydronic_slab import test_routines, thermostat

    state.init_tilt_coverage()

    fake_time = FakeTime()
    monkeypatch.setattr(test_routines, "time", fake_time)
    monkeypatch.setattr(thermostat, "time", fake_time)
    monkeypatch.setattr(state, "_last_energy_update_time", fake_time.time())

    snow_sequence = iter([5.0, 1.2, 0.9, 0.5])
    monkeypatch.setattr(test_routines, "measure_snow_depth_mm", lambda: next(snow_sequence))

    monkeypatch.setattr(test_routines, "regulate_water_temp", lambda target: target)
    monkeypatch.setattr(test_routines, "SampleRecorder", FakeRecorder)
    monkeypatch.setattr(state, "get_energy_totals_Wh", lambda: (0.0, 0.0))
    monkeypatch.setattr(test_routines, "set_pump_state", lambda on: None)
    monkeypatch.setattr(test_routines, "ensure_supply_hot", lambda target: None)
    monkeypatch.setattr(test_routines, "set_target_angle", lambda ang: None)
    monkeypatch.setattr(state, "save_state", lambda: None)
    monkeypatch.setattr(test_routines, "mark_angle_tested", lambda s, a: None)
    monkeypatch.setattr(test_routines, "log_event", lambda *_, **__: None)

    env = {"snow_depth": 5.0, "air_temp": -1, "humidity": 50, "wind_speed": 2, "wind_dir": 90}
    recorder = test_routines.run_tilted_test(env)

    # Final measurement within the clear threshold should end the loop without requiring zero.
    assert env["snow_depth"] == 0.9
    assert [sample["elapsed_s"] for sample in recorder.samples] == [10.0]


def test_main_routes_tests_by_snow(monkeypatch):
    from tests.hydronic_slab import main

    calls = []

    class StopCycle(Exception):
        pass

    def fake_run_tilted(env):
        calls.append(("tilted", env["snow_depth"]))
        raise StopCycle

    def fake_run_energy(env):
        calls.append(("energy", env["snow_depth"]))
        raise StopCycle

    monkeypatch.setattr(main, "run_tilted_test", fake_run_tilted)
    monkeypatch.setattr(main, "run_energy_test", fake_run_energy)
    monkeypatch.setattr(main, "measure_snow_depth_mm", lambda: 10.0)
    monkeypatch.setattr(main, "read_air_temperature_C", lambda: -2.0)
    monkeypatch.setattr(main, "read_relative_humidity", lambda: 60.0)
    monkeypatch.setattr(main, "read_wind_speed_mps", lambda: 1.2)
    monkeypatch.setattr(main, "read_wind_direction_deg", lambda: 45.0)
    monkeypatch.setattr(main, "is_snow_present", lambda depth: depth >= 5.0)

    with pytest.raises(StopCycle):
        main.main(cycle_period_s=0)
    assert calls[0][0] == "tilted"

    calls.clear()
    monkeypatch.setattr(main, "measure_snow_depth_mm", lambda: 1.0)
    with pytest.raises(StopCycle):
        main.main(cycle_period_s=0)
    assert calls[0][0] == "energy"


def test_randomized_energy_runs_increment_occurrence(monkeypatch, tmp_path):
    from tests.hydronic_slab import main, test_routines, thermostat

    rng = random.Random(987)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(state, "STATE_FILE", "state.json")
    state.combo_counts.clear()
    state.init_tilt_coverage()

    fake_time = FakeTime()
    monkeypatch.setattr(test_routines, "time", fake_time)
    monkeypatch.setattr(thermostat, "time", fake_time)
    monkeypatch.setattr(state, "_last_energy_update_time", fake_time.time())

    monkeypatch.setattr(test_routines, "ensure_supply_hot", lambda target: None)
    monkeypatch.setattr(test_routines, "set_flow_level", lambda level: None)
    monkeypatch.setattr(test_routines, "set_non_tilt_angle", lambda: None)
    monkeypatch.setattr(test_routines, "set_pump_state", lambda on: None)
    monkeypatch.setattr(test_routines, "get_energy_totals_Wh", lambda: (0.0, 0.0))
    monkeypatch.setattr(test_routines, "log_event", lambda *_, **__: None)
    monkeypatch.setattr(state, "save_state", lambda: None)
    monkeypatch.setattr(test_routines, "time", fake_time)
    monkeypatch.setattr(test_routines, "SampleRecorder", FakeRecorder)
    monkeypatch.setattr(test_routines, "regulate_water_temp", lambda target: target)

    def random_env():
        return {
            "air_temp": rng.uniform(-9.9, -9.8),
            "humidity": rng.uniform(45.0, 49.0),
            "wind_speed": rng.uniform(2.1, 2.4),
            "wind_dir": rng.uniform(88.0, 92.0),
        }

    recorders = []
    for _ in range(3):
        env = random_env()
        recorder = test_routines.run_energy_test(env)
        recorders.append(recorder)

    combo_key = state.bin_non_tilt_env(-10.0, 47.0, 2.0, 90.0)
    assert state.combo_counts[combo_key] == 3
    assert all(isinstance(rec, FakeRecorder) for rec in recorders)


def test_tilted_runs_progress_angle_bins(monkeypatch):
    from tests.hydronic_slab import test_routines, thermostat

    fake_time = FakeTime()
    monkeypatch.setattr(test_routines, "time", fake_time)
    monkeypatch.setattr(thermostat, "time", fake_time)
    monkeypatch.setattr(state, "_last_energy_update_time", fake_time.time())

    # Shrink the angle bins for quick progression checks and reset coverage.
    custom_angles = [0, 10, 20, 30, 40]
    monkeypatch.setattr(state, "ANGLE_BINS", custom_angles, raising=False)
    monkeypatch.setattr(test_routines, "ANGLE_BINS", custom_angles, raising=False)
    state.init_tilt_coverage()

    monkeypatch.setattr(test_routines, "ensure_supply_hot", lambda target: None)
    monkeypatch.setattr(test_routines, "get_energy_totals_Wh", lambda: (0.0, 0.0))
    monkeypatch.setattr(test_routines, "set_pump_state", lambda on: None)
    monkeypatch.setattr(test_routines, "regulate_water_temp", lambda target: target)
    monkeypatch.setattr(test_routines, "log_event", lambda *_, **__: None)
    monkeypatch.setattr(state, "save_state", lambda: None)

    target_angles = []
    monkeypatch.setattr(test_routines, "set_target_angle", lambda ang: target_angles.append(ang))
    monkeypatch.setattr(test_routines, "SampleRecorder", FakeRecorder)

    def run_once(depth_sequence):
        seq = iter(depth_sequence)
        monkeypatch.setattr(test_routines, "measure_snow_depth_mm", lambda: next(seq))
        env = {"snow_depth": 25.0, "air_temp": -5, "humidity": 50, "wind_speed": 3, "wind_dir": 90}
        test_routines.run_tilted_test(env)

    run_once([25.0, 0.0])
    run_once([26.0, 0.0])
    run_once([27.0, 0.0])
    run_once([28.0, 0.0])
    run_once([29.0, 0.0])

    assert target_angles == [0, 10, 20, 30, 40]


def test_thermostat_switches_modes(monkeypatch):
    from tests.hydronic_slab import thermostat

    actions = []

    monkeypatch.setattr(thermostat, "request_water_temp_C", lambda: -5.0)
    monkeypatch.setattr(
        thermostat,
        "set_heater_state",
        lambda on: actions.append("heater_on" if on else "heater_off"),
    )
    monkeypatch.setattr(thermostat, "solA_open", lambda: actions.append("solA_open"))
    monkeypatch.setattr(thermostat, "solA_close", lambda: actions.append("solA_close"))
    monkeypatch.setattr(thermostat, "solB_open", lambda: actions.append("solB_open"))
    monkeypatch.setattr(thermostat, "solB_close", lambda: actions.append("solB_close"))

    thermostat._last_mode = None
    assert thermostat.regulate_water_temp(5.0, deadband_C=1.0) == -5.0
    assert actions == ["solA_close", "solB_open", "heater_on"]

    actions.clear()
    monkeypatch.setattr(thermostat, "request_water_temp_C", lambda: 8.0)
    assert thermostat.regulate_water_temp(5.0, deadband_C=1.0) == 8.0
    assert actions == ["solB_close", "solA_open", "heater_off"]


def test_two_hour_simulation_produces_six_tests(monkeypatch, tmp_path):
    from tests.hydronic_slab import (
        communication,
        data_recorder,
        event_logger,
        main,
        test_routines,
        thermostat,
    )

    fake_time = FakeTime()

    for module in (state, main, test_routines, thermostat, data_recorder, event_logger):
        monkeypatch.setattr(module, "time", fake_time)

    log_dir = tmp_path / "logs"
    monkeypatch.setattr(state, "STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(state, "LOG_DIR", str(log_dir))
    monkeypatch.setattr(data_recorder, "LOG_DIR", str(log_dir))
    monkeypatch.setattr(event_logger, "LOG_FILE", str(log_dir / "events.csv"), raising=False)
    monkeypatch.setattr(event_logger, "ensure_log_dir", lambda: os.makedirs(log_dir, exist_ok=True))
    monkeypatch.setattr(data_recorder, "ensure_log_dir", lambda: os.makedirs(log_dir, exist_ok=True))

    rng = random.Random(4242)

    monkeypatch.setattr(state, "_last_energy_update_time", fake_time.time())
    monkeypatch.setattr(state, "save_state", lambda: None)
    monkeypatch.setattr(state, "load_state", lambda: None)
    state.init_tilt_coverage()
    state.combo_counts.clear()

    monkeypatch.setattr(state, "pump_on", lambda: print("pump_on()"))
    monkeypatch.setattr(state, "pump_off", lambda: print("pump_off()"))
    monkeypatch.setattr(state, "heater_on", lambda: print("heater_on()"))
    monkeypatch.setattr(state, "heater_off", lambda: print("heater_off()"))

    monkeypatch.setattr(test_routines, "ensure_supply_hot", lambda target: print("ensure_supply_hot ->", target))
    monkeypatch.setattr(test_routines, "set_flow_level", lambda level: print("set_flow_level ->", level))
    monkeypatch.setattr(test_routines, "set_target_angle", lambda ang: print("set_target_angle ->", ang))
    monkeypatch.setattr(test_routines, "set_non_tilt_angle", lambda: print("set_non_tilt_angle()"))

    monkeypatch.setattr(communication, "send_command_to_mega", lambda cmd: print("-> MEGA (stub):", cmd))
    monkeypatch.setattr(main, "actuators_stop", lambda: print("actuators_stop()"))
    monkeypatch.setattr(test_routines, "mark_angle_tested", lambda *_: None)

    def temp_source():
        while True:
            yield round(32.0 + rng.uniform(-6.0, 4.0), 2)

    temps = temp_source()
    monkeypatch.setattr(thermostat, "request_water_temp_C", lambda: next(temps))

    monkeypatch.setattr(
        data_recorder,
        "request_embedded_thermometer_temps_C",
        lambda expected=9: [round(30.0 + rng.uniform(-3.0, 3.0), 2) for _ in range(expected)],
    )
    monkeypatch.setattr(
        data_recorder,
        "request_return_water_temp_C",
        lambda: round(28.0 + rng.uniform(-4.0, 4.0), 2),
    )
    monkeypatch.setattr(
        data_recorder,
        "request_bin_id_states",
        lambda expected=4: [rng.randint(0, 1) for _ in range(expected)],
    )
    monkeypatch.setattr(
        data_recorder,
        "measure_all_snow_depths_mm",
        lambda: [round(rng.uniform(0.5, 12.0), 2) for _ in range(3)],
    )

    snow_cycle = iter([30.0, 0.0, 22.0, 0.0, 8.0, 15.0])
    air_cycle = iter([-5.0, -4.0, -6.0, -3.0, -2.0, -7.0])
    humidity_cycle = iter([60.0, 55.0, 65.0, 50.0, 52.0, 70.0])
    wind_speed_cycle = iter([3.0, 2.0, 4.0, 3.5, 2.2, 3.8])
    wind_dir_cycle = iter([90.0, 100.0, 80.0, 110.0, 95.0, 85.0])

    monkeypatch.setattr(main, "measure_snow_depth_mm", lambda: next(snow_cycle))
    monkeypatch.setattr(main, "read_air_temperature_C", lambda: next(air_cycle))
    monkeypatch.setattr(main, "read_relative_humidity", lambda: next(humidity_cycle))
    monkeypatch.setattr(main, "read_wind_speed_mps", lambda: next(wind_speed_cycle))
    monkeypatch.setattr(main, "read_wind_direction_deg", lambda: next(wind_dir_cycle))
    monkeypatch.setattr(main, "request_slab_angle_deg", lambda: 0.0)

    tilt_sequences = [
        iter([30.0, 24.0, 18.0, 12.0, 6.0, 2.0, 0.0]),
        iter([22.0, 16.0, 9.0, 4.0, 0.0]),
        iter([8.0, 5.0, 2.0, 0.0]),
        iter([15.0, 11.0, 6.0, 0.0]),
    ]
    tilt_iter = iter(tilt_sequences)

    original_run_tilted = test_routines.run_tilted_test

    def run_tilted_with_sequence(env):
        seq = next(tilt_iter)
        monkeypatch.setattr(test_routines, "measure_snow_depth_mm", lambda: next(seq))
        return original_run_tilted(env)

    monkeypatch.setattr(main, "run_tilted_test", run_tilted_with_sequence)

    fake_time.sleep(0)

    main.main(cycle_period_s=20 * 60, max_cycles=6)

    csv_files = list(log_dir.glob("*_samples.csv"))
    assert len(csv_files) == 6

    pump_Wh, heater_Wh = state.get_energy_totals_Wh()
    assert pump_Wh > 0
    assert heater_Wh > 0

    assert fake_time.time() >= 6 * 20 * 60
