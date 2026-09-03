# vehicle_gatewayd Architecture

## 1. Purpose

`vehicle_gatewayd` is the single project-facing vehicle-control service. It
accepts AUTO motion from ROS 2 and MANUAL motion from cFS, decides who has
authority, then invokes exactly one active `VehicleBackend`.

```text
cFS MANUAL / authority ----> cfs.sock --+
                                       |
ROS autonomy motion -----> ros.sock ---+--> Gateway core --> LimoBackend --> /cmd_vel --> limo_base
                                       |                                      |
                                       +--> normalized status <---------------+-- /limo_status, /wheel/odom, /imu
```

The final-rover path replaces only the final box:

```text
Gateway core --> TeensyRs485Backend --> MAX3490E / RS-485 --> Control MCU
```

## 2. Ownership

| Resource | Owner |
| --- | --- |
| authority, epoch, sequence and command TTL | `vehicle_gatewayd` core |
| AUTO command producer | `rover_vehicle_client` in ROS 2 |
| MANUAL command producer | cFS Ground/Mission adapter |
| LIMO `/cmd_vel` project publisher | `LimoBackend` only |
| LIMO vendor serial | vendor `limo_base` process, encapsulated by `LimoBackend` |
| final rover RS-485 | `TeensyRs485Backend` only |
| motor PWM, PID and independent safety | final Control MCU |

Nav2, teleop tools, cFS, and test programs must never publish directly to the
LIMO driver's `/cmd_vel` while Gateway is enabled.

## 3. Authority state machine

`NONE`, `AUTO`, and `MANUAL` are Gateway states. Every accepted authority
transition performs, in order:

1. reject new motion during the transition;
2. publish a backend zero command;
3. increment `control_epoch`;
4. clear all source command caches and sequence windows;
5. set the new authority and emit status.

Only `AUTONOMY` is accepted in `AUTO`; only `MANUAL` is accepted in `MANUAL`.
`NONE` continuously requests zero motion.

## 4. LIMO backend policy

The inspected driver consumes `geometry_msgs/msg/Twist` on `/cmd_vel` and
publishes `/wheel/odom`, `/imu`, and `limo_msgs/msg/LimoStatus`. `LimoBackend`
embeds an isolated ROS 2 context, is the only project `/cmd_vel` publisher, and
maps backend status into Gateway telemetry.

This permits MANUAL operation when Nav2 or perception has failed, but not when
the LIMO driver or DDS transport itself has failed; that failure must result in
`NONE` and zero output.

The vendor driver's own command watchdog is not yet verified. Therefore the
first LIMO acceptance gate is: TTL expiry and an ungraceful Gateway stop both
leave the vehicle stationary within the agreed limit. The final MCU path will
add an independent command lease.

## 5. Runtime

- `vehicle_gatewayd.service`: native daemon, owns Unix-domain IPC and the active
  backend.
- `limo_base`: vendor process launched separately during development; service
  readiness is observed through its ROS graph/status topic.
- cFS and ROS may restart independently. Their disconnect clears only their
  own command cache; Gateway retains safe `NONE` or zero output.

The persistent LIMO serial alias is a platform prerequisite, not a Gateway
implementation detail. It must use the verified USB path rather than the
duplicated CP2102 serial identifier.
