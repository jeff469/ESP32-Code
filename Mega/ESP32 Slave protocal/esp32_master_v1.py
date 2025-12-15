# ESP32 MicroPython: master controller for Arduino Mega (H-bridge relays)
# File: esp32_master_v1.py
#
# Responsibilities:
#   - Talk to Arduino Mega over UART2
#   - Send single-character commands to:
#       * Drive actuator UP / DOWN / STOP
#       * Turn Pump / Heater ON or OFF
#       * Open / Close Solenoid A & B
#   - Provide helper functions to move the actuator to a target angle
#     using simple time-based estimation (no feedback).

from machine import UART
import time

# ====== CONFIG ======
# UART2 on ESP32:
#   TX=17 -> Mega RX1 (pin 19)
#   RX=16 -> Mega TX1 (pin 18)
uart = UART(2, baudrate=9600, tx=17, rx=16)

# Actuator timing: 0° -> 45° in 8 seconds (measured or estimated)
FULL_TRAVEL_ANGLE = 45.0      # degrees
FULL_TRAVEL_TIME = 8.0        # seconds

# Our best estimate of current angle (0 = flat, 45 = fully raised)
current_angle = 0.0


# ====== LOW-LEVEL COMMAND SENDER ======
def send_command(cmd):
    """
    Send a single-character command to the Mega over UART.

    The Mega code understands:
      U / u : actuator EXTEND
      D / d : actuator RETRACT
      S / s : actuator STOP
      P     : Pump ON
      p     : Pump OFF
      H     : Heater ON
      h     : Heater OFF
      A     : Solenoid A ON
      a     : Solenoid A OFF
      B     : Solenoid B ON
      b     : Solenoid B OFF
    """
    if isinstance(cmd, str):
        cmd = cmd.encode()  # convert Python string -> bytes
    uart.write(cmd)
    print("Sent to Mega:", cmd)


# ====== ACTUATOR (H-BRIDGE) COMMANDS ======
def raise_actuator():
    """Tell Mega to drive actuator UP (extend)."""
    # Mega accepts both 'U' and 'u'; we use uppercase for clarity
    send_command('U')


def lower_actuator():
    """Tell Mega to drive actuator DOWN (retract)."""
    # Mega accepts both 'D' and 'd'
    send_command('D')


def stop_actuator():
    """Tell Mega to STOP the actuator (all H-bridge relays off)."""
    # Mega accepts both 'S' and 's'
    send_command('S')


# ====== EXTRA RELAY COMMANDS (PUMP, HEATER, SOLENOIDS) ======
def pump_on():
    """Turn Pump relay ON on the Mega."""
    send_command('P')


def pump_off():
    """Turn Pump relay OFF on the Mega."""
    send_command('p')


def heater_on():
    """Turn Heater relay ON on the Mega."""
    send_command('H')


def heater_off():
    """Turn Heater relay OFF on the Mega."""
    send_command('h')


def solenoid_a_on():
    """Turn Solenoid A ON (open)."""
    send_command('A')


def solenoid_a_off():
    """Turn Solenoid A OFF (closed)."""
    send_command('a')


def solenoid_b_on():
    """Turn Solenoid B ON (open)."""
    send_command('B')


def solenoid_b_off():
    """Turn Solenoid B OFF (closed)."""
    send_command('b')


# ====== ANGLE / TIMING HELPERS ======
def set_current_angle(angle_deg):
    """
    Manually set our software angle estimate.

    Call this after you "home" the system, e.g.:
      1) Fully retract actuator until it's flat at 0°
      2) Call: set_current_angle(0)

    So our time-based movements stay roughly accurate.
    """
    global current_angle
    angle_deg = float(angle_deg)
    # Clamp to [0, FULL_TRAVEL_ANGLE]
    angle_deg = max(0.0, min(FULL_TRAVEL_ANGLE, angle_deg))
    current_angle = angle_deg
    print("Current angle set to ~", current_angle, "deg")


def _move_for(direction, seconds):
    """
    Internal helper: move actuator UP or DOWN for a given time,
    then stop and update current_angle based on travel time.

    direction: 'up' or 'down'
    seconds  : how long to move in that direction
    """
    global current_angle

    seconds = float(seconds)
    if seconds <= 0:
        return

    # Start motion in requested direction
    if direction == 'up':
        print("Moving UP for", seconds, "s")
        raise_actuator()
    elif direction == 'down':
        print("Moving DOWN for", seconds, "s")
        lower_actuator()
    else:
        print("Unknown direction:", direction)
        return

    # Block while motion is happening (simple, no feedback)
    time.sleep(seconds)

    # Stop motion
    stop_actuator()
    print("Stopped actuator.")

    # Update estimated angle based on proportion of full travel
    delta_angle = (seconds / FULL_TRAVEL_TIME) * FULL_TRAVEL_ANGLE
    if direction == 'up':
        current_angle += delta_angle
    else:
        current_angle -= delta_angle

    # Clamp estimate to [0, FULL_TRAVEL_ANGLE]
    if current_angle < 0.0:
        current_angle = 0.0
    if current_angle > FULL_TRAVEL_ANGLE:
        current_angle = FULL_TRAVEL_ANGLE

    print("Estimated angle now ~", current_angle, "deg")


def set_angle(target_angle_deg):
    """
    Move actuator to a desired angle between 0 and FULL_TRAVEL_ANGLE.

    Uses time-based estimation only (no angle sensor), assuming:
      0 -> FULL_TRAVEL_ANGLE takes FULL_TRAVEL_TIME seconds.

    Steps:
      - Clamp target angle
      - Compute delta between current and target
      - Convert delta angle to move time
      - Move UP or DOWN for that time
    """
    global current_angle

    # Clamp target to [0, FULL_TRAVEL_ANGLE]
    target_angle_deg = float(target_angle_deg)
    target_angle_deg = max(0.0, min(FULL_TRAVEL_ANGLE, target_angle_deg))

    print("\nRequest to move to ~", target_angle_deg, "deg")
    print("Current estimate ~", current_angle, "deg")

    delta = target_angle_deg - current_angle

    # If we're already close, just snap and stop
    if abs(delta) < 0.5:
        print("Already within 0.5 deg, stopping.")
        stop_actuator()
        current_angle = target_angle_deg
        return

    # Time needed for this angle change (proportional)
    seconds = abs(delta) * FULL_TRAVEL_TIME / FULL_TRAVEL_ANGLE

    # Decide direction based on sign of delta
    if delta > 0:
        direction = 'up'
    else:
        direction = 'down'

    _move_for(direction, seconds)


print("\nESP32 MicroPython master ready.")
print("Helpers you can call from the REPL:")
print("  set_current_angle(0)          # call after homing flat")
print("  set_angle(30)                 # move to ~30 degrees")
print("  raise_actuator(), lower_actuator(), stop_actuator()")
print("  pump_on(), pump_off()")
print("  heater_on(), heater_off()")
print("  solenoid_a_on(), solenoid_a_off()")
print("  solenoid_b_on(), solenoid_b_off()")
