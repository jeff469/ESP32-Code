# mp_fresh

Minimal MicroPython control loop for ESP32 with Arduino Mega over UART2. Designed to run via `exec(open("main.py").read())`.

## Hardware map
- UART2 (TX=17, RX=16) @ 9600 baud to Arduino Mega for pump/heater/actuator commands.
- Ultrasonic (real): TRIG=18, ECHO=19 using `machine.time_pulse_us`.
- Ambient SHT3x: I2C(1) SDA=21, SCL=22 @ 0x44.
- Flow sensor: GPIO5 falling-edge IRQ, 2 ms debounce, 1.5 s window (pulses/min estimate).
- Fluid thermometer: DS18B20 on GPIO4 (750 ms conversion).
- Stubs: 3 ultrasonics, 1 extra fluid thermometer, 2 ambient sensors, 3 flow sensors, wind speed/direction, 10 pavement temps.

## Operation
1. Snow depth = `PRESET_CLEAR_DISTANCE_CM - avg(4 ultrasonics)`. If ≥ 5 cm → tilted test else non-tilted.
2. Bin ID `(tbin,hbin,sbin,dbin)` from ambient temp/humidity, wind speed/direction with widths (4 °C, 3 %, 3 m/s, 3 dir sectors), clamped to max indices temp/humidity/speed=3 and direction=2.
3. Bin counts persist in `state/bin_counts.json`.

### Tilted test
- Bin count→angle: 0→0°,1→10°,2→20°,3→30°,4→40° then reset to 0.
- Heat fluid to 36 °C, move actuator to angle, pump ON.
- Log every 10 s to `/logs/YYYYMMDD_HHMMSS_trialNN_tilted.csv`.
- Stop when snow depth ≤1 cm or 15 min elapsed. Then slope 5°, pump/heater OFF, rest ~1 min.

### Non-tilted test
- Bin count→target temp: [36, 36×1.05, 36×1.10, 36×1.15, 36×0.95, 36×0.90, 36×0.85] then reset.
- Heat to target, angle 0°, pump ON.
- Stop when avg pavement ≥0.7 °C or 15 min. Then slope 5°, pump/heater OFF, rest ~1 min.

## Testing modes
- Set `SMOKE_TEST=True` in `config.py` to read each real sensor once and send Mega commands `H→h`, `P→p`, `U→S→D→S`. All actions print to serial.
- Set `DIAGNOSTIC_TEST=True` to gather multiple sensor samples (count/delay configured in `DIAG_SAMPLE_COUNT`/`DIAG_SAMPLE_DELAY_S`), print the active bin ID per sample, and run the smoke test sequence.

## Files
- `config.py` constants and pin map.
- `sensors.py` real/stub sensor helpers.
- `mega.py` UART command helpers with local prints.
- `glacial_state.py` persistent bin counts and trial counter.
- `logger.py` CSV logger utilities.
- `main.py` orchestrates snow decision tree and trial loops.
- `state/bin_counts.json` created automatically on first run.

Heating guard: `HEAT_TIMEOUT_SECONDS` (in `config.py`) stops the heater wait if the target temperature is never reached
to keep raw REPL access usable during hardware testing.

## Update & run on ESP32
Adjust the serial port as needed (example uses `COM4`).

```bash
# Copy project files to the device root
mpremote connect COM4 fs cp main.py :main.py config.py :config.py logger.py :logger.py glacial_state.py :glacial_state.py sensors.py :sensors.py mega.py :mega.py

# Remove any older frozen-style module that could shadow the new state file (ignore error if missing)
mpremote connect COM4 fs rm :state.py

# Verify the correct state module is visible
mpremote connect COM4 exec "import glacial_state; print(glacial_state.__file__); print('has load_state', hasattr(glacial_state, 'load_state'))"

# Run the program (respects SMOKE_TEST/DIAGNOSTIC_TEST/RUN_ONCE flags in config.py)
mpremote connect COM4 exec "exec(open('main.py').read())"
```
