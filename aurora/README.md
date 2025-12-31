# Aurora ESP32 MicroPython Snowmelt Rig

Fresh, modular layout for the ESP32 ↔ Arduino Mega snowmelt controller. The code mirrors the state machine described in the specification: BOOT → SNAPSHOT → DECIDE → TEST → SHUTDOWN → WAIT.

## Files
- `main.py` orchestrates the loop and calls into the test runners.
- `config.py` pin map, timing, temperature targets, and thresholds.
- `state_store.py` keeps tallies for sloped/non-sloped tests.
- `roles_store.py` maps DS18B20 ROMs into pavement/out/return roles.
- `sensors/` ultrasonic, DS18B20, SHT3x, and weather helpers.
- `actuators/` Mega UART wrapper plus heater, pump, lights, and tilt helpers.
- `control/` thermostat, decision, stop conditions, and test runners.
- `logging/` CSV logger and HTTP uploader.
- `pi_server/pi_upload_server.py` Flask upload target for the Raspberry Pi drop server.

## Configure
1. Edit `config.py` for Wi-Fi, mount height (`MOUNT_HEIGHT_CM`), actuator timings (`FULL_TRAVEL_TIME_S`, `HOME_TIME_S`), and thresholds.
2. Set the Raspberry Pi upload URL in `logging/uploader.py` (placeholder uses `config.WEATHER_URL`).
3. Populate `roles.json` with DS18B20 ROM assignments. If missing, a placeholder map is used and heater closed-loop aborts when no fluid sensor is found.

## Run
Execute `main.py` on the ESP32 (e.g., via `exec(open('main.py').read())`). The firmware prints the startup snapshot, decides on sloped vs non-sloped, logs every 10 seconds, uploads CSVs, and waits 20 minutes before repeating.
