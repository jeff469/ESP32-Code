"""Weather fetcher with caching and fallback."""

import json
import time
import urllib.error
import urllib.request
from typing import Optional, Tuple

import aurora.config as config


def _cardinal(deg):
    if deg is None:
        return None
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    idx = int((deg + 22.5) // 45) % 8
    return dirs[idx]


class WeatherClient:
    def __init__(self):
        self.cached = None
        self.cached_ts = 0

    def _fetch(self):
        req = urllib.request.Request(config.WEATHER_URL)
        with urllib.request.urlopen(req, timeout=config.WEATHER_TIMEOUT_S) as resp:
            data = resp.read()
        try:
            payload = json.loads(data)
        except Exception:
            return None, None
        wind_kmh = payload.get("wind_kmh")
        wind_deg = payload.get("wind_deg")
        return wind_kmh, wind_deg

    def read(self):
        now = time.time()
        if self.cached and now - self.cached_ts < config.WEATHER_CACHE_S:
            return self.cached
        try:
            wind_kmh, wind_deg = self._fetch()
            if wind_kmh is None or wind_deg is None:
                raise ValueError("missing wind fields")
            card = _cardinal(wind_deg)
            self.cached = (wind_kmh, wind_deg, card)
            self.cached_ts = now
        except Exception:
            # Keep previous cache
            pass
        return self.cached
