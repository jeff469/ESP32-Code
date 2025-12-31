"""Simple hysteresis thermostat for the heater."""

import aurora.config as config


class Thermostat:
    def __init__(self, heater, target_c, band_c=None):
        self.heater = heater
        self.target_c = target_c
        self.band_c = band_c or config.HEATER_BAND_C

    def update(self, fluid_out_c):
        if fluid_out_c is None:
            self.heater.off()
            return False
        if fluid_out_c < self.target_c:
            self.heater.on()
        elif fluid_out_c > self.target_c + self.band_c:
            self.heater.off()
        return self.heater.state
