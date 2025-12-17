"""Weather API helper for fetching current conditions in Guelph."""

import time


def _default_http_get():
    import requests

    return requests.get


def fetch_guelph_weather(http_get=None):
    """Fetch current weather for Guelph, Ontario using Open-Meteo.

    Returns a dictionary with solar radiation, weather code/description, and
    current temperature, humidity, wind speed, and wind direction. If any
    issue occurs, a best-effort stub value is returned so downstream logging
    can still proceed.
    """

    http_get = http_get or _default_http_get()

    params = {
        "latitude": 43.5448,
        "longitude": -80.2482,
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,weather_code,shortwave_radiation",
    }

    try:
        response = http_get(
            "https://api.open-meteo.com/v1/forecast", params=params, timeout=5
        )
        response.raise_for_status()
        payload = response.json()
        current = payload.get("current", {})

        snapshot = {
            "source": "open-meteo",
            "retrieved_at": time.time(),
            "condition": current.get("weather_code"),
            "solar_radiation_Wm2": current.get("shortwave_radiation"),
            "air_temp_C": current.get("temperature_2m"),
            "humidity_pct": current.get("relative_humidity_2m"),
            "wind_speed_mps": current.get("wind_speed_10m"),
            "wind_dir_deg": current.get("wind_direction_10m"),
        }
    except Exception as exc:  # pragma: no cover - defensive logging
        print("Weather API request failed:", exc)
        snapshot = {
            "source": "open-meteo (unavailable)",
            "retrieved_at": time.time(),
            "condition": "unavailable",
            "solar_radiation_Wm2": None,
            "air_temp_C": None,
            "humidity_pct": None,
            "wind_speed_mps": None,
            "wind_dir_deg": None,
        }

    print("Weather snapshot:", snapshot)
    return snapshot

