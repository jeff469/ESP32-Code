"""Pump control wrapper."""

from aurora.actuators.mega_uart import MegaUART


class Pump:
    def __init__(self, mega: MegaUART):
        self.mega = mega
        self.state = False

    def on(self):
        if not self.state:
            self.mega.pump_on()
            self.state = True
            print("[PUMP] ON")

    def off(self):
        if self.state:
            self.mega.pump_off()
            self.state = False
            print("[PUMP] OFF")
