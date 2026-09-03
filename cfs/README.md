# LOONAR minimal cFS integration

This directory contains the two cFS applications needed for the first ground
control integration. It does not vendor or fork NASA cFS.

- `loonar_ground_link`: TCP `0.0.0.0:7443` endpoint, GroundLink frame parsing,
  five command publications, and six telemetry subscriptions.
- `loonar_vehicle_adapter`: cFS Software Bus to `vehicle_gatewayd` adapter.
  MANUAL is forwarded directly; PAYLOAD and REACTION issue STOP before selecting
  their mode and publishing their dedicated execution MID.

The TCP connection carries no video and no ROS 2 data. Reconnecting the TCP
client does not change the selected vehicle mode.

## Add to a cFS mission

Make these application directories visible in the mission's `apps/` directory:

```text
apps/loonar_ground_link     -> <LOONAR>/cfs/apps/ground_link
apps/loonar_vehicle_adapter -> <LOONAR>/cfs/apps/vehicle_adapter
apps/common                 -> <LOONAR>/cfs/apps/common
```

Apply [targets.cmake.fragment](mission/targets.cmake.fragment) to the mission
targets file and apply
[cfe_es_startup.scr.fragment](mission/cfe_es_startup.scr.fragment) to the CPU
startup generator/script. Then run the normal cFS `make prep`, build, and
install flow.

The CMake target names are descriptive, but their installed modules are the
short `lnr_ground.so` and `lnr_vehicle.so`; the short names satisfy cFS/OSAL
module filename limits.

The default Software Bus message IDs are in
[`loonar_cfs_messages.h`](apps/common/loonar_cfs_messages.h). A mission with an
existing MID allocation must change those values before integration.

## Runtime order

1. Start `vehicle_gatewayd`; it creates
   `/run/loonar/vehicle-gateway/cfs.sock`.
2. Start cFS with both LOONAR apps in the startup script.
3. Connect the ground mock with
   `ground_link_mock <PI_IP> 7443 monitor`, or send one of `stop`, `manual`,
   `auto`, `payload`, `reaction`.

Without ROS hardware, the common status relay can be exercised with
`vehicle_gatewayctl vehicle-status <backend.sock> 11.7` while GroundLink mock
is monitoring. This injects only a test battery-voltage field.

The adapter retries its local gateway connection. A missing gateway produces
`GATEWAY_DISCONNECTED`; it does not invent a mode change or silently turn the
command into a different command.

For a user service or test runtime, set `LOONAR_GATEWAY_SOCKET` to the exact
`cfs.sock` path before starting cFS. The default remains the system path above.

## Current boundary

The PAYLOAD execution MID is implemented, but its final MCU transport is a
LOONAR hardware-porting item. REACTION has the same complete route but returns
`NOT_IMPLEMENTED`; its actuator protocol and recovery/post-recovery logic are
explicitly TBD.
