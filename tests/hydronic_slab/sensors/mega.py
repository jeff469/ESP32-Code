"""Sensor requests that are proxied through the Arduino Mega."""
from tests.hydronic_slab.communication import read_line_from_mega, send_command_to_mega


def _read_prefixed_value(prefix):
    line = read_line_from_mega()
    if line and line.startswith(prefix):
        try:
            value = float(line.split(":", 1)[1])
            print("Mega sensor ->", prefix, value)
            return value
        except ValueError:
            return None
    return None


def request_water_temp_C():
    send_command_to_mega("READ:WATER_TEMP")
    return _read_prefixed_value("WATER_TEMP:")


def request_flow_rate_L_min():
    send_command_to_mega("READ:FLOW")
    return _read_prefixed_value("FLOW:")


def request_slab_angle_deg():
    send_command_to_mega("READ:ANGLE")
    return _read_prefixed_value("ANGLE:")


def request_pump_current_A():
    send_command_to_mega("READ:PUMP_I")
    return _read_prefixed_value("PUMP_I:")


def request_return_water_temp_C():
    """Read the return-loop water temperature from the Mega."""
    send_command_to_mega("READ:RETURN_TEMP")
    return _read_prefixed_value("RETURN_TEMP:")


def request_embedded_thermometer_temps_C(expected=9):
    """Fetch the array of embedded slab thermometer readings.

    The Mega is expected to return a comma-separated list after the
    ``READ:THERM_ARRAY`` command in the format ``THERM_ARRAY:t1,t2,...``.
    Missing or malformed values are ignored so callers always receive a list
    of floats with length ``expected`` (padded with ``None`` when missing).
    """

    send_command_to_mega("READ:THERM_ARRAY")
    line = read_line_from_mega()
    if not line or not line.startswith("THERM_ARRAY:"):
        return [None for _ in range(expected)]

    payload = line.split(":", 1)[1]
    temps = []
    for part in payload.split(","):
        try:
            temps.append(float(part))
        except ValueError:
            temps.append(None)

    while len(temps) < expected:
        temps.append(None)
    temps = temps[:expected]
    print("Mega sensor -> embedded thermometers:", temps)
    return temps


def request_bin_id_states(expected=4):
    """Read the four bin ID sensor states for logging."""
    send_command_to_mega("READ:BIN_IDS")
    line = read_line_from_mega()
    if not line or not line.startswith("BIN_IDS:"):
        return [None for _ in range(expected)]

    payload = line.split(":", 1)[1]
    states = []
    for part in payload.split(","):
        part = part.strip()
        try:
            states.append(int(part))
        except ValueError:
            states.append(None)

    while len(states) < expected:
        states.append(None)
    states = states[:expected]
    print("Mega sensor -> bin IDs:", states)
    return states
