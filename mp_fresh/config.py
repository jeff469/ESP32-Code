# MicroPython configuration for mp_fresh project
# Avoid forbidden imports; keep constants simple.

SMOKE_TEST = False
DIAGNOSTIC_TEST = False
RUN_ONCE = True
DIAG_SAMPLE_COUNT = 3
DIAG_SAMPLE_DELAY_S = 1

# Pin assignments
ULTRASONIC_PINS = {
    "trig": 18,
    "echo": 19,
}

FLOW_PIN = 5
DS18B20_PIN = 4
I2C_SDA = 21
I2C_SCL = 22
SHT3X_ADDR = 0x44

UART2_TX = 17
UART2_RX = 16
UART_BAUD = 9600

PRESET_CLEAR_DISTANCE_CM = 100.0
SNOW_THRESHOLD_CM = 5.0
SNOW_CLEAR_CM = 1.0
TARGET_TEMP_C = 36.0
PAVEMENT_CLEAR_C = 0.7

TILTED_MAX_ANGLE = 40
NON_TILTED_TARGETS = [
    TARGET_TEMP_C,
    TARGET_TEMP_C * 1.05,
    TARGET_TEMP_C * 1.10,
    TARGET_TEMP_C * 1.15,
    TARGET_TEMP_C * 0.95,
    TARGET_TEMP_C * 0.90,
    TARGET_TEMP_C * 0.85,
]

FLOW_WINDOW_MS = 1500
FLOW_DEBOUNCE_US = 2000

# Shortened rest to speed up repeated readings during testing
TRIAL_REST_SECONDS = 60
TRIAL_MAX_SECONDS = 15 * 60
LOG_INTERVAL_SECONDS = 10

# Heating safety/timeout
HEAT_TIMEOUT_SECONDS = 120

BIN_WIDTH_TEMP = 4
BIN_WIDTH_HUM = 3
BIN_WIDTH_WIND_SPEED = 3
BIN_WIDTH_WIND_DIR = 3
# Bin indices are capped to these maxima (0-based). With width settings
# above, this yields four bins for temp/humidity/wind speed (0-3).
BIN_MAX_TEMP = 3
BIN_MAX_HUM = 3
BIN_MAX_WIND_SPEED = 3
BIN_MAX_WIND_DIR = 2

STATE_PATH = "state/bin_counts.json"
LOG_DIR = "logs"

# Actuator motion estimate (deg/s). Keep directional values so timing can
# reflect any asymmetry in the actuator.
ACTUATOR_UP_DEG_PER_SEC = 5
ACTUATOR_DOWN_DEG_PER_SEC = 5
# Extra buffer seconds to account for start/stop lag when changing angles.
ACTUATOR_MOVE_BUFFER_S = 0.25

# Stub values
STUB_ULTRASONIC_CM = 100.0
STUB_FLUID_TEMP_C = 25.0
STUB_AMBIENT = (2.0, 60.0)
STUB_FLOW_PULSES_PER_WINDOW = 0
STUB_WIND = (1.0, 90)
STUB_PAVEMENT_TEMP_C = 0.2

# Wi-Fi + weather API (GeoMet SWOB) settings for wind sourcing
WIFI_SSID = "YOUR_WIFI_NAME"
WIFI_PASS = "YOUR_WIFI_PASSWORD"
WIND_STATION_CODE = "COGI"
WIND_API_URL = (
    "https://api.weather.gc.ca/collections/swob-realtime/items"
    "?lang=en&sortby=-date_tm-value&url="
    + WIND_STATION_CODE
    + "&limit=1&properties="
    "avg_wnd_spd_10m_pst2mts,avg_wnd_dir_10m_pst2mts"
    "&f=json"
)
WIND_API_CACHE_SECONDS = 300
