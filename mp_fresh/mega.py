import machine
import time
import config


class MegaController:
    def __init__(self, tx=config.UART2_TX, rx=config.UART2_RX, baud=config.UART_BAUD):
        self.uart = machine.UART(2, baudrate=baud, tx=machine.Pin(tx), rx=machine.Pin(rx))
        self.angle_deg = 0

    def _send(self, cmd):
        try:
            self.uart.write(cmd)
        except Exception:
            pass
        print("UART->Mega:", cmd)

    def pump_on(self):
        self._send(b"P")

    def pump_off(self):
        self._send(b"p")

    def heater_on(self):
        self._send(b"H")

    def heater_off(self):
        self._send(b"h")

    def act_up(self):
        self._send(b"U")

    def act_down(self):
        self._send(b"D")

    def act_stop(self):
        self._send(b"S")

    def set_angle_deg(self, target_deg):
        if target_deg < 0:
            target_deg = 0
        delta = target_deg - self.angle_deg
        if delta == 0:
            return
        direction = self.act_up if delta > 0 else self.act_down
        speed = config.ACTUATOR_UP_DEG_PER_SEC if delta > 0 else config.ACTUATOR_DOWN_DEG_PER_SEC
        if speed <= 0:
            speed = 1
        move_time = abs(delta) / speed + config.ACTUATOR_MOVE_BUFFER_S
        print("Changing angle from", self.angle_deg, "to", target_deg, "deg; moving for", move_time, "s")
        direction()
        time.sleep(move_time)
        self.act_stop()
        self.angle_deg = target_deg
        print("Angle set to", self.angle_deg)
