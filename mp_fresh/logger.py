import os
import time

try:
    import ujson as json
except Exception:
    import json

import config


def ensure_dirs():
    if not os.path.exists(config.LOG_DIR):
        os.mkdir(config.LOG_DIR)
    if not os.path.exists("state"):
        os.mkdir("state")


def timestamp():
    t = time.localtime()
    return "%04d%02d%02d_%02d%02d%02d" % (t[0], t[1], t[2], t[3], t[4], t[5])


def log_path(trial_num, tilted):
    ensure_dirs()
    name = "%s_trial%02d_%s.csv" % (timestamp(), trial_num, "tilted" if tilted else "nontilted")
    return "%s/%s" % (config.LOG_DIR, name)


def write_header(path):
    if os.path.exists(path):
        return
    header = (
        "ts,snow_depth_cm,distances_cm,ambient_th,wind_sd,flows,fluid_temps,pavement_avg,"
        "angle_deg,pump,heater"
    )
    with open(path, "w") as fp:
        fp.write(header + "\n")


def append_row(path, row):
    with open(path, "a") as fp:
        fp.write(row + "\n")


class CSVLogger:
    def __init__(self, path):
        self.path = path
        write_header(self.path)

    def log(self, data):
        row = (
            "%s,%0.2f,%s,%s,%s,%s,%s,%0.2f,%0.2f,%s,%s"
            % (
                data.get("ts"),
                data.get("snow_depth_cm", 0.0),
                data.get("distances"),
                data.get("ambient"),
                data.get("wind"),
                data.get("flows"),
                data.get("fluid_temps"),
                data.get("pavement_avg", 0.0),
                data.get("angle", 0.0),
                data.get("pump"),
                data.get("heater"),
            )
        )
        append_row(self.path, row)
