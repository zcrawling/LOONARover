# Ground-control implementation plan

This plan covers Raspberry Pi-side work only. Ground-station UI, TCP client and
video receiver are external deliverables.

## Completed G1: gateway mode contract

- `vehicle_gatewayd` exposes `STOP`, `MANUAL`, `AUTO`, `PAYLOAD` and
  `REACTION` modes.
- `STOP`, `MANUAL`, and `AUTO` have active vehicle-motion semantics.
- `PAYLOAD` and `REACTION` only record/report the cFS-selected operating state;
  their separate MCU adapters are not implemented yet.
- Core, protocol and daemon tests cover the mode behaviour.

## Completed G2: common GroundLink codec

Create a standalone bounded codec before taking a cFS dependency.

1. `common/ground_link/include/.../frame.hpp`: fixed header, frame type and
   bounded payload declarations.
2. `common/ground_link/src/frame.cpp`: field-wise codec and payload-length
   validation.
3. Unit tests: valid round trips, bad magic/version/length, oversized frame and
   every command type.
4. `ground_link_mock`: TCP client that sends each command and prints telemetry.

## Completed G3: minimal cFS applications

The applications are under `cfs/apps/` and have been compiled as loadable
modules against an unmodified official NASA cFS native-standard build. Mission
registration and startup fragments are under `cfs/mission/`.

### GroundLink app

- Own TCP `:7443` server and GroundLink codec.
- Publish the five incoming command packets to CFE_SB.
- Subscribe to VehicleAdapter, payload, reaction and device telemetry packets.
- Serialize command result, gateway, vehicle, MCU, device and event telemetry
  back to the connected ground station.
- On reconnect: keep current vehicle mode unchanged.

### VehicleAdapter app

- Own the one `cfs.sock` peer connection.
- Convert STOP/MANUAL/AUTO to gateway packets.
- For PAYLOAD/REACTION: perform explicit STOP, select the mode, and publish the
  dedicated execution MID. REACTION reports `NOT_IMPLEMENTED` until its TBD
  hardware protocol is supplied.
- Publish `COMMAND_RESULT` and `GATEWAY_STATUS` through CFE_SB.
- Republish the current connected Gateway status once per second so a newly
  connected ground station can observe mode without first issuing a command.

## Partially completed G4: telemetry producers

1. Gateway `VehicleStatus` packet and cFS forwarding are implemented.
2. LIMO backend maps `/limo_status`, `/wheel/odom`, `/imu` at 1 Hz without using
   them as a motion gate. Battery percent stays invalid because LIMO reports
   voltage, not a trustworthy percentage.
3. Final LOONAR serial backend and MCU/device status mapping are porting work.
4. Payload and reaction adapters publish progress/result telemetry separately.

## Completed G5: shared direct-camera video sender

- The common software H.264/MPEG-TS/UDP pipeline and systemd unit are under
  `common/video/`; ROS is not in the video data path.
- Pi 5 libcamera configuration is under `platforms/rpi/video/`.
- LIMO V4L2 configuration and inspected Orbbec-integrated UVC identity are under
  `platforms/limo/video/`.
- Identify the camera with `rpicam-hello --list-cameras`.
- Measure all three profiles before selecting a default; Pi 5 uses software
  H.264 encoding, so CPU/thermal measurements are required.

## Verification evidence (2026-09-03)

- Local Debug CTest: 15/15 passed.
- Local ASAN/UBSAN CTest: 15/15 passed.
- `loonar_ground_link` and `loonar_vehicle_adapter` compile as loadable modules
  in an unmodified NASA cFS 7.0.1 native-standard build.
- Native end-to-end command test passed for STOP, MANUAL, AUTO, PAYLOAD and
  REACTION from `ground_link_mock` through TCP, cFS Software Bus and Gateway.
- Native status test relayed a valid 11.7 V `VehicleStatus` through backend,
  Gateway, cFS and GroundLink to the ground mock.
- LIMO live video test passed for 1/3/5 Mbit/s profiles at 30 fps; the receiver
  parsed H.264 and decoded a 1280x720 frame from the installed medium service.
- The deployed LIMO build passed Gateway 3/3, GroundLink 2/2 and video 1/1
  target-side tests. The ROS 2 Humble backend also compiled against the actual
  installed `limo_msgs` package.
- A live LIMO run passed all five commands over GroundLink TCP, cFS Software
  Bus, VehicleAdapter and Gateway. MANUAL used exactly `(0, 0)`; the final STOP
  produced an observed `/cmd_vel` Twist of all zeroes. No non-zero motion was
  requested in this deployment test.
- The same live run forwarded `VehicleStatus` once per second with valid flags
  `0x1d`, 11.6 V battery voltage and LIMO odometry. The installed video service
  was restored afterward and its 1280x720 H.264/UDP output decoded successfully
  on the configured receiver at `192.168.0.86:5600`.
- Pi camera capture and CPU/thermal measurements require the target Pi 5 and
  identified camera module.
