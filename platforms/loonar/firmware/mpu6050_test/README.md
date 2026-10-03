# MPU6050 standalone I2C test — Teensy 4.1

Motor firmware is not used. Uploading this program replaces the current application;
keep motor power off during the sensor test. No motor pins or motor commands are used.

| MPU6050 module | Teensy 4.1 |
|---|---|
| VCC | 3.3V |
| GND | GND |
| SCL | 19 (Wire / SCL0) |
| SDA | 18 (Wire / SDA0) |
| AD0 | GND for 0x68; 3.3V for 0x69 |
| INT | Not required; data-ready status is polled |

Use the module's pull-ups to 3.3V (add external pull-ups if absent); no 5V signals.
Both addresses are probed and WHO_AM_I must be 0x68 even at bus address 0x69.

Power wait 5000ms, I2C100kHz, bus wait250ms, five initialization attempts,
150ms between failed attempts. Sensor reset waits100ms; wake waits100ms.
Configuration is read back: +/-2g, +/-250deg/s, 50Hz samples, DLPF setting3.
14-byte burst samples contain acceleration, temperature and angular rate.
Prints values at5Hz and health counters every second; r repeats initialization.
initialized=1 only means register initialization passed; samples must increase
and age_ms stay low to confirm live measurements. Read errors never produce values.

```bash
cd /home/sb/LOONAR
~/.local/bin/pio run -d platforms/loonar/firmware/mpu6050_test -e teensy41
~/.local/bin/pio run -d platforms/loonar/firmware/mpu6050_test -e teensy41 -t upload
~/.local/bin/pio device monitor -p /dev/ttyACM0 -b 115200
```

Expected at rest: acceleration vector magnitude about1g, gyro near0deg/s.
Individual axes/signs depend on module orientation; no bias calibration applied.
No heading/quaternion or integration into production firmware is included.

If Teensy remains connected to Pi, stop start-ground-support.sh with Ctrl+C first,
then copy the local `.pio/build/teensy41/firmware.hex` and use the verified Control
board tag with Pi's `~/.local/bin/tycmd upload`. USB text output requires stopping
the binary MCU backend while this standalone firmware is running.

Register reference:
https://invensense.tdk.com/wp-content/uploads/2015/02/MPU-6000-Register-Map1.pdf

## PULLUP-v2

After Wire.begin(), apply INPUT_PULLUP to18/19 and print GPIO PULLUP CHECK.
Restore the saved Wire mux and open-drain pad configuration while retaining
internal pull-ups. Leaving pinMode's GPIO mux in place would disconnect hardware I2C.
The previous digitalRead diagnostics in peripheral mode are removed: they are not
a reliable physical bus-level measurement. The startup GPIO check is sampled only
while the pads are GPIO inputs. Internal pull-ups are a diagnostic aid; successful
ACK/ID/sample reception must still be checked on hardware.

## WAKE-v3

Retains PULLUP-v2. Polls reset bit clear (up to1s), tries wake on internal clock
(PWR_MGMT_1=0) up to5 times with100ms settling and150ms retry, then selects PLL
(PWR_MGMT_1=1) and verifies again. Logs write ACK separately from readback.
A successful ACK alone does not establish that the configuration was retained.
This is a diagnostic/recovery attempt, not a confirmed fix for persistent0x40.

## WRITE-DIAG-v4

After five failed initialization attempts, checks writable SMPLRT_DIV(0x19)
with7/19, restores its original value, then checks a wake write immediately
and after100ms. No additional reset in this diagnostic. Successful ACK is not
proof of a retained register value; reset bit clear alone does not prove reset
execution. PLL now explicitly reports skipped when wake fails.

## GYRO-CAL-v5: stationary gyro bias (step 1)

After successful initialization, hold the rover fully stationary: 3s settling then
at least250 fresh samples spanning5s at50Hz. Apply mean gyro X/Y/Z as bias only
if the entire window passes. Output Graw and Gcorr in deg/s; Gcorr=Graw-bias.
The correction is not a deadband: real slow movement remains visible.

Reject calibration on I2C error, collection gap>100ms, overall timeout>12s,
accel norm outside0.85..1.15g, any gyro axis>10deg/s, or window sample standard
deviation>0.03g per acceleration axis / >0.5deg/s per gyro axis. These are bench
thresholds, not guarantees of physical stillness. Constant slow yaw can look like
bias: the operator must keep the rover motionless. Board orientation need not be
level. Three seconds is a settling period, not proof of thermal equilibrium.

Commands: c=discard old bias and recalibrate; r=reinitialize and recalibrate.
Bias is RAM-only and recalculated after every reboot. CAL=FAILED means no corrected
values are output until a successful retry. STATUS reports progress if opening
serial after the initial CAL START. Temperature changes can require recalibration.
This standalone firmware does not drive motors or close a feedback loop.

Build/upload/monitor commands above remain the same; banner must show GYRO-CAL-v5.
Host validation: g++ -std=c++17 -Wall -Wextra -Werror tests/test_gyro_bias.cpp -o /tmp/test-gyro-bias && /tmp/test-gyro-bias
