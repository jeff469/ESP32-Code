"""
One-shot GeoMet SWOB fetch for ESP32 MicroPython.
Connect to Wi-Fi, try several station codes (newest obs), print, exit.
Run with: exec(open('weather_swob.py').read())
"""

import gc
import network
import time
import ujson as json
import usocket as socket

try:
    import ssl
except ImportError:
    try:
        import ussl as ssl
    except ImportError:
        ssl = None

# Wi-Fi credentials (fill these in before running)
WIFI_SSID = "YOUR_WIFI_NAME"
WIFI_PASS = "YOUR_WIFI_PASSWORD"

# Try multiple southern Ontario stations (first success wins)
STATION_CODES = ["COGI", "CYHM", "CYXU"]

BASE_URL = (
    "https://api.weather.gc.ca/collections/swob-realtime/items"
    "?lang=en&f=json&limit=1&sortby=-date_tm-value&url="
)


def wifi_connect(ssid, password, timeout_s=20):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        print("WiFi already connected:", wlan.ifconfig())
        return True

    print("WiFi: connecting to", ssid)
    wlan.connect(ssid, password)

    t0 = time.ticks_ms()
    while not wlan.isconnected():
        if time.ticks_diff(time.ticks_ms(), t0) > timeout_s * 1000:
            print("WiFi: connect timeout")
            return False
        time.sleep(0.2)

    print("WiFi: connected:", wlan.ifconfig())
    return True


def http_get(url, timeout_s=20):
    rest = url.split("://", 1)[1]
    host, path = rest.split("/", 1)
    path = "/" + path

    addr = socket.getaddrinfo(host, 443)[0][-1]
    s = socket.socket()
    s.settimeout(timeout_s)
    s.connect(addr)

    gc.collect()
    if ssl is None:
        s.close()
        raise RuntimeError("HTTPS requested but ssl/ussl not available in this firmware.")
    s = ssl.wrap_socket(s, server_hostname=host)

    req = (
        "GET {} HTTP/1.1\r\n"
        "Host: {}\r\n"
        "User-Agent: esp32\r\n"
        "Accept: application/json\r\n"
        "Connection: close\r\n\r\n"
    ).format(path, host)

    s.send(req.encode())

    buf = bytearray()
    while True:
        try:
            data = s.recv(512)
        except OSError:
            break
        if not data:
            break
        buf.extend(data)

    try:
        s.close()
    except Exception:
        pass
    gc.collect()

    raw = bytes(buf)
    sep = raw.find(b"\r\n\r\n")
    return raw if sep == -1 else raw[sep + 4 :]


def safe_float(val):
    try:
        return float(val)
    except Exception:
        return None


def deg_to_cardinal(deg):
    if deg is None:
        return None
    dirs = [
        "N",
        "NNE",
        "NE",
        "ENE",
        "E",
        "ESE",
        "SE",
        "SSE",
        "S",
        "SSW",
        "SW",
        "WSW",
        "W",
        "WNW",
        "NW",
        "NNW",
    ]
    return dirs[int((deg + 11.25) / 22.5) % 16]


def first_present(dct, keys):
    for key in keys:
        v = dct.get(key)
        if v not in (None, ""):
            return v
    return None


def run_once():
    if not wifi_connect(WIFI_SSID, WIFI_PASS):
        return

    last_err = None
    for code in STATION_CODES:
        url = BASE_URL + code
        print("\nQuery:", url)

        try:
            body = http_get(url)
            data = json.loads(body)
            feats = data.get("features", [])

            if not feats:
                print("No features for", code)
                continue

            props = feats[0].get("properties", {})

            time_utc = props.get("date_tm-value")
            temp_c = safe_float(props.get("air_temp"))
            wind_kmh = safe_float(props.get("avg_wnd_spd_10m_pst2mts"))
            wind_dir = safe_float(props.get("avg_wnd_dir_10m_pst2mts"))

            print("--- RESULT ---")
            print("Station code:", code)
            print(
                "Station name:",
                first_present(props, ["stn_nam", "stn_nam_en", "stn_nam_fr"]) or "(unknown)",
            )
            print("Time (UTC):", time_utc)
            print("Temp (C):", temp_c)
            if wind_kmh is not None:
                print("Wind (km/h):", wind_kmh, "@", wind_dir, deg_to_cardinal(wind_dir))

            return

        except Exception as exc:
            last_err = exc
            print("Error for", code, ":", repr(exc))

    print("\nFAILED. Last error:", repr(last_err))


run_once()
