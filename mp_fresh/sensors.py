import machine
import network
import time

try:
    import usocket as socket
except Exception:
    import socket

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


def _wifi_connect(ssid, password, timeout_s=15):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        return True
    print("WiFi: connecting to", ssid)
    wlan.connect(ssid, password)
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
        s = ssl.wrap_socket(s, server_hostname=host)
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
        self.trig = machine.Pin(trig_pin, machine.Pin.OUT)
        self.echo = machine.Pin(echo_pin, machine.Pin.IN)
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


class StubUltrasonicSensor:
    def __init__(self, value_cm=config.STUB_ULTRASONIC_CM):
        self.value_cm = value_cm

    def measure_distance_cm(self):
        return self.value_cm


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


class StubAmbientSensor:
    def __init__(self, values=config.STUB_AMBIENT):
        self.values = values

    def read(self):
        return self.values


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


class StubFlowSensor:
    def __init__(self, pulses=config.STUB_FLOW_PULSES_PER_WINDOW):
        self.pulses = pulses

    def read_l_min(self):
        return self.pulses


class FluidThermometer:
    def __init__(self, pin_no):
        self.dat = machine.Pin(pin_no)
        self.last_good = None
        self.rom = None
        if onewire is not None and ds18x20 is not None:
            self.ow = onewire.OneWire(self.dat)
            self.ds = ds18x20.DS18X20(self.ow)
            roms = self.ds.scan()
            if roms:
                self.rom = roms[0]
            else:
                print("DS18B20 scan found no devices; using stub until available")
        else:
            self.ow = None
            self.ds = None

    def _ensure_rom(self):
        if self.ds is None:
            return False
        if self.rom is not None:
            return True
        try:
            roms = self.ds.scan()
            if roms:
                self.rom = roms[0]
                print("DS18B20 discovered after rescan")
                return True
        except Exception as exc:
            print("DS18B20 rescan failed; using stub:", exc)
        return False

    def read_temp_c(self):
        if not self._ensure_rom():
            return config.STUB_FLUID_TEMP_C
        for attempt in range(2):
            try:
                self.ds.convert_temp()
                time.sleep_ms(750)
                temp = self.ds.read_temp(self.rom)
                if temp is not None:
                    self.last_good = temp
                    return temp
            except Exception as exc:
                print("DS18B20 read attempt", attempt + 1, "failed;", exc)
        if self.last_good is not None:
            print("Using last good DS18B20 reading", self.last_good)
            return self.last_good
        print("DS18B20 unavailable; using stub temp")
        return config.STUB_FLUID_TEMP_C


class StubFluidThermometer:
    def __init__(self, value=config.STUB_FLUID_TEMP_C):
        self.value = value

    def read_temp_c(self):
        return self.value


class WindSensorStub:
    def __init__(self, values=config.STUB_WIND):
        self.values = values

    def read(self):
        return self.values


class WindFromApi:
    def __init__(self):
        self.last = config.STUB_WIND
        self.last_fetch = 0

    def _fetch(self):
        if not _wifi_connect(config.WIFI_SSID, config.WIFI_PASS):
            return self.last
        body = _http_get(config.WIND_API_URL)
        data = json.loads(body)
        feats = data.get("features", [])
        if not feats:
            print("Wind API returned no features; keeping last wind")
            return self.last
        props = feats[0].get("properties", {})
        speed = _safe_float(props.get("avg_wnd_spd_10m_pst2mts"))
        direction = _safe_float(props.get("avg_wnd_dir_10m_pst2mts"))
        if speed is None or direction is None:
            print("Wind API missing values; keeping last wind")
            return self.last
        # GeoMet provides speed in km/h; bins expect m/s style magnitudes, so
        # convert to m/s for consistency with prior stub scale.
        speed_ms = speed / 3.6
        self.last = (speed_ms, direction)
        self.last_fetch = time.time()
        print("Wind API updated", self.last)
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


class PavementArrayStub:
    def __init__(self, count=10, value=config.STUB_PAVEMENT_TEMP_C):
        self.count = count
        self.value = value

    def read_all(self):
        return [self.value for _ in range(self.count)]


class SensorSuite:
    def __init__(self):
        self.ultrasonic_real = UltrasonicSensor(config.ULTRASONIC_PINS["trig"], config.ULTRASONIC_PINS["echo"])
        self.ultrasonic_stubs = [StubUltrasonicSensor() for _ in range(3)]
        self.ambient_real = SHT3xSensor(config.I2C_SDA, config.I2C_SCL)
        self.ambient_stubs = [StubAmbientSensor() for _ in range(2)]
        self.flow_real = FlowSensor(config.FLOW_PIN)
        self.flow_stubs = [StubFlowSensor() for _ in range(3)]
        self.thermo_real = FluidThermometer(config.DS18B20_PIN)
        self.thermo_stub = StubFluidThermometer()
        self.wind_api = WindFromApi()
        self.pavement_stub = PavementArrayStub()

    def read_ultrasonics(self):
        values = [self.ultrasonic_real.measure_distance_cm()]
        values.extend([s.measure_distance_cm() for s in self.ultrasonic_stubs])
        return values

    def read_ambient_all(self):
        readings = [self.ambient_real.read()]
        readings.extend([s.read() for s in self.ambient_stubs])
        return readings

    def read_flows(self):
        readings = [self.flow_real.read_l_min()]
        readings.extend([s.read_l_min() for s in self.flow_stubs])
        return readings

    def read_temps(self):
        return [self.thermo_real.read_temp_c(), self.thermo_stub.read_temp_c()]

    def read_wind(self):
        return self.wind_api.read()

    def read_pavement(self):
        return self.pavement_stub.read_all()
