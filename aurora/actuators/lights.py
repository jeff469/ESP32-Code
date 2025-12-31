"""Lights control wrapper."""

from aurora.actuators.mega_uart import MegaUART


class Lights:
    def __init__(self, mega: MegaUART):
        self.mega = mega
        self.state = False

    def on(self):
        if not self.state:
            self.mega.lights_on()
            self.state = True
            print("[LIGHTS] ON")

    def off(self):
        if self.state:
            self.mega.lights_off()
            self.state = False
            print("[LIGHTS] OFF")
