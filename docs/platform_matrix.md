# Platform Matrix

| Item | LIMO validation platform | Final LOONAR platform |
| --- | --- | --- |
| Purpose | develop and validate common mission, autonomy and Gateway behavior | validate final electronics, MCU and vehicle dynamics |
| Compute / OS | NUC11, Ubuntu 22.04, ROS 2 Humble | Raspberry Pi and final target OS/ROS selection |
| Vehicle backend | `LimoBackend` | `TeensyRs485Backend` |
| Motion endpoint | LIMO driver or `/cmd_vel` | MAX3490E, RS-485, Teensy Control MCU |
| Must be revalidated | LIMO-specific dynamics and driver behavior | RS-485, command lease, PWM/PID, encoders, braking and final sensors |

Only the backend and platform configuration may contain LIMO- or LOONAR-specific code.
