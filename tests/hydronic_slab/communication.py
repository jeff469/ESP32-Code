"""
UART helpers for talking to the Arduino Mega.
"""
import time
from machine import Pin, UART

ESP32_TX_PIN = 17
ESP32_RX_PIN = 16
MEGA_BAUD = 115200

uart = UART(
    2,
    baudrate=MEGA_BAUD,
    tx=Pin(ESP32_TX_PIN),
    rx=Pin(ESP32_RX_PIN),
    timeout=100,
)


def send_command_to_mega(cmd):
    """Send a command string to the Arduino Mega via UART, with newline."""
    line = (cmd + "\n").encode("utf-8")
    uart.write(line)
    print("-> MEGA:", cmd)


def read_line_from_mega(timeout_ms=200):
    """
    Attempt to read one line from the Mega within ``timeout_ms``.

    Returns the decoded line (without trailing newline) or ``None`` if no data
    is received.
    """
    start = time.ticks_ms()
    buf = b""
    while time.ticks_diff(time.ticks_ms(), start) < timeout_ms:
        if uart.any():
            ch = uart.read(1)
            if ch in (b"\n", b"\r"):
                if buf:
                    try:
                        line = buf.decode("utf-8").strip()
                    except UnicodeError:
                        line = ""
                    print("<- MEGA:", line)
                    return line
                continue
            buf += ch
        else:
            time.sleep_ms(5)
    return None
