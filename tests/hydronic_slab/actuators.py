"""Relay and actuator helpers proxied through the Arduino Mega."""
from tests.hydronic_slab.communication import send_command_to_mega


def actuators_move_up():
    send_command_to_mega("ACT:UP")


def actuators_move_down():
    send_command_to_mega("ACT:DOWN")


def actuators_stop():
    send_command_to_mega("ACT:STOP")


def pump_on():
    send_command_to_mega("PUMP:ON")


def pump_off():
    send_command_to_mega("PUMP:OFF")


def heater_on():
    send_command_to_mega("HEATER:ON")


def heater_off():
    send_command_to_mega("HEATER:OFF")


def solA_open():
    send_command_to_mega("SOL_A:OPEN")


def solA_close():
    send_command_to_mega("SOL_A:CLOSE")


def solB_open():
    send_command_to_mega("SOL_B:OPEN")


def solB_close():
    send_command_to_mega("SOL_B:CLOSE")


def lights_on():
    send_command_to_mega("LIGHTS:ON")


def lights_off():
    send_command_to_mega("LIGHTS:OFF")
