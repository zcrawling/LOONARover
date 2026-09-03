# LIMO Validation Platform

This platform is the current development and end-to-end validation target:
NUC12WSKi7, Ubuntu 22.04.3, and ROS 2 Humble. (The initial NUC11 inventory
was corrected by direct inspection.)

It will provide `LimoBackend` to `vehicle_gatewayd`. LIMO-specific driver,
topic and calibration details must stay in this folder. Common autonomy and
mission code must not depend on them.

## Verified integration facts

- Workspace: `/home/wego/agilex_ws`; vendor package: `limo_base`.
- LIMO driver subscribes to `/cmd_vel` (`geometry_msgs/msg/Twist`) and publishes
  `/odom`, `/imu`, and `/limo_status`; its launch remaps odometry to
  `/wheel/odom`.
- The base driver uses a CP2102 serial device at 460800 baud. The observed
  default is `/dev/ttyUSB1`, but two CP2102 devices share the same USB serial
  identifier. A by-path udev alias must be installed and verified before any
  service uses a persistent device name.
- Orbbec depth and UVC camera devices are present. No ROS nodes were active
  during the inventory, so live status rates and LIMO motion mode remain a
  start-up acceptance check.

`vehicle_gatewayd` must be the only project publisher to `/cmd_vel`. The vendor
`limo_base` process remains the serial owner inside `LimoBackend`.

## Implemented validation stack

- `ros2/loonar_limo_backend` is the sole project-side `/cmd_vel` publisher.
  It receives only Gateway packets through the backend Unix socket, maps
  `linear_mps` and `angular_radps` to `Twist.linear.x` and `Twist.angular.z`,
  and publishes zero on startup, Gateway disconnect, status timeout, command
  expiry, and process shutdown.
- It treats fresh `/limo_status` as the backend-health evidence. Until this is
  present, the Gateway does not accept motion; `/wheel/odom` and `/imu` are
  subscribed now to lock their platform contract, while their telemetry fanout
  is deliberately deferred to the cFS adapter.
- `systemd/` contains user-service templates. They use `%t` (the per-user
  runtime directory), not a machine-wide `/run` path, so sockets are private
  to the `wego` session.

Build on the validation NUC without modifying the vendor workspace:

```bash
source /opt/ros/humble/setup.bash
source /home/wego/agilex_ws/install/setup.bash
cd /home/wego/loonar_ws
colcon build --packages-select loonar_limo_backend --symlink-install
```

The checked deployment starts with Gateway authority `NONE`; service startup
cannot issue a non-zero command. Do not begin the G4 motion acceptance tests
until the udev alias and operator safety boundary are verified.

## Live acceptance harness

`scripts/live_gateway_test.sh` is the operator-facing G4 harness. It is
non-moving by default and requires a fresh `/limo_status` before it declares a
safe smoke pass. A non-zero test is opt-in with `--move`; its supplied command
values are handed to the Gateway unchanged.

`control_mode` is printed for diagnosis only. Its numerical mapping is
firmware-specific and must not be used as a Gateway command gate. SWD selects
the vehicle motion mode; it is not a Gateway authority input.

```bash
cd /home/wego/loonar_ws/src/loonar
bash platforms/limo/scripts/live_gateway_test.sh --start-base
# After the no-motion smoke pass and safety confirmation:
bash platforms/limo/scripts/live_gateway_test.sh --start-base --move --linear 0.05 --duration 1000
```
