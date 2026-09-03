# LOONAR ground-control porting items

## Required before final-rover activation

- Implement the LOONAR serial vehicle backend for the common linear/angular
  motion input. It is intentionally not part of LIMO development.
- Map Control MCU status into `LOONAR_MCU_STATUS`: uptime, board temperature,
  state, inhibit flags, applied linear/angular command and RX error count.
- Map available battery, motor, IMU and payload-sensor status into the common
  telemetry contract without fabricating unavailable fields.
- Implement a separate PayloadAdapter/transport according to
  `platforms/loonar/interfaces/payload_mcu_reference.md`.

## Reaction wheel — TBD

`REACTION_CMD` is reserved in GroundLink, cFS and vehicle-mode telemetry.
The final reaction-wheel MCU protocol, allowable recovery sequence, feedback,
completion criteria and post-recovery logic are **TBD**.  Until that interface
is approved, ReactionAdapter must report `NOT_IMPLEMENTED` and must not attempt
to drive any actuator.
