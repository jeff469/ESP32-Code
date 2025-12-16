import csv
import os
import random
import sys
import time
import ujson

import pytest

from contextlib import contextmanager
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


@contextmanager
def trace_hydronic_calls():
    """Print every call into the hydronic slab modules for debugging."""

    def tracer(frame, event, arg):
        if event != "call":
            return tracer

        module = frame.f_globals.get("__name__", "")
        if module.startswith("tests.hydronic_slab"):
            func = frame.f_code.co_name
            print(f"CALL {module}.{func}")

        return tracer

    prev = sys.gettrace()
    sys.settrace(tracer)
    try:
        yield
    finally:
        sys.settrace(prev)


def test_is_snow_present_respects_threshold():
    assert not state.is_snow_present(state.SNOW_PRESENT_THRESHOLD - 0.1)
    assert state.is_snow_present(state.SNOW_PRESENT_THRESHOLD)


def test_call_tracing_prints(monkeypatch, capsys):
    from tests.hydronic_slab import test_routines, thermostat

    fake_time = FakeTime()
    for module in (test_routines, thermostat):
        monkeypatch.setattr(module, "time", fake_time)

    monkeypatch.setattr(test_routines, "bin_non_tilt_env", lambda *_, **__: (0, 0, 0, 0))
    monkeypatch.setattr(test_routines, "get_next_daily_test_number", lambda: ("2024-01-01", 1))
    monkeypatch.setattr(
        test_routines, "get_adjusted_temp_and_flow_for_combo", lambda combo: (5.0, 0.5, 1)
    )
    monkeypatch.setattr(test_routines, "set_non_tilt_angle", lambda: None)
    monkeypatch.setattr(test_routines, "ensure_supply_hot", lambda target: None)
    monkeypatch.setattr(test_routines, "set_flow_level", lambda level: None)
    monkeypatch.setattr(test_routines, "set_pump_state", lambda on: None)
    monkeypatch.setattr(test_routines, "get_energy_totals_Wh", lambda: (0.0, 0.0))
    monkeypatch.setattr(test_routines, "log_event", lambda *_, **__: None)
    monkeypatch.setattr(test_routines, "save_state", lambda: None)
    monkeypatch.setattr(test_routines, "regulate_water_temp", lambda target: target)
    monkeypatch.setattr(
        test_routines,
        "SampleRecorder",
        lambda test_id: EmbeddedFakeRecorder(test_id, embedded_temp=0.5),
    )

    original_capture = EmbeddedFakeRecorder.capture_sample

    def wrapped_capture(self, *args, **kwargs):
        print("CALL tests.hydronic_slab.test_behaviors.EmbeddedFakeRecorder.capture_sample")
        return original_capture(self, *args, **kwargs)

    monkeypatch.setattr(EmbeddedFakeRecorder, "capture_sample", wrapped_capture)

    env = {
        "air_temp": -2.0,
        "humidity": 55.0,
        "wind_speed": 2.0,
        "wind_dir": 90.0,
        "snow_depth": 0.0,
    }

    with trace_hydronic_calls():
        recorder = test_routines.run_energy_test(env)

    output = capsys.readouterr().out
    assert "CALL tests.hydronic_slab.test_routines.run_energy_test" in output
    assert "CALL tests.hydronic_slab.test_behaviors.EmbeddedFakeRecorder.capture_sample" in output
    assert recorder.finalized


def test_sample_recorder_saves_temperatures_without_bin_ids(monkeypatch, tmp_path):
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

    assert len(embedded) == 9
    assert len(snow_depths) == 3
    assert "bin_ids" not in row

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


def test_sample_recorder_fetches_and_saves_weather(monkeypatch, tmp_path):
    from tests.hydronic_slab import data_recorder
    from tests.hydronic_slab import event_logger

    log_dir = tmp_path / "logs"
    monkeypatch.setattr(state, "LOG_DIR", str(log_dir))
    monkeypatch.setattr(data_recorder, "LOG_DIR", str(log_dir))
    monkeypatch.setattr(event_logger, "LOG_FILE", str(log_dir / "events.csv"), raising=False)

    monkeypatch.setattr(event_logger, "ensure_log_dir", lambda: os.makedirs(log_dir, exist_ok=True))
    monkeypatch.setattr(data_recorder, "ensure_log_dir", lambda: os.makedirs(log_dir, exist_ok=True))

    monkeypatch.setattr(data_recorder, "request_embedded_thermometer_temps_C", lambda expected=9: [1.0] * 9)
    monkeypatch.setattr(data_recorder, "request_return_water_temp_C", lambda: 10.0)
    monkeypatch.setattr(data_recorder, "measure_all_snow_depths_mm", lambda: [2.0, 2.0, 2.0])
    monkeypatch.setattr(data_recorder.SampleRecorder, "upload_to_cloud", lambda *_, **__: None)

    weather_payload = {
        "source": "open-meteo",
        "retrieved_at": 1700000000.0,
        "condition": 3,
        "solar_radiation_Wm2": 150.5,
        "air_temp_C": -1.2,
        "humidity_pct": 82.0,
        "wind_speed_mps": 2.3,
        "wind_dir_deg": 210.0,
    }

    recorder = data_recorder.SampleRecorder(
        "weather_test", weather_fetcher=lambda: weather_payload
    )
    env = {"air_temp": -5.0, "humidity": 70.0, "wind_speed": 2.5, "wind_dir": 90.0, "snow_depth": 3.1}

    recorder.capture_sample(env, elapsed_s=1.0, water_temp_C=5.5)
    recorder.finalize()

    sample_csv = tmp_path / "logs" / "weather_test_samples.csv"
    weather_csv = tmp_path / "logs" / "weather_test_weather.csv"

    assert sample_csv.exists()
    assert weather_csv.exists()

    with open(weather_csv, "r") as f:
        rows = list(csv.reader(f))

    assert len(rows) == 2
    header, data = rows
    assert header == [
        "source",
        "retrieved_at",
        "condition",
        "solar_radiation_Wm2",
        "air_temp_C",
        "humidity_pct",
        "wind_speed_mps",
        "wind_dir_deg",
    ]

    weather_row = dict(zip(header, data))
    assert weather_row["source"] == "open-meteo"
    assert float(weather_row["solar_radiation_Wm2"]) == weather_payload["solar_radiation_Wm2"]
    assert float(weather_row["air_temp_C"]) == weather_payload["air_temp_C"]


def test_sample_recorder_uploads_to_configured_endpoint(monkeypatch, tmp_path):
    from tests.hydronic_slab import data_recorder
    from tests.hydronic_slab import event_logger

    log_dir = tmp_path / "logs"
    monkeypatch.setattr(state, "LOG_DIR", str(log_dir))
    monkeypatch.setattr(data_recorder, "LOG_DIR", str(log_dir))
    monkeypatch.setattr(event_logger, "LOG_FILE", str(log_dir / "events.csv"), raising=False)
    monkeypatch.setattr(event_logger, "ensure_log_dir", lambda: os.makedirs(log_dir, exist_ok=True))
    monkeypatch.setattr(data_recorder, "ensure_log_dir", lambda: os.makedirs(log_dir, exist_ok=True))

    monkeypatch.setattr(data_recorder, "request_embedded_thermometer_temps_C", lambda expected=9: [2.0] * 9)
    monkeypatch.setattr(data_recorder, "request_return_water_temp_C", lambda: 12.0)
    monkeypatch.setattr(data_recorder, "measure_all_snow_depths_mm", lambda: [4.0, 5.0, 6.0])

    weather_payload = {
        "source": "open-meteo",
        "retrieved_at": 1700000000.0,
        "condition": 3,
        "solar_radiation_Wm2": 150.5,
        "air_temp_C": -1.2,
        "humidity_pct": 82.0,
        "wind_speed_mps": 2.3,
        "wind_dir_deg": 210.0,
    }

    post_calls = []

    def fake_post(url, files=None, data=None, timeout=None):
        file_tuple = files.get("file")
        post_calls.append(
            {
                "url": url,
                "filename": file_tuple[0],
                "content": file_tuple[1].read().decode(),
                "data": data,
                "timeout": timeout,
            }
        )

        class Resp:
            status_code = 200

            def raise_for_status(self):
                return None

        return Resp()

    recorder = data_recorder.SampleRecorder(
        "upload_test",
        weather_fetcher=lambda: weather_payload,
        upload_url="https://upload.example",
        upload_client=fake_post,
    )

    env = {"air_temp": -5.0, "humidity": 70.0, "wind_speed": 2.5, "wind_dir": 90.0, "snow_depth": 3.1}

    recorder.capture_sample(env, elapsed_s=1.0, water_temp_C=5.5)
    recorder.finalize()

    filenames = {call["filename"] for call in post_calls}
    assert filenames == {"upload_test_samples.csv", "upload_test_weather.csv"}
    assert all(call["url"] == "https://upload.example" for call in post_calls)
    assert all(call["data"]["test_id"] == "upload_test" for call in post_calls)


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
    events = []

    def capture_event(name, env_data, extra=None):
        events.append((name, extra or {}))

    monkeypatch.setattr(test_routines, "log_event", capture_event)
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
    monkeypatch.setattr(data_recorder, "measure_all_snow_depths_mm", lambda: [0.0, 0.0, 0.0])

    env = {"air_temp": 2.0, "humidity": 40.0, "wind_speed": 1.5, "wind_dir": 90.0, "snow_depth": 0.0}

    recorder = test_routines.run_energy_test(env)

    assert len(recorder.samples) == 3
    avg_last = sum(recorder.samples[-1]["embedded_temps_C"]) / 9
    assert avg_last <= 1.0
    assert fake_time.time() >= 30.0

    end_events = [extra for name, extra in events if name == "ENERGY_END"]
    assert end_events, "ENERGY_END event should be logged"
    assert end_events[0].get("time_to_clear_s") == pytest.approx(30.0)
    assert recorder.samples[-1].get("return_temp_C") == 10.0


def test_energy_test_caps_at_fifteen_minutes(monkeypatch):
    from tests.hydronic_slab import test_routines, thermostat

    fake_time = FakeTime()

    for module in (test_routines, thermostat):
        monkeypatch.setattr(module, "time", fake_time)

    monkeypatch.setattr(test_routines, "ensure_supply_hot", lambda target: None)
    monkeypatch.setattr(test_routines, "set_flow_level", lambda level: None)
    monkeypatch.setattr(test_routines, "set_non_tilt_angle", lambda: None)
    monkeypatch.setattr(test_routines, "set_pump_state", lambda on: None)
    monkeypatch.setattr(test_routines, "get_energy_totals_Wh", lambda: (0.0, 0.0))
    monkeypatch.setattr(test_routines, "regulate_water_temp", lambda target: target)

    events = []

    def capture_event(name, env_data, extra=None):
        events.append((name, extra or {}))

    monkeypatch.setattr(test_routines, "log_event", capture_event)

    monkeypatch.setattr(test_routines, "SampleRecorder", FakeRecorder)

    env = {"air_temp": 5.0, "humidity": 30.0, "wind_speed": 1.0, "wind_dir": 45.0, "snow_depth": 0.0}

    recorder = test_routines.run_energy_test(env)

    assert fake_time.time() == pytest.approx(900.0)
    assert recorder.samples, "expected periodic samples during long run"
    # Every 10 seconds until 900 seconds inclusive -> 90 samples after first delay.
    assert recorder.samples[0]["elapsed_s"] == 10.0
    assert recorder.samples[-1]["elapsed_s"] == 900.0

    end_events = [extra for name, extra in events if name == "ENERGY_END"]
    assert end_events and end_events[0].get("time_to_clear_s") is None

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
    monkeypatch.setattr(test_routines, "SIMULATED_MELT_MM_PER_CYCLE", 1.0)

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


def test_main_runs_tilted_when_snow_at_or_above_threshold(monkeypatch):
    from tests.hydronic_slab import main, state

    calls = []

    def track_tilted(env):
        calls.append(("tilted", env["snow_depth"]))

    def track_energy(env):
        calls.append(("energy", env["snow_depth"]))

    monkeypatch.setattr(main, "load_state", lambda: None)
    monkeypatch.setattr(main, "init_log_file", lambda: None)
    monkeypatch.setattr(main, "request_slab_angle_deg", lambda: None)
    monkeypatch.setattr(main, "actuators_stop", lambda: None)
    monkeypatch.setattr(main, "measure_snow_depth_mm", lambda: state.SNOW_PRESENT_THRESHOLD + 0.5)
    monkeypatch.setattr(main, "read_air_temperature_C", lambda: -2.0)
    monkeypatch.setattr(main, "read_relative_humidity", lambda: 60.0)
    monkeypatch.setattr(main, "read_wind_speed_mps", lambda: 1.2)
    monkeypatch.setattr(main, "read_wind_direction_deg", lambda: 45.0)
    monkeypatch.setattr(main, "run_tilted_test", track_tilted)
    monkeypatch.setattr(main, "run_energy_test", track_energy)

    main.main(cycle_period_s=0, max_cycles=1)

    assert calls == [("tilted", state.SNOW_PRESENT_THRESHOLD + 0.5)]


def test_main_runs_energy_when_snow_below_threshold(monkeypatch):
    from tests.hydronic_slab import main, state

    calls = []

    def track_tilted(env):
        calls.append(("tilted", env["snow_depth"]))

    def track_energy(env):
        calls.append(("energy", env["snow_depth"]))

    monkeypatch.setattr(main, "load_state", lambda: None)
    monkeypatch.setattr(main, "init_log_file", lambda: None)
    monkeypatch.setattr(main, "request_slab_angle_deg", lambda: None)
    monkeypatch.setattr(main, "actuators_stop", lambda: None)
    monkeypatch.setattr(main, "measure_snow_depth_mm", lambda: state.SNOW_PRESENT_THRESHOLD - 0.1)
    monkeypatch.setattr(main, "read_air_temperature_C", lambda: -2.0)
    monkeypatch.setattr(main, "read_relative_humidity", lambda: 60.0)
    monkeypatch.setattr(main, "read_wind_speed_mps", lambda: 1.2)
    monkeypatch.setattr(main, "read_wind_direction_deg", lambda: 45.0)
    monkeypatch.setattr(main, "run_tilted_test", track_tilted)
    monkeypatch.setattr(main, "run_energy_test", track_energy)

    main.main(cycle_period_s=0, max_cycles=1)


def test_main_falls_back_to_last_angle_when_unavailable(monkeypatch, capsys):
    from tests.hydronic_slab import main, state

    state.last_angle_deg = 12.5

    monkeypatch.setattr(main, "load_state", lambda: None)
    monkeypatch.setattr(main, "init_log_file", lambda: None)
    monkeypatch.setattr(main, "request_slab_angle_deg", lambda: None)

    stopped = []
    monkeypatch.setattr(main, "actuators_stop", lambda: stopped.append(True))
    monkeypatch.setattr(main, "measure_snow_depth_mm", lambda: 0.0)
    monkeypatch.setattr(main, "read_air_temperature_C", lambda: 0.0)
    monkeypatch.setattr(main, "read_relative_humidity", lambda: 0.0)
    monkeypatch.setattr(main, "read_wind_speed_mps", lambda: 0.0)
    monkeypatch.setattr(main, "read_wind_direction_deg", lambda: 0.0)
    monkeypatch.setattr(main, "run_tilted_test", lambda env: None)
    monkeypatch.setattr(main, "run_energy_test", lambda env: None)
    monkeypatch.setattr(main.time, "sleep", lambda *_: None)

    main.main(cycle_period_s=0, max_cycles=1)

    out = capsys.readouterr().out
    assert "using last recorded/default angle: 12.5" in out
    assert state.last_angle_deg == 12.5
    assert stopped


def test_env_bin_prints_across_snow_sequences(monkeypatch):
    from tests.hydronic_slab import main, state

    state.combo_counts.clear()
    state.daily_test_counts.clear()

    snow_depths = iter(
        [
            0.0,
            0.0,
            0.0,
            state.SNOW_PRESENT_THRESHOLD + 1,
            state.SNOW_PRESENT_THRESHOLD + 2,
            state.SNOW_PRESENT_THRESHOLD + 2,
        ]
    )

    bin_a_env = {"air": -20.0, "hum": 50.0, "wind": 5.0, "dir": 90.0}
    bin_b_env = {"air": -8.0, "hum": 20.0, "wind": 12.0, "dir": 270.0}

    env_sequence = iter(
        [
            bin_a_env.copy(),
            bin_a_env.copy(),
            bin_a_env.copy(),
            bin_a_env.copy(),
            bin_b_env.copy(),
            bin_b_env.copy(),
        ]
    )

    current_env = {"air": 0.0, "hum": 0.0, "wind": 0.0, "dir": 0.0}

    def advance_cycle():
        try:
            env_vals = next(env_sequence)
        except StopIteration:
            env_vals = bin_b_env
        current_env.update(env_vals)
        return next(snow_depths)

    monkeypatch.setattr(main, "load_state", lambda: None)
    monkeypatch.setattr(main, "init_log_file", lambda: None)
    monkeypatch.setattr(main, "request_slab_angle_deg", lambda: None)
    monkeypatch.setattr(main, "actuators_stop", lambda: None)
    monkeypatch.setattr(main, "time", __import__("time"))
    monkeypatch.setattr(main, "measure_snow_depth_mm", advance_cycle)
    monkeypatch.setattr(main, "read_air_temperature_C", lambda: current_env["air"])
    monkeypatch.setattr(main, "read_relative_humidity", lambda: current_env["hum"])
    monkeypatch.setattr(main, "read_wind_speed_mps", lambda: current_env["wind"])
    monkeypatch.setattr(main, "read_wind_direction_deg", lambda: current_env["dir"])

    run_log = []
    daily_counter = 0
    repetition_counts = {}

    def next_test_number():
        nonlocal daily_counter
        daily_counter += 1
        return "2024-02-02", daily_counter

    def fake_run_energy(env):
        env_bin = state.bin_non_tilt_env(
            env.get("air_temp"), env.get("humidity"), env.get("wind_speed"), env.get("wind_dir")
        )
        run_log.append(("energy", env_bin, env.get("snow_depth")))

        day_key, test_no = next_test_number()
        duration_s = 120 + test_no * 5
        time_to_clear = 60 + test_no * 2

        print("\n===== START ENERGY TEST =====")
        print(
            "ENERGY TEST #{} ON {} | env_bin {} | angle {} DEG".format(
                test_no, day_key, env_bin, 0
            )
        )
        print(" Actuator target angle: 0 (non-tilted mode)")
        for offset in (10, 20, 30):
            print(
                " Sample @ {:>4}s -> test_no {} | env_bin {} | air {:+.1f}°C | humidity {}% | wind {} m/s @ {} deg".format(
                    offset,
                    test_no,
                    env_bin,
                    env.get("air_temp"),
                    env.get("humidity"),
                    env.get("wind_speed"),
                    env.get("wind_dir"),
                )
            )
        print(
            "ENERGY TEST END -> TEST #{} duration_s = {:.1f} | time_to_clear_1C_s = {:.1f} | return_temp_C = {:.1f} | end_reason = embedded temp threshold".format(
                test_no, duration_s, time_to_clear, 28.5
            )
        )
        thermostat_modes = ["idle", "heating", "idle", "cooling", "idle"]
        changes = sum(1 for prev, curr in zip(thermostat_modes, thermostat_modes[1:]) if prev != curr)
        print(" Thermostat modes this run: {}".format(" -> ".join(thermostat_modes)))
        print(f" Thermostat mode changes: {changes}")
        print("===== END ENERGY TEST =====\n")

    def fake_run_tilted(env):
        env_bin = state.bin_non_tilt_env(
            env.get("air_temp"), env.get("humidity"), env.get("wind_speed"), env.get("wind_dir")
        )
        run_log.append(("tilted", env_bin, env.get("snow_depth")))

        day_key, test_no = next_test_number()
        repetition = repetition_counts.get(env_bin, 0)
        ANGLES = [0, 10, 20, 30, 40]
        target_ang = ANGLES[min(repetition, len(ANGLES) - 1)]
        repetition_counts[env_bin] = repetition + 1

        start_depth = env.get("snow_depth", 0.0)
        clear_depth = max(start_depth - 10.0, state.SNOW_CLEAR_THRESHOLD)
        time_to_clear = 180 + 15 * repetition

        print("\n===== BEGIN TILTED TEST =====")
        print(
            "TILTED TEST #{} ON {} | env_bin {} | REPETITION {} | target angle {} DEG".format(
                test_no, day_key, env_bin, repetition + 1, target_ang
            )
        )
        print(" Actuator moving to target angle {} DEG".format(target_ang))
        for offset in (10, 20, 30):
            current_depth = max(start_depth - offset * 0.1, state.SNOW_CLEAR_THRESHOLD)
            melted = max(start_depth - current_depth, 0.0)
            print(
                " Sample @ {:>4}s -> test_no {} | env_bin {} | angle {} DEG | snow depth {:.2f} mm (melted {:.2f} mm)".format(
                    offset,
                    test_no,
                    env_bin,
                    target_ang,
                    current_depth,
                    melted,
                )
            )
        print(
            "TILTED TEST END -> TEST #{} ANGLE {} DEG | duration_s = {:.1f} | time_to_clear_s = {:.1f} | depth_melted_mm = {:.2f} | end_reason = snow depth {:.2f} mm <= clear threshold".format(
                test_no,
                target_ang,
                time_to_clear + 25,
                time_to_clear,
                max(start_depth - clear_depth, 0.0),
                clear_depth,
            )
        )
        thermostat_modes = ["heating", "heating", "idle", "cooling", "idle"]
        changes = sum(1 for prev, curr in zip(thermostat_modes, thermostat_modes[1:]) if prev != curr)
        print(" Thermostat modes this run: {}".format(" -> ".join(thermostat_modes)))
        print(f" Thermostat mode changes: {changes}")
        print("===== END TILTED TEST =====\n")

    monkeypatch.setattr(main, "run_energy_test", fake_run_energy)
    monkeypatch.setattr(main, "run_tilted_test", fake_run_tilted)
    monkeypatch.setattr(main, "time", __import__("time"))
    monkeypatch.setattr(main.time, "sleep", lambda *_: None)

    main.main(cycle_period_s=0, max_cycles=6)

    total_runs = len(run_log)
    print(f"TOTAL TESTS EXECUTED: {total_runs}")

    assert total_runs == 6

    first_env_bin = run_log[0][1]
    assert all(run[0] == "energy" and run[1] == first_env_bin for run in run_log[:3])
    assert run_log[3][0] == "tilted" and run_log[3][1] == first_env_bin

    second_env_bin = run_log[4][1]
    assert second_env_bin != first_env_bin
    assert all(run[0] == "tilted" and run[1] == second_env_bin for run in run_log[4:])
    assert run_log[5][1] == run_log[4][1]
    assert run_log[5][2] >= state.SNOW_PRESENT_THRESHOLD


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


def test_tilted_models_gradual_snow_melt(monkeypatch):
    from tests.hydronic_slab import test_routines, thermostat

    fake_time = FakeTime()

    for module in (test_routines, thermostat):
        monkeypatch.setattr(module, "time", fake_time)

    monkeypatch.setattr(test_routines, "bin_snow_depth", lambda *_: 0)
    monkeypatch.setattr(test_routines, "get_next_angle_bin_for_snow_bin", lambda *_: 0)
    monkeypatch.setattr(test_routines, "get_repetition_count_for_snow_bin", lambda *_: 0)
    monkeypatch.setattr(test_routines, "mark_angle_tested", lambda *_: None)
    monkeypatch.setattr(test_routines, "get_next_daily_test_number", lambda: ("2024-01-02", 1))
    monkeypatch.setattr(test_routines, "ensure_supply_hot", lambda *_: None)
    monkeypatch.setattr(test_routines, "set_target_angle", lambda *_: None)
    monkeypatch.setattr(test_routines, "set_pump_state", lambda *_: None)
    monkeypatch.setattr(test_routines, "get_energy_totals_Wh", lambda: (0.0, 0.0))
    monkeypatch.setattr(test_routines, "log_event", lambda *_, **__: None)
    monkeypatch.setattr(test_routines, "save_state", lambda: None)
    monkeypatch.setattr(test_routines, "regulate_water_temp", lambda target: target)

    # Constant sensor reading; melt model should drive a downward ramp to zero.
    monkeypatch.setattr(test_routines, "measure_snow_depth_mm", lambda: 20.0)

    class MeltRecorder(FakeRecorder):
        def capture_sample(self, env, elapsed_s, water_temp_C=None, test_meta=None):
            sample = super().capture_sample(env, elapsed_s, water_temp_C, test_meta)
            sample["snow_depth"] = env.get("snow_depth")
            return sample

    monkeypatch.setattr(test_routines, "SampleRecorder", MeltRecorder)

    env = {"snow_depth": 20.0, "air_temp": -5.0, "humidity": 55.0, "wind_speed": 2.0, "wind_dir": 90.0}

    recorder = test_routines.run_tilted_test(env)

    depths = [sample["snow_depth"] for sample in recorder.samples if "snow_depth" in sample]
    assert depths, "expected samples to be recorded"
    assert all(earlier >= later for earlier, later in zip(depths, depths[1:])), "snow depths should decline"
    assert depths[-1] <= test_routines.SNOW_CLEAR_THRESHOLD


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
