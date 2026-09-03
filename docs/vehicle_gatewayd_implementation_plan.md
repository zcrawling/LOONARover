# vehicle_gatewayd Implementation Plan

This document started as the Phase-2 review artifact. The G1-G3 minimum slice
below is now implemented and build-verified locally and on the LIMO NUC; G4
remains the separately controlled physical-motion acceptance gate.

## Slice G0 — Platform preflight

Minimal deliverables:

1. `platforms/limo/config/udev/99-loonar-limo.rules` using the verified
   CP2102 USB **path**; create `/dev/ttylimo`.
2. `platforms/limo/scripts/preflight.sh`, read-only checks for `/dev/ttylimo`,
   `limo_base`, `/cmd_vel`, `/limo_status`, `/wheel/odom`, and `/imu`.
3. A recorded table for LIMO motion mode, command/status rate, battery/error
   semantics, and vendor command-timeout behavior.

Acceptance: restart/replug does not change the LIMO device identity; no other
project publisher exists on `/cmd_vel`.

## Slice G1 — Pure Gateway core

Implemented as `common/vehicle_gateway/` with no ROS, socket, serial, or
systemd dependency in its core:

| File | Minimal responsibility |
| --- | --- |
| `types.hpp` | authority, source, command, telemetry and reason types |
| `limits.hpp` | validated command TTL limits |
| `authority.cpp` | transition -> zero barrier -> epoch increment |
| `sequence_window.cpp` | duplicate/out-of-order protection per peer/source |
| `command_cache.cpp` | latest accepted command and receive-time expiry |
| `gateway_core.cpp` | one deterministic `tick(now)` decision |

Unit tests first: initial `NONE`, AUTO/MANUAL rejection, transition zero,
old-epoch rejection, TTL expiry, duplicate sequence, reconnect cache clearing,
and non-finite/range rejection.

## Slice G2 — Local IPC daemon

Implemented in `common/vehicle_gateway/src/main.cpp`:

| File | Minimal responsibility |
| --- | --- |
| `main.cpp` | process lifecycle, signal handling and safe shutdown |
| `ipc_server.cpp` | two `SOCK_SEQPACKET` listeners and peer credentials |
| `protocol.cpp` | field-wise codec; fixed maximum frame sizes |
| `cfs_peer.cpp` | authority/MANUAL request mapping |
| `ros_peer.cpp` | AUTO command/status mapping |
| `status_publisher.cpp` | latest status fan-out and transition events |

Use a single event loop plus monotonic timer. Periodic commands/status use
latest-value slots; discrete authority requests use a bounded FIFO and
`request_id` deduplication.

Acceptance: a PTY/fake backend proves no direct peer can bypass core validation.

## Slice G3 — LimoBackend

Implemented as ROS 2 package `platforms/limo/ros2/loonar_limo_backend`:

| File | Minimal responsibility |
| --- | --- |
| `limo_backend.cpp` | isolated rclcpp context, sole `/cmd_vel` publisher |
| `limo_telemetry.cpp` | subscribe/map LIMO status, wheel odom and IMU |
| `limo_config.yaml` | topic names, limits, rates and status timeout |
| `limo_backend_test.cpp` | fake ROS graph/backend contract test |

Start conservatively: publish zero at backend startup, after every transition,
and for a bounded stop burst after TTL expiry. Do not let Nav2, teleop or a test
node publish to `/cmd_vel` in the integrated configuration.

## Slice G4 — Service and fault gates

Add `vehicle_gatewayd.service`, runtime-directory ownership, resource limits,
and an explicit dependency/readiness policy for the vendor `limo_base` process.

LIMO acceptance tests, in this exact order:

1. Gateway startup emits zero; no movement.
2. MANUAL 0.05 m/s command moves only in `MANUAL`.
3. MANUAL packet interruption expires TTL and stops.
4. AUTO -> MANUAL transition stops before manual motion is accepted.
5. Kill Nav2: MANUAL still works; AUTO stops.
6. Kill Gateway: verify the vendor/base watchdog stops the vehicle. If it does
   not, add a supervised LIMO watchdog solution before proceeding.
7. Vendor driver/ROS graph loss: Gateway reports unhealthy and remains `NONE`.

## Slice G5 — Final rover backend preparation

Only after G1-G4 are accepted, implement `TeensyRs485Backend`. Preserve the
Gateway core unchanged, introduce MCU wire v2 with independent command lease,
then repeat the same authority/TTL/fault tests plus RS-485, motor, encoder and
braking HIL gates.

## Build evidence (2026-09-02)

- Local Debug CTest: 12/12 passed.
- Local ASAN/UBSAN CTest: 12/12 passed.
- LIMO NUC12 (Ubuntu 22.04, GCC 11) standalone Gateway: 3/3 passed.
- LIMO NUC12 ROS 2 Humble: `loonar_limo_backend` compiled against the existing
  read-only AgileX `limo_msgs` overlay and its executable was registered.
- NUC smoke test: Gateway created all three sockets and the ROS backend
  connected, ran, and shut down without sending a non-zero motion command.
