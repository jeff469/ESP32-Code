// ============================================================
// GLACIAL Prototype - Arduino Mega Relay + Sensor Driver
// ------------------------------------------------------------
// - Drives a 4-relay H-bridge for a linear actuator.
// - Drives 4 extra relays for:
//      Pump, Heater, Solenoid A, Solenoid B
// - Optionally drives a Lights relay.
// - Listens on Serial1 (pins 18/19) for commands from ESP32.
//
// COMMANDS (line-based from ESP32 over Serial1):
//
//  ---- Actuators ----
//  "ACT:UP"      -> actuator EXTEND
//  "ACT:DOWN"    -> actuator RETRACT
//  "ACT:STOP"    -> actuator STOP
//
//  ---- Relays ----
//  "PUMP:ON"     -> Pump ON
//  "PUMP:OFF"    -> Pump OFF
//  "HEATER:ON"   -> Heater ON
//  "HEATER:OFF"  -> Heater OFF
//  "SOL_A:OPEN"  -> Solenoid A ON
//  "SOL_A:CLOSE" -> Solenoid A OFF
//  "SOL_B:OPEN"  -> Solenoid B ON
//  "SOL_B:CLOSE" -> Solenoid B OFF
//  "LIGHTS:ON"   -> Lights ON
//  "LIGHTS:OFF"  -> Lights OFF
//
//  ---- Sensor reads (ESP32 expects a reply line) ----
//  "READ:WATER_TEMP" -> reply "WATER_TEMP:<value>\n"
//  "READ:FLOW"       -> reply "FLOW:<value>\n"
//  "READ:ANGLE"      -> reply "ANGLE:<value>\n"
//  "READ:PUMP_I"     -> reply "PUMP_I:<value>\n"
//
//  ---- Legacy single-character commands (still supported) ----
//   U / u : actuator EXTEND
//   D / d : actuator RETRACT
//   S / s : actuator STOP
//   P     : Pump ON
//   p     : Pump OFF
//   H     : Heater ON
//   h     : Heater OFF
//   A     : Solenoid A ON
//   a     : Solenoid A OFF
//   B     : Solenoid B ON
//   b     : Solenoid B OFF
// ============================================================

#include <Arduino.h>

// ------------------------------------------------------------
// H-bridge relay pins for actuator
// ------------------------------------------------------------
const int PIN_A_PLUS  = 22;  // A+
const int PIN_A_MINUS = 24;  // A-
const int PIN_B_PLUS  = 26;  // B+
const int PIN_B_MINUS = 28;  // B-

// ------------------------------------------------------------
// Extra relay pins (Pump, Heater, Sol A, Sol B, Lights)
// ------------------------------------------------------------
const int PIN_PUMP    = 23;  // Pump relay
const int PIN_HEATER  = 25;  // Heater relay
const int PIN_SOL_A   = 27;  // Solenoid A
const int PIN_SOL_B   = 29;  // Solenoid B
const int PIN_LIGHTS  = 31;  // Lights (adjust if needed)

// ------------------------------------------------------------
// Relay logic type
// ------------------------------------------------------------
// ACTIVE-LOW:
//   - IN = LOW  -> relay ON
//   - IN = HIGH -> relay OFF
const bool RELAYS_ACTIVE_LOW = true;

void setRelay(int pin, bool on) {
  if (RELAYS_ACTIVE_LOW) {
    digitalWrite(pin, on ? LOW : HIGH);
  } else {
    digitalWrite(pin, on ? HIGH : LOW);
  }
}

// ------------------------------------------------------------
// Actuator state enum & logic
// ------------------------------------------------------------
enum ActuatorState {
  ACT_STOP,
  ACT_EXTEND,
  ACT_RETRACT
};

ActuatorState currentState = ACT_STOP;

void applyActuatorState(ActuatorState state) {
  currentState = state;

  switch (state) {
    case ACT_STOP:
      setRelay(PIN_A_PLUS,  false);
      setRelay(PIN_A_MINUS, false);
      setRelay(PIN_B_PLUS,  false);
      setRelay(PIN_B_MINUS, false);
      break;

    case ACT_EXTEND:
      // Example polarity for extend:
      // A+ ON, A- OFF, B+ OFF, B- ON
      setRelay(PIN_A_PLUS,  true);
      setRelay(PIN_A_MINUS, false);
      setRelay(PIN_B_PLUS,  false);
      setRelay(PIN_B_MINUS, true);
      break;

    case ACT_RETRACT:
      // Opposite polarity for retract:
      // A+ OFF, A- ON, B+ ON, B- OFF
      setRelay(PIN_A_PLUS,  false);
      setRelay(PIN_A_MINUS, true);
      setRelay(PIN_B_PLUS,  true);
      setRelay(PIN_B_MINUS, false);
      break;
  }
}

// ------------------------------------------------------------
// Stub sensor functions (replace with real sensors later)
// ------------------------------------------------------------
// These match what the ESP32 expects to receive as values.

float readWaterTempC() {
  // TODO: replace with real sensor (e.g., analogRead + conversion)
  return 25.0;  // placeholder
}

float readFlowLpm() {
  // TODO: replace with flow sensor logic
  return 1.23;  // placeholder
}

float readAngleDeg() {
  // TODO: replace with angle/tilt sensor or encoder
  return 5.0;   // placeholder (e.g., near non-tilt)
}

float readPumpCurrentA() {
  // TODO: replace with current sensor logic
  return 0.80;  // placeholder
}

// ------------------------------------------------------------
// Command handling
// ------------------------------------------------------------

String cmdBuffer;  // accumulates characters until newline

void handleStringCommand(const String &cmd) {
  // --------- Actuator commands ----------
  if (cmd == "ACT:UP") {
    applyActuatorState(ACT_EXTEND);
    Serial.println("CMD: ACTUATOR EXTEND");
  } else if (cmd == "ACT:DOWN") {
    applyActuatorState(ACT_RETRACT);
    Serial.println("CMD: ACTUATOR RETRACT");
  } else if (cmd == "ACT:STOP") {
    applyActuatorState(ACT_STOP);
    Serial.println("CMD: ACTUATOR STOP");

  // --------- Pump ----------
  } else if (cmd == "PUMP:ON") {
    setRelay(PIN_PUMP, true);
    Serial.println("CMD: PUMP ON");
  } else if (cmd == "PUMP:OFF") {
    setRelay(PIN_PUMP, false);
    Serial.println("CMD: PUMP OFF");

  // --------- Heater ----------
  } else if (cmd == "HEATER:ON") {
    setRelay(PIN_HEATER, true);
    Serial.println("CMD: HEATER ON");
  } else if (cmd == "HEATER:OFF") {
    setRelay(PIN_HEATER, false);
    Serial.println("CMD: HEATER OFF");

  // --------- Solenoid A ----------
  } else if (cmd == "SOL_A:OPEN") {
    setRelay(PIN_SOL_A, true);
    Serial.println("CMD: SOLENOID A ON");
  } else if (cmd == "SOL_A:CLOSE") {
    setRelay(PIN_SOL_A, false);
    Serial.println("CMD: SOLENOID A OFF");

  // --------- Solenoid B ----------
  } else if (cmd == "SOL_B:OPEN") {
    setRelay(PIN_SOL_B, true);
    Serial.println("CMD: SOLENOID B ON");
  } else if (cmd == "SOL_B:CLOSE") {
    setRelay(PIN_SOL_B, false);
    Serial.println("CMD: SOLENOID B OFF");

  // --------- Lights (optional) ----------
  } else if (cmd == "LIGHTS:ON") {
    setRelay(PIN_LIGHTS, true);
    Serial.println("CMD: LIGHTS ON");
  } else if (cmd == "LIGHTS:OFF") {
    setRelay(PIN_LIGHTS, false);
    Serial.println("CMD: LIGHTS OFF");

  // --------- Sensor reads (reply back on Serial1) ----------
  } else if (cmd == "READ:WATER_TEMP") {
    float val = readWaterTempC();
    Serial.print("READ WATER_TEMP -> ");
    Serial.println(val, 2);
    Serial1.print("WATER_TEMP:");
    Serial1.println(val, 2);

  } else if (cmd == "READ:FLOW") {
    float val = readFlowLpm();
    Serial.print("READ FLOW -> ");
    Serial.println(val, 2);
    Serial1.print("FLOW:");
    Serial1.println(val, 2);

  } else if (cmd == "READ:ANGLE") {
    float val = readAngleDeg();
    Serial.print("READ ANGLE -> ");
    Serial.println(val, 2);
    Serial1.print("ANGLE:");
    Serial1.println(val, 2);

  } else if (cmd == "READ:PUMP_I") {
    float val = readPumpCurrentA();
    Serial.print("READ PUMP_I -> ");
    Serial.println(val, 2);
    Serial1.print("PUMP_I:");
    Serial1.println(val, 2);

  } else if (cmd.length() == 1) {
    // --------- Legacy single byte commands ----------
    char c = cmd[0];
    switch (c) {
      case 'U':
      case 'u':
        applyActuatorState(ACT_EXTEND);
        Serial.println("CMD: (legacy) ACTUATOR EXTEND");
        break;
      case 'D':
      case 'd':
        applyActuatorState(ACT_RETRACT);
        Serial.println("CMD: (legacy) ACTUATOR RETRACT");
        break;
      case 'S':
      case 's':
        applyActuatorState(ACT_STOP);
        Serial.println("CMD: (legacy) ACTUATOR STOP");
        break;

      case 'P':
        setRelay(PIN_PUMP, true);
        Serial.println("CMD: (legacy) PUMP ON");
        break;
      case 'p':
        setRelay(PIN_PUMP, false);
        Serial.println("CMD: (legacy) PUMP OFF");
        break;

      case 'H':
        setRelay(PIN_HEATER, true);
        Serial.println("CMD: (legacy) HEATER ON");
        break;
      case 'h':
        setRelay(PIN_HEATER, false);
        Serial.println("CMD: (legacy) HEATER OFF");
        break;

      case 'A':
        setRelay(PIN_SOL_A, true);
        Serial.println("CMD: (legacy) SOLENOID A ON");
        break;
      case 'a':
        setRelay(PIN_SOL_A, false);
        Serial.println("CMD: (legacy) SOLENOID A OFF");
        break;

      case 'B':
        setRelay(PIN_SOL_B, true);
        Serial.println("CMD: (legacy) SOLENOID B ON");
        break;
      case 'b':
        setRelay(PIN_SOL_B, false);
        Serial.println("CMD: (legacy) SOLENOID B OFF");
        break;

      default:
        // Unknown single-char command: ignore
        break;
    }
  } else {
    // Unknown string command
    Serial.print("Unknown cmd: ");
    Serial.println(cmd);
  }
}

// ------------------------------------------------------------
// setup() - runs once on boot/reset
// ------------------------------------------------------------

void setup() {
  pinMode(PIN_A_PLUS,  OUTPUT);
  pinMode(PIN_A_MINUS, OUTPUT);
  pinMode(PIN_B_PLUS,  OUTPUT);
  pinMode(PIN_B_MINUS, OUTPUT);

  pinMode(PIN_PUMP,    OUTPUT);
  pinMode(PIN_HEATER,  OUTPUT);
  pinMode(PIN_SOL_A,   OUTPUT);
  pinMode(PIN_SOL_B,   OUTPUT);
  pinMode(PIN_LIGHTS,  OUTPUT);

  applyActuatorState(ACT_STOP);
  setRelay(PIN_PUMP,   false);
  setRelay(PIN_HEATER, false);
  setRelay(PIN_SOL_A,  false);
  setRelay(PIN_SOL_B,  false);
  setRelay(PIN_LIGHTS, false);

  Serial.begin(115200);

  // IMPORTANT: match ESP32 baudrate (Base.py uses 115200)
  Serial1.begin(115200);

  Serial.println("Mega relay + sensor driver ready.");
  Serial.println("Listening for line-based commands on Serial1.");
}

// ------------------------------------------------------------
// loop() - runs repeatedly
// ------------------------------------------------------------

void loop() {
  // Accumulate characters from Serial1 until newline, then handle.
  while (Serial1.available() > 0) {
    char c = Serial1.read();

    if (c == '\r' || c == '\n') {
      if (cmdBuffer.length() > 0) {
        String cmd = cmdBuffer;
        cmdBuffer = "";
        cmd.trim();
        if (cmd.length() > 0) {
          handleStringCommand(cmd);
        }
      }
    } else {
      cmdBuffer += c;
      // Optional: protect against runaway long strings
      if (cmdBuffer.length() > 64) {
        cmdBuffer = ""; // reset if too long / corrupted
      }
    }
  }

  // You can add safety checks here (limit switches, watchdog, etc.)
}

