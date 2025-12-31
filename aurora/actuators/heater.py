"""Heater control wrapper."""

from aurora.actuators.mega_uart import MegaUART


class Heater:
    def __init__(self, mega: MegaUART):
        self.mega = mega
        self.state = False

    def on(self):
        if not self.state:
            self.mega.heater_on()
            self.state = True
            print("[HEATER] ON")

    def off(self):
        if self.state:
            self.mega.heater_off()
            self.state = False
            print("[HEATER] OFF")
