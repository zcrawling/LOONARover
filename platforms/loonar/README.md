# Final LOONAR Rover Platform

The [dual-Teensy MCU requirements and v2 architecture](porting/mcu_architecture_v2.md)
defines the 2026-09-19 design for role identification, unattended firmware recovery,
BNO085/RoboClaw control, buffered telemetry and cFS health reporting. It is a design,
not a claim that those firmware features have been implemented.

This is the final-rover platform, not a legacy archive. It retains the PCB,
Control MCU firmware, RS-485 wire implementation, hardware baselines and HIL
references needed for migration from LIMO.

See the [LIMO → LOONAR porting and acceptance plan](porting/limo_to_loonar_plan.md)
for Raspberry Pi 5 / Ubuntu 24.04 / ROS 2 Jazzy, systemd/cFS deployment,
minimal EKF with motion restrictions, CubeEye, camera streaming, and operator tests.
The [Pi preparation guide](deploy/README.md) contains native build/deployment commands
and the current camera → Teensy USB → lidar/ToF → driving verification sequence.

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

MCU 구현: [펌웨어](firmware/control/README.md), [Pi/ROS/cFS 설정과 검증](porting/mcu_v2_implementation.md), [wire v2](porting/mcu_wire_v2.md).
