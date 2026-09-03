# LOONAR Rover Software

LOONAR is developed against two first-class vehicle platforms:

- `platforms/limo/`: the current NUC11, Ubuntu 22.04, ROS 2 Humble integration platform.
- `platforms/loonar/`: the final rover hardware platform: Raspberry Pi, Teensy, RS-485, sensors, camera, and PCB assets.

The architecture source of truth is [project.md](project.md). cFS owns mission and
ground control, ROS 2 owns autonomy, and `vehicle_gatewayd` is the single final
arbiter and owner of the active vehicle backend. The backend is `LimoBackend`
during platform validation and `TeensyRs485Backend` on the final rover.

The retained LOONAR hardware implementation is intentionally buildable as a
hardware reference. It is not an active vehicle control path until its protocol
is revised to satisfy the Gateway and MCU command-lease contracts.

See [docs/README.md](docs/README.md) for the new document hierarchy.
