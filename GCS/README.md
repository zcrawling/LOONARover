# LOONAR Ground Control Station (GCS) handoff

This folder is the ground-station application project. Its job is deliberately
small: show video, send the five vehicle commands, and show the telemetry that
comes back. It does **not** run ROS, cFS, or motor-control code. Those live on
the rover.

This document is written so that someone new to Linux and programming can build
the first usable version with Codex. Do the stages in order and keep each stage
working before starting the next one.

## What you are building

The finished GCS PC runs two independent data paths:

```text
camera:  rover -- UDP 5600 / H.264 MPEG-TS --> video player on GCS PC
control: GCS UI -- local HTTP/WebSocket --> GCS backend -- TCP 7443 --> rover cFS
```

The GCS backend keeps the one persistent TCP connection to the rover. The UI
must never open its own connection to port 7443. Video is not sent through the
backend, cFS, or ROS.

### What is already implemented on the rover

- TCP GroundLink server: `<ROVER_IP>:7443`
- five commands: `STOP`, `MANUAL`, `AUTO`, `PAYLOAD`, `REACTION`
- periodic `GatewayStatus` and `VehicleStatus` telemetry, nominally once per
  second
- UDP camera sender to `<GCS_IP>:5600`, using H.264 in MPEG-TS

The currently validated LIMO test setup uses GCS IP `192.168.0.86`, UDP port
`5600`, and TCP port `7443`. Do not hard-code these values in source code;
place them in a local `.env` configuration file.

## Important behaviour to understand first

1. The rover owns mode selection. The GCS sends an explicit command and displays
   the result returned by the rover.
2. Do not add client-side command limits, command expiry timers, authority
   systems, hidden command rewriting, or automatic mode changes. The UI sends
   the value the operator selected. The rover's explicit command routes decide
   the final action.
3. `STOP` is an explicit command and must always be visible as a button. It is
   not an emergency feature implemented by the UI; it is simply forwarded to
   the rover.
4. A TCP reconnect does **not** change rover mode. After reconnecting, wait for
   status telemetry and redraw the UI from it.
5. `PAYLOAD` and `REACTION` command envelopes already exist. Their final LOONAR
   MCU functionality is not implemented yet. In particular, `REACTION` currently
   returns `NOT_IMPLEMENTED`; display that as an honest result, not as a broken
   TCP connection.
6. TCP is a byte stream. One `recv()` call may contain half a frame, exactly one
   frame, or several frames. A correct buffer/parser is mandatory.

## Recommended first-version technology

Use a small Python application. It is the easiest path for a beginner to read,
run, and modify with Codex.

- Python 3.10 or newer
- `FastAPI` + `uvicorn`: local PC backend and HTTP/WebSocket API
- plain HTML, CSS and JavaScript: initial UI (no React/Electron required)
- Python standard-library `socket`: rover TCP connection and binary protocol
- `ffplay` or GStreamer: first video receiver, outside the web UI

Do not start with a packaged desktop application, React, Docker, ROS 2, or a
database. They do not help the first working control path.

## PC setup (Ubuntu example)

Run these commands in the GCS PC terminal, not through SSH on the rover.

```bash
sudo apt update
sudo apt install -y python3 python3-venv ffmpeg gstreamer1.0-tools gstreamer1.0-libav

cd /path/to/LOONAR/GCS
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install fastapi 'uvicorn[standard]'
```

Create `.env` locally and do not commit it:

```text
ROVER_HOST=192.168.0.85
GROUNDLINK_PORT=7443
VIDEO_PORT=5600
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
```

`ROVER_HOST` is the Raspberry Pi/LIMO computer IP, not the camera IP. The GCS
PC must have the IP configured as the video sender's destination. If the GCS PC
IP changes, the rover video service configuration must be updated too.

## First network checks

From the GCS PC:

```bash
ping -c 3 192.168.0.85
nc -vz 192.168.0.85 7443
```

The TCP port is open only while the rover cFS GroundLink application is running.
Do not run `ground_link_mock` at the same time as the real GCS backend: the
first version of GroundLink is designed for one connected ground client.

If UDP video does not arrive, check the GCS PC firewall and Wi-Fi network before
changing application code:

```bash
sudo ufw status
ip -4 addr
```

## Verify camera video first

Video is independent from the command/telemetry path. On the GCS PC, run:

```bash
ffplay -fflags nobuffer -flags low_delay -framedrop udp://@:5600
```

Or use GStreamer:

```bash
gst-launch-1.0 -v \
  udpsrc port=5600 caps='video/mpegts,systemstream=(boolean)true,packetsize=(int)188' \
  ! tsdemux ! h264parse ! avdec_h264 ! videoconvert ! autovideosink sync=false
```

If GStreamer says `no element "avdec_h264"`, install
`gstreamer1.0-libav` on the **GCS PC**, then rerun the command. A video window
proves only the video path; it says nothing about GroundLink TCP.

For the first UI version, launch the video player separately. Browser playback
of MPEG-TS/H.264 is not a first-stage requirement. Embedding video can be added
later only if it is genuinely needed.

## Create this folder structure

Ask Codex to create these files one small stage at a time:

```text
GCS/
  README.md                    # this handoff
  .gitignore                   # .venv/, .env, __pycache__/
  requirements.txt             # fastapi, uvicorn
  .env.example                 # no private IP/password values
  backend/
    __init__.py
    config.py                  # reads .env
    protocol.py                # GroundLink frame encode/decode only
    rover_client.py            # one reconnecting TCP client
    state.py                   # latest telemetry and command results
    app.py                     # FastAPI routes and WebSocket
  web/
    index.html
    app.js
    style.css
  tests/
    test_protocol.py
    test_stream_parser.py
```

Keep the binary protocol independent from FastAPI and the web UI. It must be
unit-testable with no rover connected.

## GroundLink protocol: exact contract

The authoritative detailed document is
[`../docs/ground_link_protocol.md`](../docs/ground_link_protocol.md). Read it
before writing `protocol.py`.

Every TCP frame is:

```text
magic:u32 | version:u16 | type:u16 | sequence:u32 | payload_length:u32 | payload
```

- Header size: 16 bytes
- magic bytes on the wire: ASCII `LNK1`
- protocol version: `1`
- byte order: little-endian for all integers and `float64` values
- maximum payload length: 512 bytes
- `sequence`: nonzero increasing value selected by the GCS for every command
- periodic telemetry has sequence `0`

Python header helpers should use this exact layout:

```python
import struct

HEADER = struct.Struct("<4sHHII")
MAGIC = b"LNK1"
VERSION = 1
MAX_PAYLOAD = 512

def encode_frame(frame_type: int, sequence: int, payload: bytes = b"") -> bytes:
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("payload too large")
    return HEADER.pack(MAGIC, VERSION, frame_type, sequence, len(payload)) + payload
```

Do not use native C structure layouts, `pickle`, JSON, or network-byte-order
(`!`) struct formats for this rover TCP connection.

### Command frames to send

| UI action | Type | Type ID | Payload encoder |
| --- | ---: | ---: | --- |
| STOP button | `STOP_CMD` | `0x0001` | empty bytes |
| Manual joystick/value | `MANUAL_CMD` | `0x0002` | `struct.pack("<dd", linear_mps, angular_radps)` |
| AUTO button | `AUTO_CMD` | `0x0003` | empty bytes |
| Payload activity | `PAYLOAD_CMD` | `0x0004` | `<QHH` + parameters |
| Reaction activity | `REACTION_CMD` | `0x0005` | `<QHH` + parameters |

`PAYLOAD_CMD` / `REACTION_CMD` header inside their payload is:

```text
request_id:u64 | opcode:u16 | parameter_length:u16 | parameters
```

The current allowed parameter length is 0–64 bytes. Start with a UI that can
send an integer request ID and integer opcode. Do not invent payload/reaction
opcode meanings; they will be supplied with their MCU specifications.

### Frames received from rover

| Type | ID | Show in UI |
| --- | ---: | --- |
| `COMMAND_RESULT` | `0x8001` | command sequence, accepted/forwarded flags, mode, result |
| `GATEWAY_STATUS` | `0x8002` | current mode and last linear/angular command |
| `VEHICLE_STATUS` | `0x8003` | battery, odometry, velocity, IMU, field validity |
| `LOONAR_MCU_STATUS` | `0x8004` | future MCU state, temperature, errors, applied motion |
| `DEVICE_STATUS` | `0x8005` | IMU/motor/payload/LiDAR/camera/MCU link/Wi-Fi connection state |
| `EVENT` | `0x8006` | timestamped source, severity, code and text |

The fixed payload sizes are useful parser checks:

| Type | Expected payload size |
| --- | ---: |
| `COMMAND_RESULT` | 10 bytes |
| `GATEWAY_STATUS` | 20 bytes |
| `VEHICLE_STATUS` | 92 bytes |
| `LOONAR_MCU_STATUS` | 50 bytes |
| `DEVICE_STATUS` | `9 + 9 * device_count` bytes |
| `EVENT` | variable, validate its two string lengths |

### Enum values to display

```text
mode:          1=AUTO, 2=MANUAL, 3=STOP, 4=PAYLOAD, 5=REACTION
result:        0=OK, 1=BAD_PAYLOAD, 2=GATEWAY_DISCONNECTED,
               3=NOT_IMPLEMENTED, 4=INTERNAL_ERROR
device state:  0=UNKNOWN, 1=CONNECTED, 2=DISCONNECTED, 3=ERROR
```

For `VEHICLE_STATUS`, only display a field if its bit is set in `valid_flags`:

```text
bit 0: battery voltage       bit 1: battery percentage
bit 2: odometry pose         bit 3: odometry linear/angular velocity
bit 4: IMU roll/pitch/yaw
```

An unavailable field is not zero. Show `—` (unknown) instead. LIMO currently
provides battery voltage, odometry and IMU; battery percentage can be unknown.

## TCP client rules

Implement `rover_client.py` as one background task/thread with this behaviour:

1. Connect to `ROVER_HOST:GROUNDLINK_PORT`.
2. Mark `tcp_connected=True` in shared state.
3. Continuously append received bytes to a buffer.
4. While the buffer contains a full valid frame, decode it and update state.
5. On disconnect/error, mark `tcp_connected=False`, preserve the last received
   rover mode as stale display data, wait briefly, and reconnect.
6. Do not send any automatic STOP, AUTO, or MANUAL command on connect or
   reconnect.
7. Give each user-requested command the next nonzero sequence number. Store it
   as pending until its matching `COMMAND_RESULT.ground_sequence` arrives.

The parser must reject a wrong magic/version, unknown type, payload length over
512, or malformed fixed payload. On malformed input, close and reconnect rather
than trying to guess byte alignment.

Suggested state object:

```text
connection: connected/disconnected + last connection error
gateway: current mode, last command, last update time
vehicle: decoded latest VehicleStatus + last update time
mcu: latest McuStatus + last update time
devices: seven decoded device entries + last update time
events: last 100 events, newest first
pending_commands: sequence -> requested command/time
last_command_result: decoded CommandResult
```

Use a lock around this state if the TCP client runs in a Python thread. WebSocket
messages should be snapshots made from that state, not raw socket data.

## Local backend API to implement

Keep this API on `127.0.0.1:8000` initially. The browser UI and backend are on
the same GCS PC.

| Method/path | Request | Result |
| --- | --- | --- |
| `GET /api/health` | none | backend alive, rover TCP connected/disconnected |
| `GET /api/state` | none | one JSON snapshot of latest display state |
| `POST /api/command/stop` | none | accepted sequence number |
| `POST /api/command/manual` | `{ "linear_mps": 0.5, "angular_radps": 0.0 }` | accepted sequence number |
| `POST /api/command/auto` | none | accepted sequence number |
| `POST /api/command/payload` | request ID/opcode/parameters | accepted sequence number |
| `POST /api/command/reaction` | request ID/opcode/parameters | accepted sequence number |
| `WS /ws` | none | push a state snapshot whenever telemetry/result changes |

The POST response means only that the local backend accepted the UI request. The
UI must show the later `COMMAND_RESULT` from the rover separately. Never label a
button press as “vehicle completed” just because the HTTP request succeeded.

For the first stage, it is acceptable for the browser to poll `/api/state` once
per second instead of using WebSocket. Add WebSocket only after command sending
and parsing work.

## UI: required first screen

Make one simple page. Plain and obvious is better than a polished dashboard.

1. **Connection strip**: backend status, rover TCP status, and last telemetry
   receive time.
2. **Mode strip**: large current mode from `GatewayStatus`; do not infer it from
   the last pressed UI button.
3. **Command panel**:
   - STOP button
   - AUTO button
   - manual selected label
   - linear and angular numeric fields plus a small joystick or arrow controls
   - show the exact linear/angular values most recently sent
4. **Command result panel**: sequence, command, `OK`/error result, current mode.
5. **Vehicle panel**: battery voltage/percent, odometry, velocity, IMU; use `—`
   for invalid fields.
6. **Device panel**: IMU, motor, payload sensor, LiDAR, camera, MCU link, Wi-Fi.
7. **Event panel**: timestamp, severity, source and text.
8. **Payload/Reaction panel**: placeholders that show the current mode and
   received events/results. Do not claim that payload/reaction hardware works
   before its MCU protocol exists.

Manual control UI rule: a joystick movement sends a `MANUAL_CMD` with exactly
the displayed `linear_mps` and `angular_radps`. The UI should not secretly send
another value or automatically change mode. A separate explicit STOP button is
always available.

## Development stages and acceptance tests

### Stage 1 — project starts locally

- Create the virtual environment and a FastAPI `/api/health` endpoint.
- Run `uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000`.
- Open `http://127.0.0.1:8000/docs` and verify the health route.

### Stage 2 — protocol unit tests

- Implement header encode/decode and buffered frame parser.
- Write tests for: split header, split payload, two frames in one receive,
  wrong magic, wrong version, payload length 513, and MANUAL payload round trip.
- Run `python -m unittest discover -s tests -v` until all pass.

### Stage 3 — live telemetry monitor

- Implement TCP connection/reconnection and parse only received telemetry.
- Connect to the rover with no command buttons wired yet.
- Verify `GatewayStatus` and `VehicleStatus` appear in `/api/state`.
- Disconnect Wi-Fi briefly; verify UI shows disconnected and reconnects without
  changing displayed rover mode after telemetry resumes.

### Stage 4 — discrete commands

- Add STOP, AUTO, then MANUAL APIs and buttons.
- For each click, show a pending sequence then show its matching
  `COMMAND_RESULT`.
- Start with `MANUAL(0.0, 0.0)` during bench testing.
- When a physical motion test is authorized, use a small value chosen by the
  operator and finish with explicit STOP.

### Stage 5 — complete display

- Add fields guarded by `valid_flags`, device states, event log, and activity
  placeholders.
- Add WebSocket push updates only if one-second polling is no longer sufficient.

### Stage 6 — video convenience

- Keep `ffplay`/GStreamer working as the reference receiver.
- Optional: add a UI button that launches the known video-player command, or
  document it next to the UI. Do not couple it to GroundLink TCP.

## Use the existing rover-side mock to diagnose

The rover repository includes `ground_link_mock`, which is useful to prove the
rover path before blaming GCS code. Run it on the rover, not on the GCS PC:

```bash
MOCK=~/loonar_ws/build/ground_link/ground_link_mock
timeout 5 "$MOCK" 127.0.0.1 7443 monitor
```

It prints frames such as:

```text
type=GATEWAY_STATUS ... mode=3 linear=0 angular=0
type=VEHICLE_STATUS ... valid=0x1d battery_voltage=11.6 odom=(...)
```

It intentionally keeps receiving status frames, so `timeout` exit code `124`
is expected and is not a failure.

## How to work with Codex effectively

Use small, testable requests. Before every request, tell Codex which stage you
are on and paste the exact terminal error if there is one.

Good prompts:

```text
Read GCS/README.md. Implement only Stage 2 in GCS/backend/protocol.py and
GCS/tests. Do not create a UI or connect to the rover. Run the unit tests.
```

```text
Read GCS/README.md and inspect the existing Stage 2 code. Implement only the
read-only TCP telemetry client from Stage 3. Do not send any command. Add a
small terminal log and tests for split TCP frames.
```

```text
Read GCS/README.md. Add only the STOP endpoint and UI button. Keep the protocol
format unchanged. Show the returned COMMAND_RESULT separately from local HTTP
success. Run tests.
```

Avoid prompts such as “make the full GCS.” They are too broad and make it hard
to inspect what changed. Ask Codex to explain every new file after each stage,
run the stated tests, and show `git diff` before committing.

## Definition of done for the first GCS version

- Video displays from UDP 5600 on the GCS PC.
- GCS backend holds one TCP connection to port 7443 and reconnects cleanly.
- UI accurately displays rover-reported mode, command results, battery/odom/IMU
  when valid, and device/event data when available.
- STOP, MANUAL and AUTO produce correctly encoded GroundLink commands and show
  their matching rover result.
- PAYLOAD and REACTION envelopes can be sent/displayed, but their future MCU
  execution is clearly labelled TBD/NOT_IMPLEMENTED until implemented.
- Protocol tests cover TCP fragmentation and invalid frames.
- No GCS code changes ROS topics, runs cFS, or silently changes a user command.

## Related source documents

- [GroundLink protocol](../docs/ground_link_protocol.md)
- [Ground-control implementation plan](../docs/ground_control_implementation_plan.md)
- [cFS GroundLink integration](../cfs/README.md)
- [Direct video pipeline](../common/video/README.md)
- [LIMO camera validation notes](../platforms/limo/video/README.md)
