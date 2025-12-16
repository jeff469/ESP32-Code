import sys
import types
import time as _time
import json


class DummyPin:
    def __init__(self, pin, *_, **__):
        self.pin = pin


# Provide simple direction constants expected by sensor helpers
DummyPin.OUT = 1
DummyPin.IN = 0


class DummyPWM:
    def __init__(self, pin, freq=1000, *_, **__):
        self.pin = pin
        self.freq = freq
        self.last_duty = 0

    def duty(self, value):
        self.last_duty = value


class DummyUART:
    def __init__(self, *_, **__):
        self.buffer = bytearray()
        self.written = []

    def write(self, data):
        self.written.append(data)

    def any(self):
        return len(self.buffer) > 0

    def read(self, n=1):
        if not self.buffer:
            return b""
        chunk = self.buffer[:n]
        del self.buffer[:n]
        return bytes(chunk)


# Provide minimal MicroPython-compatible helpers used by communication.py
machine_stub = types.ModuleType("machine")
machine_stub.Pin = DummyPin
machine_stub.PWM = DummyPWM
machine_stub.UART = DummyUART
machine_stub.freq = lambda *_, **__: None
machine_stub.ticks_ms = lambda: int(_time.time() * 1000)
machine_stub.ticks_diff = lambda a, b: a - b
machine_stub.sleep_ms = lambda ms: _time.sleep(ms / 1000.0)

sys.modules.setdefault("machine", machine_stub)
sys.modules.setdefault("ujson", json)

# Provide ``time.ticks_*`` helpers that MicroPython code expects.
if not hasattr(_time, "ticks_ms"):
    _time.ticks_ms = lambda: int(_time.time() * 1000)
if not hasattr(_time, "ticks_diff"):
    _time.ticks_diff = lambda a, b: a - b
if not hasattr(_time, "sleep_ms"):
    _time.sleep_ms = lambda ms: _time.sleep(ms / 1000.0)
