"""Structured sampling and Excel-friendly export for test runs."""
import csv
import os
import time
import ujson


def _default_http_post():
    try:
        import requests
    except Exception as exc:  # pragma: no cover - defensive for missing dependency
        raise RuntimeError("requests is required for HTTP uploads") from exc

    return requests.post

from tests.hydronic_slab.event_logger import ensure_log_dir
from tests.hydronic_slab.sensors.mega import (
    request_embedded_thermometer_temps_C,
    request_return_water_temp_C,
)
from tests.hydronic_slab.sensors.ultrasonic import measure_all_snow_depths_mm
from tests.hydronic_slab.sensors.weather_api import fetch_guelph_weather
from tests.hydronic_slab.state import LOG_DIR


class SampleRecorder:
    """Collects per-interval sensor snapshots and exports them for Excel."""

    def __init__(self, test_id, weather_fetcher=None, upload_url=None, upload_client=None):
        self.test_id = test_id
        self.samples = []
        self.weather_fetcher = weather_fetcher or fetch_guelph_weather
        self.weather_snapshot = None
        self.upload_url = upload_url or os.environ.get("HYDRONIC_UPLOAD_URL")
        self.upload_client = upload_client
    def __init__(self, test_id):
        self.test_id = test_id
        self.samples = []

    def capture_sample(self, env, elapsed_s, water_temp_C=None, test_meta=None):
        """Capture all requested sensors for the current moment."""

        timestamp = time.time()
        embedded_temps = request_embedded_thermometer_temps_C()
        return_temp = request_return_water_temp_C()
        snow_depths = measure_all_snow_depths_mm()
        snow_depth_avg = (
            sum(snow_depths) / len(snow_depths) if snow_depths else env.get("snow_depth")
        )

        sample = {
            "timestamp": timestamp,
            "elapsed_s": elapsed_s,
            "air_temp_C": env.get("air_temp"),
            "humidity_pct": env.get("humidity"),
            "wind_speed_mps": env.get("wind_speed"),
            "wind_dir_deg": env.get("wind_dir"),
            "water_temp_C": water_temp_C,
            "embedded_temps_C": embedded_temps,
            "return_temp_C": return_temp,
            "snow_depths_mm": snow_depths,
            "snow_depth_avg_mm": snow_depth_avg,
        }

        self.samples.append(sample)

        meta_parts = []
        if test_meta:
            if test_meta.get("test_no") is not None:
                meta_parts.append(f"Test #{test_meta['test_no']}")
            if test_meta.get("test_day"):
                meta_parts.append(test_meta["test_day"])
            if test_meta.get("test_type"):
                meta_parts.append(test_meta["test_type"].upper())
            if test_meta.get("angle_deg") is not None:
                meta_parts.append(f"angle={test_meta['angle_deg']}°")

        meta_str = " | ".join(meta_parts) if meta_parts else "Sample"

        print(
            f"{meta_str} -> Excel row data:",
            f"timestamp={round(timestamp, 3)}",
            f"elapsed_s={round(elapsed_s, 1)}",
            f"air_temp_C={env.get('air_temp')}",
            f"humidity_pct={env.get('humidity')}",
            f"wind_speed_mps={env.get('wind_speed')}",
            f"wind_dir_deg={env.get('wind_dir')}",
            f"water_temp_C={water_temp_C}",
            f"return_temp_C={return_temp}",
            f"snow_depths_mm={snow_depths}",
            f"snow_depth_avg_mm={snow_depth_avg}",
        )
        print(
            "    embedded A-I (°C) =",
            embedded_temps,
            "| raw embedded list =",
            ujson.dumps(embedded_temps),
        )
        return sample

    def capture_weather(self):
        """Fetch a single weather snapshot for Guelph via API."""

        if not self.weather_fetcher:
            return None

        try:
            self.weather_snapshot = self.weather_fetcher()
        except Exception as exc:  # pragma: no cover - defensive logging
            print("Weather fetch failed:", exc)
            self.weather_snapshot = None
        return self.weather_snapshot

    def _get_sample_path(self):
        ensure_log_dir()
        return os.path.join(LOG_DIR, f"{self.test_id}_samples.csv")

    def _get_weather_path(self):
        ensure_log_dir()
        return os.path.join(LOG_DIR, f"{self.test_id}_weather.csv")

    def save_excel_friendly_csv(self):
        """Persist samples to a CSV file Excel can ingest easily."""

        if not self.samples:
            return None

        path = self._get_sample_path()
        try:
            with open(path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "timestamp",
                        "elapsed_s",
                        "air_temp_C",
                        "humidity_pct",
                        "wind_speed_mps",
                        "wind_dir_deg",
                        "water_temp_C",
                        "return_temp_C",
                        "embedded_temp_A_C",
                        "embedded_temp_B_C",
                        "embedded_temp_C_C",
                        "embedded_temp_D_C",
                        "embedded_temp_E_C",
                        "embedded_temp_F_C",
                        "embedded_temp_G_C",
                        "embedded_temp_H_C",
                        "embedded_temp_I_C",
                        "embedded_temps_C",
                        "snow_depths_mm",
                        "snow_depth_avg_mm",
                    ]
                )

                for sample in self.samples:
                    embedded = sample.get("embedded_temps_C", [])
                    embedded_slots = [embedded[i] if i < len(embedded) else None for i in range(9)]

                    writer.writerow(
                        [
                            round(sample.get("timestamp", 0.0), 3),
                            round(sample.get("elapsed_s", 0.0), 1),
                            sample.get("air_temp_C"),
                            sample.get("humidity_pct"),
                            sample.get("wind_speed_mps"),
                            sample.get("wind_dir_deg"),
                            sample.get("water_temp_C"),
                            sample.get("return_temp_C"),
                            *embedded_slots,
                            ujson.dumps(sample.get("embedded_temps_C", [])),
                            ujson.dumps(sample.get("snow_depths_mm", [])),
                            sample.get("snow_depth_avg_mm"),
                        ]
                    )
        except Exception as e:
            print("Error saving sample CSV:", e)
            return None

        return path

    def save_weather_snapshot(self):
        """Persist the fetched weather snapshot to a CSV file."""

        if not self.weather_snapshot:
            return None

        path = self._get_weather_path()
        try:
            with open(path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "source",
                        "retrieved_at",
                        "condition",
                        "solar_radiation_Wm2",
                        "air_temp_C",
                        "humidity_pct",
                        "wind_speed_mps",
                        "wind_dir_deg",
                    ]
                )

                writer.writerow(
                    [
                        self.weather_snapshot.get("source"),
                        round(self.weather_snapshot.get("retrieved_at", 0.0), 3),
                        self.weather_snapshot.get("condition"),
                        self.weather_snapshot.get("solar_radiation_Wm2"),
                        self.weather_snapshot.get("air_temp_C"),
                        self.weather_snapshot.get("humidity_pct"),
                        self.weather_snapshot.get("wind_speed_mps"),
                        self.weather_snapshot.get("wind_dir_deg"),
                    ]
                )
        except Exception as e:  # pragma: no cover - defensive logging
            print("Error saving weather CSV:", e)
            return None

        print("Saved weather snapshot for Excel export ->", path)
        return path

    def upload_to_cloud(self, filepath):
        """Upload the CSV to a configured HTTP endpoint."""

        if not filepath:
            return None

        if not self.upload_url:
            print("No HYDRONIC_UPLOAD_URL configured; skipping upload for", filepath)
            return None

        if self.upload_client is None:
            try:
                self.upload_client = _default_http_post()
            except Exception as exc:
                print("Upload unavailable (no HTTP client):", exc)
                return None

        try:
            with open(filepath, "rb") as f:
                files = {
                    "file": (os.path.basename(filepath), f, "text/csv"),
                }
                data = {
                    "test_id": self.test_id,
                    "uploaded_at": round(time.time(), 3),
                }
                response = self.upload_client(
                    self.upload_url, files=files, data=data, timeout=10
                )
                if hasattr(response, "raise_for_status"):
                    response.raise_for_status()
                print(
                    "Uploaded",
                    filepath,
                    "->",
                    self.upload_url,
                    "status",
                    getattr(response, "status_code", "unknown"),
                )
                return response
        except Exception as exc:  # pragma: no cover - defensive logging
            print("Upload failed for", filepath, ":", exc)
            return None

    def finalize(self):
        """Save samples and upload to the cloud at the end of a trial."""
        # Collect weather once at the end of a trial for context.
        if self.weather_snapshot is None:
            self.capture_weather()

        path = self.save_excel_friendly_csv()
        weather_path = self.save_weather_snapshot()

        for target in (path, weather_path):
            if target:
                self.upload_to_cloud(target)
    def upload_to_cloud(self, filepath):
        """Placeholder for cloud upload integration."""
        # Implement cloud upload (e.g., HTTP PUT) when credentials are available.
        print("Uploading", filepath, "to cloud storage (stub).")

    def finalize(self):
        """Save samples and upload to the cloud at the end of a trial."""
        path = self.save_excel_friendly_csv()
        if path:
            self.upload_to_cloud(path)

