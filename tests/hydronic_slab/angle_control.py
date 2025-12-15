"""Angle control helpers for positioning the slab."""
import time
from tests.hydronic_slab.actuators import actuators_move_down, actuators_move_up, actuators_stop
from tests.hydronic_slab.sensors.mega import request_slab_angle_deg
from tests.hydronic_slab.state import ANGLE_TOLERANCE, NON_TILTED_ANGLE_DEG


def set_target_angle(angle_deg, timeout_s=60):
    """Move the slab to ``angle_deg`` with simple on/off control."""
    start_time = time.time()
    while True:
        current_angle = request_slab_angle_deg()
        if current_angle is None:
            print("Angle read failed; continuing to move up a bit...")
            actuators_move_up()
            time.sleep(0.5)
            continue

        error = angle_deg - current_angle
        if abs(error) <= ANGLE_TOLERANCE:
            actuators_stop()
            print("Angle reached:", current_angle)
            return

        if error > 0:
            actuators_move_up()
        else:
            actuators_move_down()

        if time.time() - start_time > timeout_s:
            print("Timeout while trying to reach angle", angle_deg)
            actuators_stop()
            return

        time.sleep(0.2)


def set_non_tilt_angle():
    """Move slab to the default non-tilted angle used in energy tests."""
    set_target_angle(NON_TILTED_ANGLE_DEG)
