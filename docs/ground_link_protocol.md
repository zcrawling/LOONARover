# GroundLink protocol v1

GroundLink is the only Raspberry Pi LAN endpoint for the ground station control
and telemetry plane.  It is a single persistent TCP server on port `7443`.
Video UDP and ROS 2 DDS are deliberately separate.

## Frame

```text
magic:u32 | version:u16 | type:u16 | sequence:u32 | payload_length:u32 | payload
```

The four magic bytes are ASCII `LNK1` (`4c 4e 4b 31`), `version` is `1`, and
the maximum payload is 512 bytes. All integer fields and IEEE-754 binary64
floating-point fields are little-endian. `sequence` lets the ground station
match a discrete request to its result; periodic telemetry uses sequence zero.
TCP reconnect does not change vehicle mode. TCP supplies ordered/reliable byte
delivery, so v1 does not add a separate frame CRC.

## Commands

| Type | ID | Payload | cFS route |
| --- | --- | --- | --- |
| `STOP_CMD` | `0x0001` | empty | VehicleAdapter -> gateway STOP |
| `MANUAL_CMD` | `0x0002` | linear_mps:f64, angular_radps:f64 | VehicleAdapter -> gateway manual motion |
| `AUTO_CMD` | `0x0003` | empty | VehicleAdapter -> gateway AUTO select |
| `PAYLOAD_CMD` | `0x0004` | request_id:u64, opcode:u16, parameter_length:u16, parameters | Payload route after explicit STOP |
| `REACTION_CMD` | `0x0005` | request_id:u64, opcode:u16, parameter_length:u16, parameters | Reaction route after explicit STOP |

`parameter_length` is 0 through 64 bytes in the current cFS applications.
`PAYLOAD_CMD` and `REACTION_CMD` are discrete requests. They receive a command
result and later progress/result telemetry. The `REACTION_CMD` envelope and
route are defined, but its opcode meanings and actuator/recovery behaviour are
TBD; the current adapter returns `NOT_IMPLEMENTED`.

## Telemetry

| Type | ID | Required content |
| --- | --- | --- |
| `COMMAND_RESULT` | `0x8001` | request sequence, command, cFS receipt, forwarding result, current mode |
| `GATEWAY_STATUS` | `0x8002` | STOP/MANUAL/AUTO/PAYLOAD/REACTION, last gateway command |
| `VEHICLE_STATUS` | `0x8003` | battery, odometry/IMU if available, timestamp |
| `LOONAR_MCU_STATUS` | `0x8004` | uptime, board temperature, state, inhibit flags, applied motion, RX errors |
| `DEVICE_STATUS` | `0x8005` | IMU, motor, payload sensor, LiDAR, camera, MCU link, Wi-Fi; each with timestamp |
| `EVENT` | `0x8006` | bounded source, severity, code, text |

The displayed age of each status is derived from its producer timestamp. It is
diagnostic information; GroundLink and Gateway do not turn it into an implicit
command rejection rule.

### Fixed payload layouts

All fields below are little-endian and packed on the wire; C/C++ structure
padding is never transmitted.

| Type | Wire payload |
| --- | --- |
| `COMMAND_RESULT` | ground_sequence:u32, command_type:u16, cfs_received:u8, adapter_forwarded:u8, current_mode:u8, result_code:u8 |
| `GATEWAY_STATUS` | mode:u8, last_source:u8, has_last:u8, reason:u8, last_linear:f64, last_angular:f64 |
| `VEHICLE_STATUS` | timestamp_ms:u64, valid_flags:u32, battery_voltage:f64, battery_percent:f64, odom_x/y/yaw:f64, linear/angular:f64, imu_roll/pitch/yaw:f64 |
| `LOONAR_MCU_STATUS` | timestamp_ms:u64, uptime_ms:u64, temperature_c:f64, state:u16, inhibit_flags:u32, applied_linear/angular:f64, rx_errors:u32 |
| `DEVICE_STATUS` | timestamp_ms:u64, count:u8, repeated state:u8 + last_update_ms:u64 in IMU/MOTOR/PAYLOAD_SENSOR/LIDAR/CAMERA/MCU_LINK/WIFI order |
| `EVENT` | timestamp_ms:u64, severity:u8, code:u32, source_length:u8, text_length:u16, source bytes, text bytes |

`valid_flags` prevents a backend from fabricating unavailable numeric values.
Device state is `0=UNKNOWN`, `1=CONNECTED`, `2=DISCONNECTED`, `3=ERROR`.

### Enum values

- mode: `1=AUTO`, `2=MANUAL`, `3=STOP`, `4=PAYLOAD`, `5=REACTION`
- last source: `0=NONE`, `1=ROS_AUTO`, `2=GROUND_MANUAL`, `3=GROUND_STOP`
- result: `0=OK`, `1=BAD_PAYLOAD`, `2=GATEWAY_DISCONNECTED`,
  `3=NOT_IMPLEMENTED`, `4=INTERNAL_ERROR`
- `VehicleStatus.valid_flags`: bit 0 battery voltage, bit 1 battery percent,
  bit 2 odometry pose, bit 3 odometry motion, bit 4 IMU orientation
- device order: `0=IMU`, `1=MOTOR`, `2=PAYLOAD_SENSOR`, `3=LIDAR`,
  `4=CAMERA`, `5=MCU_LINK`, `6=WIFI`

`COMMAND_RESULT.adapter_forwarded` means the adapter completed its immediate
forward/routing step. It is not a claim that a motor, payload or reaction-wheel
operation physically completed. Hardware completion is reported by later
status/event telemetry.
