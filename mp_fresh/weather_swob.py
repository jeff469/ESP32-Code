"""
Minimal MicroPython script to fetch real-time SWOB data for the
Guelph Turfgrass Institute (station code COGI) from ECCC GeoMet.
Run with: exec(open('weather_swob.py').read())
"""

import gc
import network
import time
import ujson as json
import usocket as socket
import ussl as ssl

# Wi-Fi credentials (fill in before running)
WIFI_SSID = "YOUR_WIFI_NAME"
WIFI_PASS = "YOUR_WIFI_PASSWORD"

# Fetch interval (seconds)
POLL_EVERY_S = 300  # 5 minutes

# Station code and URL
STATION_CODE = "COGI"
GEOMET_URL = (
    "https://api.weather.gc.ca/collections/swob-realtime/items"
    "?lang=en"
    "&sortby=-date_tm-value"
    "&url="
    + STATION_CODE
    + "&limit=1&properties="
    "date_tm-value,stn_nam,air_temp,rel_hum,avg_wnd_spd_10m_pst2mts,avg_wnd_dir_10m_pst2mts,"
    "mslp,stn_pres"
    "&f=json"
)

# Optional: fetch once for a quick check instead of looping
RUN_ONCE = False


def wifi_connect(ssid, password, timeout_s=20):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        return True

    print("WiFi: connecting to", ssid)
    wlan.connect(ssid, password)
    t0 = time.ticks_ms()
    while not wlan.isconnected():
        if time.ticks_diff(time.ticks_ms(), t0) > timeout_s * 1000:
            print("WiFi: connect timeout")
            return False
        time.sleep(0.2)
    print("WiFi: connected", wlan.ifconfig())
    return True


def wifi_ensure():
    wlan = network.WLAN(network.STA_IF)
    if not wlan.active():
        wlan.active(True)
    if not wlan.isconnected():
        wifi_connect(WIFI_SSID, WIFI_PASS)


def _parse_url(url):
    scheme = "https" if url.startswith("https://") else "http"
    rest = url.split("://", 1)[1]
    if "/" in rest:
        hostport, path = rest.split("/", 1)
        path = "/" + path
    else:
        hostport, path = rest, "/"
    if ":" in hostport:
        host, port_s = hostport.split(":", 1)
        port = int(port_s)
    else:
        host = hostport
        port = 443 if scheme == "https" else 80
    return scheme, host, port, path


def http_get(url, timeout_s=15):
    scheme, host, port, path = _parse_url(url)
    addr = socket.getaddrinfo(host, port)[0][-1]
    s = socket.socket()
    s.settimeout(timeout_s)
    s.connect(addr)
    if scheme == "https":
        s = ssl.wrap_socket(s, server_hostname=host)
    req = (
        "GET "
        + path
        + " HTTP/1.1\r\nHost: "
        + host
        + "\r\nUser-Agent: esp32-micropython\r\nAccept: application/json\r\nConnection: close\r\n\r\n"
    )
    s.send(req.encode("utf-8"))
    chunks = []
    while True:
        try:
            data = s.recv(1024)
        except OSError:
            data = None
        if not data:
            break
        chunks.append(data)
    s.close()
    raw = b"".join(chunks)
    sep = raw.find(b"\r\n\r\n")
    if sep == -1:
        return raw
    return raw[sep + 4 :]


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
    i = int((deg + 11.25) / 22.5) % 16
    return dirs[i]


def safe_float(val):
    try:
        return float(val)
    except Exception:
        return None


def first_present(dct, keys):
    for key in keys:
        if key in dct and dct[key] not in (None, ""):
            return dct[key]
    return None


def fetch_guelph_turfgrass():
    body = http_get(GEOMET_URL)
    data = json.loads(body)
    feats = data.get("features", [])
    if not feats:
        raise RuntimeError("No features returned (bad station code or empty API response).")
    props = feats[0].get("properties", {})
    obs = {
        "station": props.get("stn_nam"),
        "time_utc": props.get("date_tm-value"),
        "temp_c": safe_float(props.get("air_temp")),
        "rh_pct": safe_float(props.get("rel_hum")),
        "wind_kmh": safe_float(props.get("avg_wnd_spd_10m_pst2mts")),
        "wind_dir_deg": safe_float(props.get("avg_wnd_dir_10m_pst2mts")),
        "mslp_hpa": safe_float(first_present(props, ["mslp", "stn_pres"])),
    }
    obs["wind_card"] = deg_to_cardinal(obs["wind_dir_deg"])
    return obs


def print_obs(obs):
    print("----------------------------------------")
    print("Station:", obs.get("station") or "(unknown)")
    print("Time (UTC):", obs.get("time_utc") or "(unknown)")
    if obs.get("temp_c") is not None:
        print("Temp (C):", obs["temp_c"])
    if obs.get("rh_pct") is not None:
        print("RH (%):", obs["rh_pct"])
    if obs.get("wind_kmh") is not None:
        extra = ""
        if obs.get("wind_dir_deg") is not None:
            extra = " @ " + str(obs["wind_dir_deg"]) + "° " + (obs.get("wind_card") or "")
        print("Wind (km/h):", obs["wind_kmh"], extra)
    if obs.get("mslp_hpa") is not None:
        print("Pressure (hPa):", obs["mslp_hpa"])


def main():
    if not wifi_connect(WIFI_SSID, WIFI_PASS):
        return
    while True:
        try:
            wifi_ensure()
            gc.collect()
            obs = fetch_guelph_turfgrass()
            print_obs(obs)
        except Exception as exc:
            print("ERROR:", exc)
        if RUN_ONCE:
            break
        time.sleep(POLL_EVERY_S)


main()
