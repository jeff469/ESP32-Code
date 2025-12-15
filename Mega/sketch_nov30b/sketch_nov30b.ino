// ============================================================
// GLACIAL Prototype - Arduino Mega Relay Driver
// ------------------------------------------------------------
// - Drives a 4-relay H-bridge for a linear actuator.
// - Drives 4 extra relays for:
//      Pump, Heater, Solenoid A, Solenoid B
// - Listens on Serial1 (pins 18/19) for single-character commands
//   from an ESP32 or other master.
//
// COMMANDS (from ESP32 over Serial1):
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
// These go to the input pins of your relay modules controlling
// the actuator motor wiring.
const int PIN_A_PLUS  = 22;  // A+
const int PIN_A_MINUS = 24;  // A-
const int PIN_B_PLUS  = 26;  // B+
const int PIN_B_MINUS = 28;  // B-

// ------------------------------------------------------------
// Extra relay pins (Pump, Heater, Sol A, Sol B)
// ------------------------------------------------------------
// Each goes to the input pin of a relay channel for that device.
const int PIN_PUMP    = 23;  // Pump relay
const int PIN_HEATER  = 25;  // Heater relay
const int PIN_SOL_A   = 27;  // Solenoid A
const int PIN_SOL_B   = 29;  // Solenoid B

// ------------------------------------------------------------
// Relay logic type
// ------------------------------------------------------------
// Your boards behave as ACTIVE-LOW:
//   - IN = LOW  -> relay ON (LED ON, clicks, load powered)
//   - IN = HIGH -> relay OFF
//
// Set this to true so the helper does the right thing.
const bool RELAYS_ACTIVE_LOW = true;

// Small helper so we can say setRelay(pin, true/false)
// and not worry about HIGH vs LOW each time.
void setRelay(int pin, bool on) {
  if (RELAYS_ACTIVE_LOW) {
    // Active-LOW: LOW = ON, HIGH = OFF
    digitalWrite(pin, on ? LOW : HIGH);
  } else {
    // Active-HIGH: HIGH = ON, LOW = OFF
    digitalWrite(pin, on ? HIGH : LOW);
  }
}

// ------------------------------------------------------------
// Actuator state enum & logic
// ------------------------------------------------------------

// Simple enum to remember what we *want* the actuator doing.
enum ActuatorState {
  ACT_STOP,
  ACT_EXTEND,
  ACT_RETRACT
};

// Store the current actuator command
ActuatorState currentState = ACT_STOP;

// Forward declaration of the function that applies the state
void applyActuatorState(ActuatorState state);

// Implementation: set the 4 H-bridge relays based on desired state
void applyActuatorState(ActuatorState state) {
  currentState = state;

  switch (state) {
    case ACT_STOP:
      // All H-bridge relays OFF -> motor not powered
      setRelay(PIN_A_PLUS,  false);
      setRelay(PIN_A_MINUS, false);
      setRelay(PIN_B_PLUS,  false);
      setRelay(PIN_B_MINUS, false);
      break;

    case ACT_EXTEND:
      // One polarity to extend actuator (example pattern)
      // A+ ON, A- OFF, B+ OFF, B- ON
      setRelay(PIN_A_PLUS,  true);
      setRelay(PIN_A_MINUS, false);
      setRelay(PIN_B_PLUS,  false);
      setRelay(PIN_B_MINUS, true);
      break;

    case ACT_RETRACT:
      // Opposite polarity to retract actuator
      // A+ OFF, A- ON, B+ ON, B- OFF
      setRelay(PIN_A_PLUS,  false);
      setRelay(PIN_A_MINUS, true);
      setRelay(PIN_B_PLUS,  true);
      setRelay(PIN_B_MINUS, false);
      break;
  }
}

// ------------------------------------------------------------
// setup() - runs once on boot/reset
// ------------------------------------------------------------

void setup() {
  // Configure all relay pins as outputs
  pinMode(PIN_A_PLUS,  OUTPUT);
  pinMode(PIN_A_MINUS, OUTPUT);
  pinMode(PIN_B_PLUS,  OUTPUT);
  pinMode(PIN_B_MINUS, OUTPUT);

  pinMode(PIN_PUMP,    OUTPUT);
  pinMode(PIN_HEATER,  OUTPUT);
  pinMode(PIN_SOL_A,   OUTPUT);
  pinMode(PIN_SOL_B,   OUTPUT);

  // Make sure everything starts OFF safely
  applyActuatorState(ACT_STOP);    // actuator H-bridge off
  setRelay(PIN_PUMP,   false);     // pump OFF
  setRelay(PIN_HEATER, false);     // heater OFF
  setRelay(PIN_SOL_A,  false);     // solenoid A OFF
  setRelay(PIN_SOL_B,  false);     // solenoid B OFF

  // USB serial for debugging
  Serial.begin(115200);

  // Serial1 is hardware UART1 on Mega:
  //   RX1 = pin 19, TX1 = pin 18
  // Connect ESP32 TX -> Mega RX1 (19)
  //         ESP32 RX -> Mega TX1 (18)
  Serial1.begin(9600);

  Serial.println("Mega relay driver ready.");
  Serial.println("Commands via Serial1:");
  Serial.println("  U/u = actuator EXTEND");
  Serial.println("  D/d = actuator RETRACT");
  Serial.println("  S/s = actuator STOP");
  Serial.println("  P   = pump ON, p = pump OFF");
  Serial.println("  H   = heater ON, h = heater OFF");
  Serial.println("  A   = solenoid A ON, a = OFF");
  Serial.println("  B   = solenoid B ON, b = OFF");
}

// ------------------------------------------------------------
// loop() - runs repeatedly
// ------------------------------------------------------------

void loop() {
  // Check if the ESP32 (or other master) sent us a byte on Serial1
  if (Serial1.available() > 0) {
    char cmd = Serial1.read();

    switch (cmd) {
      // ------------- Actuator commands -------------
      case 'U':
      case 'u':
        applyActuatorState(ACT_EXTEND);
        Serial.println("CMD: ACTUATOR EXTEND");
        break;

      case 'D':
      case 'd':
        applyActuatorState(ACT_RETRACT);
        Serial.println("CMD: ACTUATOR RETRACT");
        break;

      case 'S':
      case 's':
        applyActuatorState(ACT_STOP);
        Serial.println("CMD: ACTUATOR STOP");
        break;

      // ------------- Pump relay (P/p) --------------
      case 'P':   // Pump ON
        setRelay(PIN_PUMP, true);
        Serial.println("CMD: PUMP ON");
        break;

      case 'p':   // Pump OFF
        setRelay(PIN_PUMP, false);
        Serial.println("CMD: PUMP OFF");
        break;

      // ------------- Heater relay (H/h) ------------
      case 'H':   // Heater ON
        setRelay(PIN_HEATER, true);
        Serial.println("CMD: HEATER ON");
        break;

      case 'h':   // Heater OFF
        setRelay(PIN_HEATER, false);
        Serial.println("CMD: HEATER OFF");
        break;

      // ------------- Solenoid A (A/a) --------------
      case 'A':   // Solenoid A ON (open)
        setRelay(PIN_SOL_A, true);
        Serial.println("CMD: SOLENOID A ON");
        break;

      case 'a':   // Solenoid A OFF (closed)
        setRelay(PIN_SOL_A, false);
        Serial.println("CMD: SOLENOID A OFF");
        break;

      // ------------- Solenoid B (B/b) --------------
      case 'B':   // Solenoid B ON (open)
        setRelay(PIN_SOL_B, true);
        Serial.println("CMD: SOLENOID B ON");
        break;

      case 'b':   // Solenoid B OFF (closed)
        setRelay(PIN_SOL_B, false);
        Serial.println("CMD: SOLENOID B OFF");
        break;

      default:
        // Unknown command: ignore (or print if you want)
        // Serial.print("Unknown cmd: "); Serial.println(cmd);
        break;
    }
  }

  // You can add safety checks here:
  // - limit switches
  // - watchdog for stuck actuator
  // - overcurrent detection
}
