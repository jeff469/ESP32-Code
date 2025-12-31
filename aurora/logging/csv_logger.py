"""CSV logger for 10-second samples."""

import csv
import os
import time
from typing import Dict

import aurora.config as config

HEADER = [
    "timestamp_ms",
    "run_id",
    "mode",
    "target_fluid_c",
    "slope_deg",
    "heater_on",
    "pump_on",
    "u1_cm",
    "u2_cm",
    "u3_cm",
    "u4_cm",
    "depth1_cm",
    "depth2_cm",
    "depth3_cm",
    "depth4_cm",
    "depth_avg_cm",
    "pav1_c",
    "pav2_c",
    "pav3_c",
    "pav4_c",
    "pav5_c",
    "pav6_c",
    "pav7_c",
    "pav8_c",
    "pav9_c",
    "pav10_c",
    "pav_avg_c",
    "fluid_out_c",
    "fluid_return_c",
    "ambient_c",
    "rh_pct",
    "wind_kmh",
    "wind_dir_deg",
    "wind_card",
    "event",
    "melt_time_s",
    "time_to_pav1c_s",
    "end_reason",
]


def timestamp_ms():
    return int(time.time() * 1000)


def ensure_dir():
    if not os.path.exists(config.LOG_DIR):
        os.makedirs(config.LOG_DIR)


class CSVLogger:
    def __init__(self, path):
        ensure_dir()
        self.path = path
        self.file = open(path, "w", newline="")
        self.writer = csv.writer(self.file)
        self.writer.writerow(HEADER)

    def append(self, row: Dict[str, object]):
        values = [row.get(key, "") for key in HEADER]
        self.writer.writerow(values)
        self.file.flush()
        print("[CSV] append ok")

    def close(self):
        self.file.close()
