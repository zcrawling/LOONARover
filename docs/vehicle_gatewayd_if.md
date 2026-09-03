# vehicle_gatewayd interface (minimum)

`vehicle_gatewayd` converts one common motion command into a platform backend
command.  It does not apply speed limits, leases, TTLs, backend-health gates,
epochs, sequence checks, or automatic stop rules.

## Endpoints

All endpoints are local `SOCK_SEQPACKET` sockets in
`/run/loonar/vehicle-gateway/`.

| Socket | Peer | Allowed input |
| --- | --- | --- |
| `cfs.sock` | cFS ground-station adapter or ground mock | `STOP`, `AUTO select`, `MANUAL(v,w)` |
| `ros.sock` | ROS vehicle client | `AUTO(v,w)` |
| `backend.sock` | LIMO or future LOONAR backend | receives selected motion |

## Motion and selection

The shared motion fields are `linear_mps: float64` and
`angular_radps: float64`.  NaN and Inf are malformed and ignored.  No other
range or freshness rule exists in this process.

The gateway status is exactly `STOP`, `MANUAL`, or `AUTO`.

1. A cFS `STOP` immediately sends `(0,0)` and records `STOP`.
2. A cFS `MANUAL(v,w)` records `MANUAL` and immediately forwards `(v,w)`.
3. A cFS `AUTO select` records `AUTO`; it does not replay an old ROS command.
4. A ROS `AUTO(v,w)` forwards only while the recorded status is `AUTO`.

Thus a ROS packet cannot cancel manual driving or a stop.  The ground station
performs a handoff explicitly: `STOP`, then `AUTO select`, then ROS supplies a
new auto command.  `STOP` is an explicit command, not a hidden latch,
watchdog, or authority mechanism.

## Backend

The LIMO backend maps the selected motion directly to `/cmd_vel`:
`linear_mps -> Twist.linear.x`, `angular_radps -> Twist.angular.z`.  It does
not inspect `/limo_status` before publishing.  Future LOONAR serial work must
implement the same two-field backend input and map it to `MOTION_CMD`; that
serial backend is intentionally not implemented in the LIMO phase.

## Status telemetry (next implementation unit)

The backend will emit a common `VehicleStatus` envelope to both ROS and the
cFS adapter.  The cFS adapter forwards the complete LOONAR MCU extension to
the ground station: MCU uptime, board temperature, MCU state, inhibit flags,
applied linear/angular command, RX error count, and available battery data.
LIMO-specific fields remain separate: vehicle state, control/motion mode,
battery voltage, and vendor error code.  Odom and IMU remain common ROS data.

## Debugger

`vehicle_gatewayctl monitor SOCKET` prints gateway status as it changes, for
example `mode=MANUAL last=manual linear=0.4 angular=1.0`.  The next telemetry
unit extends this output with the received hardware status.
