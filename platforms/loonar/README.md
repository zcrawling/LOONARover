# Final LOONAR Rover Platform

This is the final-rover platform, not a legacy archive. It retains the PCB,
Control MCU firmware, RS-485 wire implementation, hardware baselines and HIL
references needed for migration from LIMO.

The retained Control MCU wire protocol is **v1 hardware reference**. Before a
vehicle is driven through this platform, `TeensyRs485Backend` and the MCU protocol
must implement the Gateway contract and independent MCU command lease required by
`project.md`.

| Path | Content |
| --- | --- |
| `hardware/` | PCB, physical configuration, Pi camera reference |
| `firmware/control/` | Teensy 4.1 FreeRTOS Control MCU reference |
| `interfaces/` | Control/Payload MCU protocol references |
| `libs/wire_c/` | framing, CRC and codec implementation |
| `tests/` | codec/firmware and HIL reference tests |
