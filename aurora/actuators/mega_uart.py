"""UART helper for communicating with the Arduino Mega."""

import time

import aurora.config as config


class MegaUART:
    def __init__(self):
        self.current_angle = 0.0

    def send(self, char):
        print("[MEGA] send:", char)
        # MicroPython: uart.write(char)

    def heater_on(self):
        self.send("H")

    def heater_off(self):
        self.send("h")

    def pump_on(self):
        self.send("P")

    def pump_off(self):
        self.send("p")

    def tilt_up(self):
        self.send("U")

    def tilt_down(self):
        self.send("D")

    def tilt_stop(self):
        self.send("S")

    def lights_on(self):
        self.send("A")

    def lights_off(self):
        self.send("a")

    def move_angle(self, target_deg):
        delta = target_deg - self.current_angle
        direction = "up" if delta > 0 else "down"
        move_s = abs(delta) / config.FULL_TRAVEL_ANGLE_DEG * config.FULL_TRAVEL_TIME_S
        print("[TILT] current_est:", self.current_angle, "-> target:", target_deg, "delta:", delta, "move_s:", move_s, "dir:", direction)
        try:
            if delta > 0:
                self.tilt_up()
            elif delta < 0:
                self.tilt_down()
            time.sleep(move_s)
        finally:
            self.tilt_stop()
        self.current_angle = target_deg
        print("[TILT] stop sent. new_est:", self.current_angle)

    def home_flat(self):
        print("[TILT] homing flat: retract for", config.HOME_TIME_S, "s")
        try:
            self.tilt_down()
            time.sleep(config.HOME_TIME_S)
        finally:
            self.tilt_stop()
        self.current_angle = 0.0
        print("[TILT] homed -> current_est set to 0")
