import machine
import network
import time

try:
    import usocket as socket
except Exception:
    import socket

try:
    import ssl
except Exception:
    try:
        import ussl as ssl
    except Exception:
        ssl = None

try:
    import onewire
    import ds18x20
except Exception:
    onewire = None
    ds18x20 = None

try:
    import ujson as json
except Exception:
    import json

import config


def _hex_to_rom(hex_str):
    try:
        return bytes.fromhex(hex_str)
    except Exception:
        return None


def _wifi_connect(ssid, password, timeout_s=15):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        return True
    print("WiFi: connecting to", ssid)
    try:
        wlan.connect(ssid, password)
    except Exception as exc:
        print("WiFi connect failed; keeping last wind", exc)
        return False
    start = time.ticks_ms()
    while not wlan.isconnected():
        if time.ticks_diff(time.ticks_ms(), start) > timeout_s * 1000:
            print("WiFi connect timeout; keeping last wind reading")
            return False
        time.sleep(0.25)
    print("WiFi: connected", wlan.ifconfig())
    return True


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


def _http_get(url, timeout_s=15):
    scheme, host, port, path = _parse_url(url)
    addr = socket.getaddrinfo(host, port)[0][-1]
    s = socket.socket()
    s.settimeout(timeout_s)
    s.connect(addr)
    if scheme == "https":
        if ssl is None:
            s.close()
            raise RuntimeError("HTTPS requested but no SSL support")
        try:
            s = ssl.wrap_socket(s, server_hostname=host)
        except TypeError:
            s = ssl.wrap_socket(s)
    req = (
        "GET "
        + path
        + " HTTP/1.1\r\nHost: "
        + host
        + "\r\nUser-Agent: esp32-mp\r\nAccept: application/json\r\nConnection: close\r\n\r\n"
    )
    s.send(req.encode("utf-8"))
    chunks = []
    while True:
        try:
            data = s.recv(512)
        except Exception:
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


def _safe_float(val):
    try:
        return float(val)
    except Exception:
        return None


class UltrasonicSensor:
    def __init__(self, trig_pin, echo_pin, timeout_us=30000):
        # Allow passing a Pin object for the shared trigger so multiple sensors
        # can reuse a single TRIG line.
        if isinstance(trig_pin, machine.Pin):
            self.trig = trig_pin
        else:
            self.trig = machine.Pin(trig_pin, machine.Pin.OUT)
        self.trig.off()
        self.echo = machine.Pin(echo_pin, machine.Pin.IN, machine.Pin.PULL_DOWN)
        self.timeout_us = timeout_us

    def measure_distance_cm(self):
        self.trig.off()
        time.sleep_us(2)
        self.trig.on()
        time.sleep_us(10)
        self.trig.off()
        duration = machine.time_pulse_us(self.echo, 1, self.timeout_us)
        if duration < 0:
            return config.STUB_ULTRASONIC_CM
        # speed of sound 343 m/s -> 0.0343 cm/us; divide by 2 for round trip
        distance = (duration * 0.0343) / 2
        return distance


class SHT3xSensor:
    def __init__(self, sda, scl, addr=config.SHT3X_ADDR):
        self.addr = addr
        self.failed = False
        try:
            self.i2c = machine.I2C(1, sda=machine.Pin(sda), scl=machine.Pin(scl))
        except Exception as exc:
            # If the sensor is missing or I2C fails to init, fall back to stub values.
            print("Ambient sensor init failed; using stub:", exc)
            self.failed = True
            self.i2c = None

    def read(self):
        if self.failed:
            return config.STUB_AMBIENT
        try:
            # Single shot high repeatability, clock stretching disabled
            cmd = bytearray([0x24, 0x00])
            self.i2c.writeto(self.addr, cmd)
            time.sleep_ms(15)
            data = self.i2c.readfrom(self.addr, 6)
            t_raw = data[0] << 8 | data[1]
            h_raw = data[3] << 8 | data[4]
            temperature = -45 + (175 * t_raw / 65535)
            humidity = 100 * h_raw / 65535
            return temperature, humidity
        except Exception as exc:
            print("Ambient sensor read failed; using stub:", exc)
            self.failed = True
            return config.STUB_AMBIENT


class FlowSensor:
    def __init__(self, pin_no, window_ms=config.FLOW_WINDOW_MS, debounce_us=config.FLOW_DEBOUNCE_US):
        self.pin = machine.Pin(pin_no, machine.Pin.IN, machine.Pin.PULL_UP)
        self.window_ms = window_ms
        self.debounce_us = debounce_us
        self.count = 0
        self.last_tick = time.ticks_us()
        self.last_reset = time.ticks_ms()
        self.pin.irq(trigger=machine.Pin.IRQ_FALLING, handler=self._pulse)

    def _pulse(self, pin):
        now = time.ticks_us()
        if time.ticks_diff(now, self.last_tick) < self.debounce_us:
            return
        self.last_tick = now
        self.count += 1

    def read_l_min(self):
        now_ms = time.ticks_ms()
        elapsed = time.ticks_diff(now_ms, self.last_reset)
        if elapsed <= 0:
            elapsed = 1
        pulses = self.count
        if elapsed >= self.window_ms:
            self.count = 0
            self.last_reset = now_ms
        # Convert pulses per window to per minute estimation
        flow_per_min = pulses * 60000 / elapsed
        return flow_per_min


class DS18B20Manager:
    def __init__(self, pin_no, fluid_out_rom, fluid_return_rom, pavement_roms):
        self.dat = machine.Pin(pin_no)
        self.last_good = {}
        self.fluid_out_rom = _hex_to_rom(fluid_out_rom)
        self.fluid_return_rom = _hex_to_rom(fluid_return_rom)
        self.pavement_roms = []
        for rom_hex in pavement_roms:
            rom = _hex_to_rom(rom_hex)
            if rom is not None:
                self.pavement_roms.append(rom)
        if onewire is not None and ds18x20 is not None:
            try:
                self.ow = onewire.OneWire(self.dat)
                self.ds = ds18x20.DS18X20(self.ow)
            except Exception as exc:
                print("DS18B20 bus init failed", exc)
                self.ow = None
                self.ds = None
        else:
            self.ow = None
            self.ds = None

    def _convert(self):
        if self.ds is None:
            return False
        try:
            self.ds.convert_temp()
            time.sleep_ms(750)
            return True
        except Exception as exc:
            print("DS18B20 convert failed", exc)
            return False

    def _read_one(self, name, rom):
        if self.ds is None or rom is None:
            return self.last_good.get(name)
        try:
            temp = self.ds.read_temp(rom)
        except Exception as exc:
            print("DS18B20 read failed for", name, exc)
            temp = None
        if temp is None:
            return self.last_good.get(name)
        self.last_good[name] = temp
        return temp

    def read_all(self):
        self._convert()
        pavements = []
        fluid_out = self._read_one("fluid_out", self.fluid_out_rom)
        fluid_return = self._read_one("fluid_return", self.fluid_return_rom)
        idx = 1
        for rom in self.pavement_roms:
            name = "pavement_%d" % idx
            pavements.append(self._read_one(name, rom))
            idx += 1
        return {
            "fluid_out": fluid_out,
            "fluid_return": fluid_return,
            "pavements": pavements,
        }

    def read_pavements(self):
        return self.read_all().get("pavements", [])


class WindFromApi:
    def __init__(self):
        self.last = config.STUB_WIND
        self.last_fetch = 0

    def _fetch(self):
        if not config.WIFI_SSID or config.WIFI_SSID == "YOUR_WIFI_NAME":
            print("Wind API skipped; WIFI_SSID not set")
            return self.last
        if not _wifi_connect(config.WIFI_SSID, config.WIFI_PASS):
            return self.last

        last_error = None
        for url in config.WIND_API_URLS:
            try:
                body = _http_get(url)
                data = json.loads(body)
                feats = data.get("features", [])
                if not feats:
                    last_error = "no features"
                    continue
                props = feats[0].get("properties", {})
                speed = _safe_float(props.get("avg_wnd_spd_10m_pst2mts"))
                direction = _safe_float(props.get("avg_wnd_dir_10m_pst2mts"))
                if speed is None or direction is None:
                    last_error = "missing speed/dir"
                    continue
                speed_ms = speed / 3.6
                self.last = (speed_ms, direction)
                self.last_fetch = time.time()
                print("Wind API updated", self.last, "from", url)
                return self.last
            except Exception as exc:
                last_error = exc

        print("Wind API fallback; keeping last wind", last_error)
        return self.last

    def read(self):
        now = time.time()
        if self.last_fetch and (now - self.last_fetch) < config.WIND_API_CACHE_SECONDS:
            return self.last
        try:
            return self._fetch()
        except Exception as exc:
            print("Wind API error; keeping last wind", exc)
            return self.last


class SensorSuite:
    def __init__(self):
        trig_pin = machine.Pin(config.ULTRASONIC_TRIG, machine.Pin.OUT)
        self.ultrasonics = [UltrasonicSensor(trig_pin, echo, timeout_us=60000) for echo in config.ULTRASONIC_ECHOS]
        self.ambient_real = SHT3xSensor(config.I2C_SDA, config.I2C_SCL)
        self.flow_real = FlowSensor(config.FLOW_PIN)
        self.temp_manager = DS18B20Manager(
            config.DS18B20_PIN,
            config.DS18B20_FLUID_OUT_ROM,
            config.DS18B20_FLUID_RETURN_ROM,
            config.DS18B20_PAVEMENT_ROMS,
        )
        self.wind_api = WindFromApi()

    def read_ultrasonics(self):
        distances = []
        for sensor in self.ultrasonics:
            distances.append(sensor.measure_distance_cm())
            time.sleep_ms(50)
        return distances

    def read_flows(self):
        return [self.flow_real.read_l_min()]

    def read_temps(self):
        return self.temp_manager.read_all()

    def read_fluid_out(self):
        return self.temp_manager.read_all().get("fluid_out")

    def read_fluid_return(self):
        return self.temp_manager.read_all().get("fluid_return")

    def read_wind(self):
        return self.wind_api.read()

    def read_pavement(self):
        return self.temp_manager.read_pavements()
