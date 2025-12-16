"""Entry point for the hydronic slab prototype split into modules."""
import time

from tests.hydronic_slab.actuators import actuators_stop
from tests.hydronic_slab.event_logger import init_log_file
from tests.hydronic_slab.sensors.environment import (
    read_air_temperature_C,
    read_relative_humidity,
    read_wind_direction_deg,
    read_wind_speed_mps,
)
from tests.hydronic_slab.sensors.mega import request_slab_angle_deg
from tests.hydronic_slab.sensors.ultrasonic import measure_snow_depth_mm
from tests.hydronic_slab.state import (
    bin_non_tilt_env,
    get_last_known_angle,
    is_snow_present,
    load_state,
    update_last_angle,
)
from tests.hydronic_slab.test_routines import run_energy_test, run_tilted_test


def main(cycle_period_s=20 * 60, max_cycles=None):
    load_state()
    init_log_file()

    initial_angle = request_slab_angle_deg()
    if initial_angle is not None:
        print("Initial slab angle from sensor:", initial_angle)
        update_last_angle(initial_angle)
    else:
        fallback_angle = get_last_known_angle()
        update_last_angle(fallback_angle)
        print(
            "Initial slab angle unavailable; using last recorded/default angle:",
            fallback_angle,
        )
        actuators_stop()

    cycle_count = 0
    while True:
        cycle_start = time.time()

        snow_depth = measure_snow_depth_mm()
        air_temp = read_air_temperature_C()
        humidity = read_relative_humidity()
        wind_speed = read_wind_speed_mps()
        wind_dir = read_wind_direction_deg()

        env = {
            "snow_depth": snow_depth,
            "air_temp": air_temp,
            "humidity": humidity,
            "wind_speed": wind_speed,
            "wind_dir": wind_dir,
        }

        env_bin = bin_non_tilt_env(air_temp, humidity, wind_speed, wind_dir)
        env["env_bin"] = env_bin

        print(
            "New cycle: snow_depth = {:.1f} mm, air_temp = {:.1f} °C, env_bin = {}".format(
                snow_depth, air_temp, env_bin
            )
        )

        if is_snow_present(snow_depth):
            print("Snow present -> running tilted melt-time test.")
            run_tilted_test(env)
        else:
            print("No snow -> running non-tilted energy test.")
            run_energy_test(env)

        cycle_end = time.time()
        elapsed = cycle_end - cycle_start
        remaining = cycle_period_s - elapsed
        if remaining > 0:
            print("Cycle complete. Sleeping for", remaining, "seconds.")
            time.sleep(remaining)
        else:
            print("Cycle overran period; starting next cycle now.")

        cycle_count += 1
        if max_cycles is not None and cycle_count >= max_cycles:
            print("Reached max_cycles =", max_cycles, "-> exiting main loop.")
            break


if __name__ == "__main__":
    main()
