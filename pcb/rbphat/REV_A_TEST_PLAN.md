# RBPHAT Rev.A power-off test plan

## Power and grounding

- Power Raspberry Pi 5 from its USB-C 5 V adapter.
- Power the Teensy from a separate PSU.
- Join grounds only through the RS-422 connector GND / HAT GND path.
- Never join the two positive supply rails.
- Leave BAT+/BAT- disconnected unless the battery-sense tests are being run.

## Normal reboot test

1. Keep Pi 3V3 present and the Teensy continuously transmitting.
2. Reboot the Pi repeatedly.
3. Confirm GPIO4 and GPIO12 remain near UART idle HIGH while configured as
   input/Hi-Z because of the 47k pull-ups.
4. Confirm no electrical overstress or abnormal rail current.
5. Verify the firmware discards a partial frame received after reboot and locks
   to the next valid framing boundary.

This is normal powered operation, not the hardware fault condition.

## Required MAX3490E power-off fault test

Test each channel separately.

1. Teensy ON; continuously transmit worst-case alternating data over RS-422.
2. Pi 3V3 OFF.
3. Remove the selected MAX3490E VCC 0R link.
4. Insert a current meter between the Pi-3V3 side and the MAX-VCC side of the
   0R footprint, or measure the isolated rail through its VCC test point.
5. Record MAX-VCC voltage, current into the Pi 3V3 rail, GPIO-side voltages,
   temperature, cable length, data rate, and pattern.
6. Repeat for both polarities/idle states and for both channels.
7. With the current meter removed, confirm the SN74LVC2G34 Ioff barrier prevents
   GPIO back-drive.

Release criterion: measured backfeed must be reviewed against the Pi off-state
rail budget before Rev.B. MAX3490E A/B-to-VCC behavior remains an empirical Rev.A
qualification item; it is not waived by ERC.

## Receiver idle / optional bias test

1. Fit the 120R A/B termination (default population).
2. Leave the remote transmitter OFF and the 680R bias footprints DNP.
3. Scope A, B, and A-B at the MAX3490E pins and at the connector.
4. Populate A-to-3V3 and B-to-GND 680R parts only if the measured idle state is
   not adequate for the protocol/noise environment.

## Battery isolation test

1. Pi 3V3 OFF; apply 0–12.6 V at BAT+/BAT-.
2. Confirm TMUX1511 VDD=0 and ADS1115 AIN0/Pi 3V3 are not materially back-powered.
3. Pi ON; sweep BAT+ and confirm `VBAT = VADC × 6.222222`.
4. At 12.6 V expect approximately 2.025 V at BAT_DIV before tolerance/leakage.

