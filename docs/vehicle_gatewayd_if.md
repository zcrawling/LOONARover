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
| `backend.sock` | LIMO or future LOONAR backend | receives selected motion; sends common `VehicleStatus` |

## Motion and selection

The shared motion fields are `linear_mps: float64` and
`angular_radps: float64`.  NaN and Inf are malformed and ignored.  No other
range or freshness rule exists in this process.

The gateway status is exactly `STOP`, `MANUAL`, `AUTO`, `PAYLOAD`, or
`REACTION`. Payload and Reaction are cFS-selected operational states; their
MCU-specific command paths remain outside the vehicle motion backend.

1. A cFS `STOP` immediately sends `(0,0)` and records `STOP`.
2. A cFS `MANUAL(v,w)` records `MANUAL` and immediately forwards `(v,w)`.
3. A cFS `AUTO select` records `AUTO`; it does not replay an old ROS command.
4. A ROS `AUTO(v,w)` forwards only while the recorded status is `AUTO`.

`PAYLOAD` and `REACTION` selection do not replay a motion command. cFS sends an
explicit `STOP` before selecting either state. The gateway then reports the
selected state to cFS and ROS so an intentional non-moving payload/recovery
operation is not diagnosed as autonomy loss.

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

## Status telemetry

The backend emits a common 92-byte `VehicleStatus` envelope. Gateway validates
its framing and relays it unchanged to the cFS peer; telemetry never rejects,
clamps, or changes a command. The LIMO backend produces it once per second from
`/limo_status`, `/wheel/odom`, and `/imu`. `valid_flags` identifies observed
fields, so battery percentage remains invalid rather than being estimated from
voltage.

The final LOONAR backend must additionally publish MCU uptime, board
temperature, MCU state, inhibit flags, applied linear/angular command, RX error
count, and device connection states. Their cFS messages and GroundLink
serialization exist; the final serial producer remains a porting task.

## Debugger

`vehicle_gatewayd` prints the current mode once per second and every received
command. `vehicle_gatewayctl monitor SOCKET` prints status changes, for example
`mode=MANUAL last=manual linear=0.4 angular=1.0`.
