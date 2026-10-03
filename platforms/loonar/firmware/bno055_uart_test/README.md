# Teensy 4.1 / BNO055 UART test

Standalone PlatformIO project; does not link rover motor/control firmware.

## Wiring

|Teensy 4.1|BNO055|
|---|---|
|24 (TX6)|RX / COM1 / SCL|
|25 (RX6)|TX / COM0 / SDA|
|GND|GND|
|3.3V logic|PS1 HIGH, PS0 LOW|

Set PS1=HIGH and PS0=LOW before powering the sensor; power-cycle after changing them.
UART is fixed 115200 8N1. Teensy pins are 3.3V and not 5V tolerant.
Power the breakout according to its own VIN/3Vo specification; a raw BNO055 needs
both VDD and VDDIO and the datasheet support circuit. Keep reset deasserted and
BOOT_LOAD in normal operating state. Module labels may differ: use TX/RX markings
when available, not an assumed I2C wiring scheme.

## Run from LOONAR root

```bash
pio run -d platforms/loonar/firmware/bno055_uart_test
pio run -d platforms/loonar/firmware/bno055_uart_test -t upload
pio device monitor -b 115200
# If several USB serial devices are present:
pio device monitor --port /dev/ttyACM0 -b 115200
```

Upload replaces the connected Teensy's existing firmware. This test has no motor commands.
No upload is performed just by building.

Default mode NDOF (0x0C), default sensor axes, internal/default clock unchanged.
For magnetometer-free relative yaw, add `-DBNO_MODE=0x08` to build_flags (IMUPLUS).
No calibration offsets are saved to nonvolatile storage by this program.

USB CSV at approximately 50Hz:
- ax/ay/az: acceleration including gravity, m/s²
- gx/gy/gz: angular velocity, degrees/s
- heading/roll/pitch: BNO Euler convention, degrees (not ROS ENU conversion)
- quaternion qw/qx/qy/qz
- lin_a: sensor fusion linear acceleration, m/s² (do not subtract gravity again)
- grav: sensor fusion gravity vector, m/s²
- temperature °C, calibration system/gyro/accel/magnetometer levels 0..3
- SYS_STATUS, SYS_ERR, cumulative UART transaction errors

`t_ms` is MCU host receipt time, not a sensor sample timestamp. Register burst
reads are not claimed to be a synchronized robotics/odometry interface.
CHIP_ID must be 0xA0. Fusion SYS_STATUS is normally 5, SYS_ERR 0.
First hold still for gyro calibration; then gently vary orientations for accel and
magnetometer calibration. NDOF heading can change while calibration develops.
IMUPLUS does not provide absolute magnetic heading. Calibration status 3 does not
prove application-level acceleration/position accuracy.

Timeout and protocol errors retry up to 3 times; persistent failures reinitialize
without blocking indefinitely. No stale packet is printed as a new sample.
UART error FF means host timeout, FE malformed response; other values are BNO
UART response codes. Check mode straps and TX/RX wiring first on repeated FF.

Sources:
- https://www.pjrc.com/teensy/td_uart.html
- https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bno055-ds000.pdf
- https://www.bosch-sensortec.com/media/boschsensortec/downloads/application_notes_1/bst-bno055-an012.pdf

Diagnostic v2 reads register 0x00 before configuration and prints TX/RX bytes on
failed transactions. `FE` means unexpected protocol response, NOT a measured
hardware framing error. `RX25_level` is a single pin-level snapshot, not a UART
waveform measurement. `RX[0]=<none>` means no bytes were received within 150ms;
a one-byte reply followed by timeout is separately visible. The first page0
ID read should receive `BB 01 A0`. Protocol straps must be checked as actual
voltage levels; a solder bridge may pull HIGH or LOW depending on the module.
