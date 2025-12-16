"""Structured sampling and Excel-friendly export for test runs."""
import csv
import os
import time
import ujson

from tests.hydronic_slab.event_logger import ensure_log_dir
from tests.hydronic_slab.sensors.mega import (
    request_embedded_thermometer_temps_C,
    request_return_water_temp_C,
)
from tests.hydronic_slab.sensors.ultrasonic import measure_all_snow_depths_mm
from tests.hydronic_slab.state import LOG_DIR


class SampleRecorder:
    """Collects per-interval sensor snapshots and exports them for Excel."""

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

    def _get_sample_path(self):
        ensure_log_dir()
        return os.path.join(LOG_DIR, f"{self.test_id}_samples.csv")

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

    def upload_to_cloud(self, filepath):
        """Placeholder for cloud upload integration."""
        # Implement cloud upload (e.g., HTTP PUT) when credentials are available.
        print("Uploading", filepath, "to cloud storage (stub).")

    def finalize(self):
        """Save samples and upload to the cloud at the end of a trial."""
        path = self.save_excel_friendly_csv()
        if path:
            self.upload_to_cloud(path)

