# Hydronic slab test explanations

Plain-English summaries of the behavior-focused tests in `test_behaviors.py`.

- **`test_is_snow_present_respects_threshold`** – Checks that snow detection flips to "present" when depth meets or exceeds the configured threshold and stays false just below it.
- **`test_call_tracing_prints`** – Ensures the call-tracing context prints function entries (including recorder calls) during an energy-test run and that the recorder finalizes.
- **`test_sample_recorder_saves_temperatures_without_bin_ids`** – Verifies sample CSVs include environmental readings, water temperature, snow depths, and embedded thermometer values (both aggregated and per-sensor columns) without any bin ID columns.
- **`test_energy_occurrence_counts_persist`** – Confirms occurrence counters for non-tilted test combinations increment per run and survive saving/loading state.
- **`test_energy_occurrence_survives_power_cycle`** – Simulates a power cycle to make sure energy-test occurrence counts persist across runs when state is saved to disk and reloaded.
- **`test_power_use_estimator_tracks_pump_and_heater`** – Validates that tracked pump and heater watt-hours accumulate correctly based on on/off durations.
- **`test_energy_test_stops_when_embedded_hits_one`** – Checks that a no-snow energy test logs samples every 10 seconds and terminates once average embedded temperatures drop to 1 °C or below.
- **`test_tilted_test_samples_every_ten_seconds`** – Confirms tilted runs capture samples at 10-second intervals, log snow-depth decay, and keep elapsed-time stamps as expected.
- **`test_tilted_test_stops_once_snow_within_clear_threshold`** – Verifies a tilted test ends once snow depth reaches the melt threshold (within 1 mm), without waiting for exact zero.
- **`test_main_routes_tests_by_snow`** – Ensures the main loop dispatches to tilted tests when snow is present and energy tests when snow is absent.
- **`test_main_runs_tilted_when_snow_at_or_above_threshold`** – Double-checks the main loop picks a tilted test when measured snow depth is at/above the configured presence threshold.
- **`test_main_runs_energy_when_snow_below_threshold`** – Double-checks the main loop picks an energy test when measured snow depth falls below the presence threshold.
- **`test_randomized_energy_runs_increment_occurrence`** – Runs multiple randomized energy tests in the same environmental bin to confirm occurrence counts accumulate and recorders finalize.
- **`test_tilted_runs_progress_angle_bins`** – Runs sequential tilted tests in one snow bin to ensure repetition tracking steps through 0/10/20/30/40 degree angles.
- **`test_tilted_models_gradual_snow_melt`** – Asserts the melt model drives snow depth downward between samples even if the sensor reading stays flat, stopping at the clear threshold.
- **`test_thermostat_switches_modes`** – Checks thermostat logic opens/closes solenoids and toggles the heater when water temperature crosses the deadband around the setpoint.
- **`test_two_hour_simulation_produces_six_tests`** – Simulates six 20-minute cycles (about two hours) to confirm alternating tilted/energy runs record CSV samples, log energy use, and advance fake time accordingly.
