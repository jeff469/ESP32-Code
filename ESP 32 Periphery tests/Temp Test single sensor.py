import machine, time

# Try importing OneWire & DS18B20 support, if available
try:
    import onewire, ds18x20
    HAVE_ONEWIRE = True
except ImportError:
    HAVE_ONEWIRE = False

# ========= 1) I2C SCANNER =========

def scan_i2c():
    """
    Scan for I2C devices on typical ESP32 I2C pins:
      - SDA = 21
      - SCL = 22
    """
    print("=== I2C SCAN (SDA=21, SCL=22) ===")
    try:
        i2c = machine.I2C(0, scl=machine.Pin(22), sda=machine.Pin(21), freq=400000)
        devices = i2c.scan()
    except Exception as e:
        print("I2C error:", e)
        return

    if not devices:
        print("No I2C devices found.")
    else:
        print("I2C devices found at addresses:")
        for addr in devices:
            print("  - 0x{:02X}".format(addr))
    print()


# ========= 2) ONE-WIRE SCANNER (DS18B20/etc) =========

# Pins we’ll test for OneWire devices (you can add/remove)
ONEWIRE_TEST_PINS = [2, 4, 5, 12, 13, 14, 15, 16, 17]

def scan_onewire():
    """
    Try multiple pins to find any OneWire devices (DS18B20 etc.).
    For each candidate GPIO, we:
      - create a OneWire bus
      - scan for ROMs
      - if any found, try reading temperature if DS18B20 support exists
    """
    if not HAVE_ONEWIRE:
        print("OneWire / DS18X20 modules not available; skipping OneWire scan.")
        return

    print("=== OneWire SCAN on pins:", ONEWIRE_TEST_PINS, "===")

    for pin_num in ONEWIRE_TEST_PINS:
        pin = machine.Pin(pin_num)

        try:
            ow = onewire.OneWire(pin)
            roms = ow.scan()
        except Exception as e:
            print("GPIO", pin_num, ": OneWire error:", e)
            continue

        if not roms:
            # No devices on this pin
            # print("GPIO", pin_num, ": no OneWire devices.")
            continue

        print("GPIO", pin_num, ": OneWire devices found:")
        for rom in roms:
            rom_hex = ''.join('{:02X}'.format(b) for b in rom)
            print("  ROM:", rom, " ->", rom_hex)

        # If we have DS18X20 support, try reading temps
        try:
            ds = ds18x20.DS18X20(ow)
            ds.convert_temp()
            time.sleep_ms(750)
            for rom in roms:
                temp_c = ds.read_temp(rom)
                print("    Temp from", rom_hex, ": ", temp_c, "°C")
        except Exception as e:
            print("  (Could not read as DS18B20, maybe it's a different 1-Wire type?)")

    print()


# ========= MAIN LOOP =========

def main():
    while True:
        print("\n==============================")
        print("  SENSOR SCAN CYCLE")
        print("==============================")

        scan_i2c()
        scan_onewire()

        print("Scan complete. Sleeping 5s...\n")
        time.sleep(5)


main()
