"""HTTP uploader for CSV files."""

import os
import time
import urllib.request

import aurora.config as config


def upload(path, timeout=config.UPLOAD_TIMEOUT_S):
    if not os.path.exists(path):
        return False
    url = config.WEATHER_URL  # placeholder drop server URL
    data = open(path, "rb").read()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "text/csv")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
        print("[UP] sent ok")
        return True
    except Exception as err:
        print("[UP][FAIL]", err)
        return False


def retry_upload(path):
    deadline = time.time() + config.FINAL_UPLOAD_TIMEOUT_S
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        if upload(path, timeout=config.UPLOAD_TIMEOUT_S):
            return True
        wait = min(2 ** attempt, 30)
        time.sleep(wait)
    return False
