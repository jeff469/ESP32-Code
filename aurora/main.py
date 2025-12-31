"""Main control loop for the Aurora snowmelt rig."""

import time

import aurora.config as config
import aurora.roles_store as roles_store
import aurora.state_store as state_store
from aurora.actuators.heater import Heater
from aurora.actuators.mega_uart import MegaUART
from aurora.actuators.pump import Pump
from aurora.actuators.tilt import Tilt
from aurora.control import decision, tests
from aurora.sensors.ds18b20 import DS18B20Suite
from aurora.sensors.sht3x import SHT3x
from aurora.sensors.ultrasonic import UltrasonicArray
from aurora.sensors.weather import WeatherClient


def boot_banner():
    print("\n=== AURORA ESP32 START ===")
    print("Build:", config.BUILD_ID, "| Uptime ms:", int(time.ticks_ms() if hasattr(time, "ticks_ms") else time.time() * 1000))
    print(
        "Pins: UART2 TX%d RX%d | TRIG%d ECHOs %s | OneWire GPIO%d | I2C0 SDA%d SCL%d"
        % (config.UART_TX, config.UART_RX, config.ULTRASONIC_TRIG, config.ULTRASONIC_ECHOS, config.DS18B20_PIN, config.I2C_SDA, config.I2C_SCL)
    )


def make_devices():
    mega = MegaUART()
    return {
        "mega": mega,
        "heater": Heater(mega),
        "pump": Pump(mega),
        "tilt": Tilt(mega),
        "ultra": UltrasonicArray(),
        "temps": DS18B20Suite(),
        "ambient": SHT3x(),
        "weather": WeatherClient(),
    }


def snapshot(mode, devices, roles):
    sample = tests._collect_sample(devices["ultra"], devices["temps"], devices["ambient"], devices["weather"], roles)
    tests._log_snapshot(mode, sample)
    return sample


def run_once(devices, state, roles):
    sample = snapshot("startup", devices, roles)
    decision_result = decision.choose_mode(sample.get("depths"), sample.get("depth_avg"))
    mode = decision_result.mode
    if mode == "skip":
        print("[ULTRA][FAIL] all sensors unavailable -> no test. retry in 60s")
        time.sleep(60)
        return state
    if mode == "sloped":
        state = state_store.increment_sloped(state)
        tests.run_sloped(state["sloped_test_count"], devices["ultra"], devices["temps"], devices["ambient"], devices["weather"], devices["heater"], devices["pump"], devices["tilt"], roles)
    else:
        state = state_store.increment_nonsloped(state)
        tests.run_nonsloped(state["nonsloped_test_count"], devices["ultra"], devices["temps"], devices["ambient"], devices["weather"], devices["heater"], devices["pump"], devices["tilt"], roles)
    print("\n=== SHUTDOWN ===")
    devices["pump"].off()
    devices["heater"].off()
    devices["tilt"].home_flat()
    print("[WAIT] sleeping", config.WAIT_BETWEEN_TESTS_S, "seconds")
    time.sleep(config.WAIT_BETWEEN_TESTS_S)
    return state


def main():
    boot_banner()
    state = state_store.load_state()
    roles = roles_store.load_roles()
    print("[STATE] loaded:", state)
    print("[ROLES] roles.json present:", not roles.get("placeholder"), " | pavement:", len(roles.get("pavement", [])), " fluid_out:", roles.get("fluid_out"), " fluid_return:", roles.get("fluid_return"))
    devices = make_devices()
    while True:
        state = run_once(devices, state, roles)


if __name__ == "__main__":
    main()
