"""Tilt actuator helper that wraps MegaUART open-loop moves."""

import aurora.config as config
from aurora.actuators.mega_uart import MegaUART


class Tilt:
    def __init__(self, mega: MegaUART):
        self.mega = mega

    def set_angle(self, angle_deg):
        self.mega.move_angle(max(0.0, min(config.FULL_TRAVEL_ANGLE_DEG, angle_deg)))

    def home_flat(self):
        self.mega.home_flat()
