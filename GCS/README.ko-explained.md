# GCS README 원문과 한국어 해설

README.md의 원문을 순서대로 모두 싣고, 각 절 뒤에 **한국어 해설**을 덧붙였습니다. 영어 본문·명령·표는 원문 그대로이며, 한국어 부분은 이해를 돕기 위한 설명입니다. 이 문서는 실행 결과가 아니라 README의 해설입니다.

# LOONAR Ground Control Station (GCS) handoff

This folder is the ground-station application project. Its job is deliberately
small: show video, send the five vehicle commands, and show the telemetry that
comes back. It does **not** run ROS, cFS, or motor-control code. Those live on
the rover.

This document is written so that someone new to Linux and programming can build
the first usable version with Codex. Do the stages in order and keep each stage
working before starting the next one.


> **한국어 해설**
>
> GCS는 Ground Control Station, 즉 지상 관제 프로그램입니다. 사용자의 PC에서 영상을 보고, 명령을 보내고, 로버의 상태를 확인합니다. telemetry(텔레메트리)는 로버가 전송하는 배터리·위치·속도 같은 상태 정보입니다.
>
> ROS, cFS, 모터 제어는 로버 쪽의 역할입니다. 이 폴더는 PC 쪽 프로그램을 만드는 곳입니다. handoff는 다음 개발자에게 작업 내용과 규칙을 넘겨주는 인계 문서라는 뜻입니다.

---

## What you are building

The finished GCS PC runs two independent data paths:

```text
camera:  rover -- UDP 5600 / H.264 MPEG-TS --> video player on GCS PC
control: GCS UI -- local HTTP/WebSocket --> GCS backend -- TCP 7443 --> rover cFS
```

The GCS backend keeps the one persistent TCP connection to the rover. The UI
must never open its own connection to port 7443. Video is not sent through the
backend, cFS, or ROS.


> **한국어 해설**
>
> 영상과 조종은 서로 독립된 통신을 사용합니다. 영상은 로버에서 PC의 영상 재생기로 바로 전달됩니다. H.264는 영상 압축 방식, MPEG-TS는 그 영상을 담아 전송하는 형식입니다.
>
> 조종은 ‘브라우저 화면(UI) → PC의 통신 프로그램(백엔드) → 로버’ 순서입니다. HTTP/WebSocket은 화면과 백엔드 사이의 통신이고, TCP 7443은 백엔드와 로버 사이의 통신입니다. 7443과 5600은 컴퓨터 안에서 통신 대상을 구분하는 포트 번호입니다.
>
> 브라우저가 로버에 직접 연결하지 않고 백엔드가 연결 하나를 계속 유지합니다. 영상이 나온다고 조종 연결도 성공한 것은 아닙니다.

---

### What is already implemented on the rover

- TCP GroundLink server: `<ROVER_IP>:7443`
- five commands: `STOP`, `MANUAL`, `AUTO`, `PAYLOAD`, `REACTION`
- periodic `GatewayStatus` and `VehicleStatus` telemetry, nominally once per
  second
- UDP camera sender to `<GCS_IP>:5600`, using H.264 in MPEG-TS

The validated LIMO test setup uses the configured `<GCS_IP>`, UDP port
`5600`, and TCP port `7443`. Do not hard-code these values in source code;
place them in a local `.env` configuration file.


> **한국어 해설**
>
> 문서에 따르면 로버에는 명령을 받는 GroundLink 서버와 영상 송신 기능이 이미 구현되어 있습니다. 다만 ‘구현되어 있다’는 말이 지금 로버에서 실행 중이라는 뜻은 아닙니다.
>
> GatewayStatus는 현재 모드와 명령 상태, VehicleStatus는 차량의 측정 상태를 뜻합니다. 기본적으로 약 1초마다 받는다고 설명합니다.
>
> `<GCS_IP>`는 시험할 지상국 PC 주소를 뜻합니다. IP와 포트는 코드에 고정하지 않고 로컬 설정 파일에 적도록 합니다.

---

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


> **한국어 해설**
>
> 화면은 사용자의 명령을 전달하고 로버의 응답을 보여주는 역할입니다. 예를 들어 AUTO를 눌렀다는 사실과 로버가 AUTO 모드가 되었다는 사실은 다릅니다. 실제 모드는 로버가 보낸 상태로 확인합니다.
>
> 연결이 복구되었다고 자동으로 STOP이나 AUTO를 보내지 않습니다. STOP 버튼은 사용자가 직접 보내는 정지 명령이며, 이 문서에서 별도의 비상정지 체계를 뜻하지 않습니다.
>
> MCU는 장치 내부의 작은 제어 컴퓨터입니다. PAYLOAD/REACTION은 메시지 형식은 있어도 최종 MCU 기능은 미완성입니다. NOT_IMPLEMENTED는 ‘아직 구현되지 않음’이라는 응답입니다.
>
> TCP는 메시지를 통째로 한 번에 전달한다고 보장하지 않습니다. 한 메시지가 여러 번에 나뉘거나 여러 메시지가 한꺼번에 도착할 수 있습니다. buffer는 데이터를 잠시 모으는 공간, parser는 모인 데이터에서 메시지를 구분하고 해석하는 코드입니다.

---

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


> **한국어 해설**
>
> Python으로 통신 프로그램을 만들고, HTML·CSS·JavaScript로 브라우저 화면을 만드는 구성입니다.
>
> FastAPI는 화면이 요청할 수 있는 창구를 만들고 uvicorn은 그 서버를 실행합니다. socket은 로버와 데이터를 주고받는 Python 기능입니다. ffplay/GStreamer는 영상 수신과 재생을 담당합니다.
>
> 이 절은 첫 버전을 작게 만들기 위한 기술 선택 안내입니다. 실행할 프로그램이 이미 준비되어 있다는 설명은 아닙니다.

---

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
ROVER_HOST=<ROVER_IP>
GROUNDLINK_PORT=7443
VIDEO_PORT=5600
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
```

`ROVER_HOST` is the Raspberry Pi/LIMO computer IP, not the camera IP. The GCS
PC must have the IP configured as the video sender's destination. If the GCS PC
IP changes, the rover video service configuration must be updated too.


> **한국어 해설**
>
> 이 명령들은 사용자 PC에서 실행하는 설치 예시입니다. SSH로 로버에 들어간 터미널에서 실행하면 로버에 설치하게 됩니다.
>
> - sudo apt update: 설치할 수 있는 패키지 목록을 갱신합니다.
> - sudo apt install: Python과 영상 처리 도구를 설치합니다.
> - cd: GCS 폴더로 이동합니다. /path/to/LOONAR/GCS는 예시 경로입니다. 이 작업 공간에서는 $HOME/LOONAR/LOONARover/GCS입니다.
> - python3 -m venv .venv: 이 프로젝트용 Python 실행 환경을 만듭니다.
> - source .venv/bin/activate: 해당 환경을 사용하도록 현재 터미널을 설정합니다.
> - pip install: Python 라이브러리를 설치합니다.
>
> .env의 ROVER_HOST는 로버 컴퓨터 주소입니다. 실제 장비에서 확인한 로버 주소를 사용합니다. BACKEND_HOST=127.0.0.1은 ‘내 PC 자신’을 뜻하며, 로버 IP와 다릅니다. BACKEND_PORT=8000은 PC 안에서 화면과 백엔드가 통신하는 포트입니다.
>
> 영상은 로버가 지정된 PC 주소로 보내므로 수신 PC의 주소도 맞아야 합니다. 로버 설정 변경이 필요하다는 문서 설명과 별개로, 이번 프로젝트의 수정 허용 범위는 사용자가 정한 GCS 내부입니다.

---

## First network checks

From the GCS PC:

```bash
ping -c 3 <ROVER_IP>
nc -vz <ROVER_IP> 7443
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


> **한국어 해설**
>
> ping은 상대 IP에서 응답이 오는지 확인합니다. nc -vz는 특정 TCP 포트에 연결할 수 있는지 확인합니다. ping 성공만으로 7443 포트나 GCS 통신까지 확인된 것은 아닙니다.
>
> 7443은 로버의 GroundLink가 실행 중이어야 열립니다. 문서의 첫 버전은 클라이언트 하나를 받는 구조라서 진단 도구와 GCS가 동시에 접속하면 서로 영향을 줄 수 있습니다.
>
> ufw status는 PC 방화벽 상태를, ip -4 addr는 PC의 IPv4 주소들을 보여줍니다. `<ROVER_IP>`는 실제 로버 주소로 바꿔 읽으세요.

---

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


> **한국어 해설**
>
> ffplay 명령은 내 PC의 UDP 5600으로 들어오는 영상을 재생합니다. 지연을 줄이고 늦은 프레임을 버리는 옵션이 포함되어 있습니다. 이 명령이 로버의 카메라 송신을 시작시키는 것은 아니므로, 로버가 이미 이 PC로 영상을 보내고 있어야 합니다.
>
> GStreamer 명령은 ‘수신 → 영상 추출 → 압축 해제 → 화면 표시’ 단계를 연결한 다른 재생 방법입니다. 둘 중 하나로 확인하면 됩니다. avdec_h264 오류는 해당 디코더 요소가 없다는 뜻입니다.
>
> 첫 버전은 조종 화면과 영상 창을 따로 열어도 됩니다. 영상 확인을 먼저 할 수 있지만, 영상의 브라우저 통합은 뒤 단계입니다.

---

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


> **한국어 해설**
>
> 아래 구조는 앞으로 만들 파일들의 설계도입니다. 이 해설 작성 전 GCS에서 확인된 파일은 README.md 하나였습니다.
>
> - backend/: 설정 읽기, 메시지 변환, 로버 연결, 상태 보관, 화면 요청 처리를 담당합니다.
> - web/: 사용자가 보는 화면과 버튼 동작을 담습니다.
> - tests/: 로버 없이도 코드가 맞는지 검사합니다.
> - requirements.txt: 필요한 Python 라이브러리 목록입니다.
> - .env.example: 설정 작성 예시이고, 실제 환경의 값은 .env에 둡니다.
> - .gitignore: Git 기록에서 제외할 파일을 지정합니다.
>
> protocol.py를 화면 코드와 분리하면 로버 없이 메시지 형식부터 검사할 수 있습니다.

---

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


> **한국어 해설**
>
> 프로토콜은 양쪽이 데이터를 해석하는 약속입니다. frame은 하나의 메시지이며 ‘설명표(header) + 실제 내용(payload)’으로 구성됩니다.
>
> magic은 메시지 시작을 확인하는 표시 LNK1, version은 규칙 버전, type은 메시지 종류, sequence는 명령의 일련번호, payload_length는 본문 길이입니다. u16/u32는 각각 16비트/32비트의 부호 없는 정수입니다.
>
> 헤더는 16바이트이며 본문은 최대 512바이트입니다. 명령에는 0이 아닌 일련번호를 붙이고, 주기적인 상태 보고는 번호 0을 사용합니다. 응답 번호를 보면 어떤 명령에 대한 결과인지 알 수 있습니다.
>
> little-endian은 여러 바이트로 표현하는 숫자의 저장 순서입니다. Python의 <4sHHII는 이 규칙에 맞게 헤더를 구성합니다. 여기서는 형식을 임의로 바꾸면 로버가 이해하지 못합니다. JSON 금지는 로버와의 이 TCP 통신에 관한 것이고, PC 내부 웹 API의 JSON까지 금지한다는 뜻은 아닙니다.

---

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


> **한국어 해설**
>
> 0x0001 같은 값은 16진수로 쓴 메시지 식별 번호입니다. STOP과 AUTO는 메시지 종류만으로 요청이 표현되어 별도 본문이 없습니다.
>
> MANUAL에는 직진 속도 linear_mps(미터/초)와 회전 속도 angular_radps(라디안/초)를 넣습니다. <dd는 두 실수를 정해진 순서의 64비트 값으로 포장한다는 뜻입니다.
>
> PAYLOAD/REACTION에는 요청 ID, 작업 번호(opcode), 매개변수 길이와 내용을 넣습니다. 작업 번호별 구체적 의미는 아직 MCU 명세가 필요하므로 이름만 보고 기능을 추측하면 안 됩니다.

---

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


> **한국어 해설**
>
> 수신 메시지는 크게 ‘명령 처리 결과’, ‘현재 운전 상태’, ‘차량 측정값’, ‘MCU 상태’, ‘장치 연결 상태’, ‘이벤트 기록’으로 나뉩니다.
>
> odometry는 이동량을 바탕으로 추정한 위치·자세, IMU는 기울기와 회전 같은 관성 정보를 측정하는 장치입니다. EVENT는 언제 어떤 일이 있었는지 알려주는 기록입니다.
>
> 표의 바이트 수는 정상 메시지인지 검사할 때 사용합니다. 예를 들어 COMMAND_RESULT 본문이 10바이트가 아니면 규격에 맞지 않습니다. 메시지 형식이 정의되어 있어도 모든 센서 값이 현재 하드웨어에서 제공된다는 뜻은 아닙니다.

---

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


> **한국어 해설**
>
> enum은 숫자에 의미 있는 이름을 붙인 약속입니다. 예를 들어 mode=3은 STOP입니다. result=3은 같은 숫자여도 NOT_IMPLEMENTED입니다. 어느 항목의 숫자인지에 따라 뜻이 달라집니다.
>
> valid_flags는 ‘어떤 측정값을 믿고 표시할 수 있는가’를 알려주는 표시입니다. 각 bit는 항목 하나의 유효 여부를 나타내는 작은 스위치라고 생각하면 됩니다.
>
> 배터리 잔량 정보가 없으면 0%로 표시하지 말고 —로 표시해야 합니다. ‘모른다’와 ‘실제로 0이다’를 구분하는 규칙입니다.

---

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


> **한국어 해설**
>
> TCP client는 PC에서 로버 서버로 접속하는 코드입니다. 연결 후 계속 데이터를 받아 메시지를 해석하고 최신 상태를 저장합니다. 연결이 끊어지면 끊김을 표시하고 잠시 후 재접속합니다.
>
> 이때 이전 측정값은 과거 정보라는 표시와 함께 보존합니다. 새 연결만으로 모드를 판단하지 않고 새로운 상태 보고를 기다립니다. 전송한 명령은 pending(응답 대기)으로 저장하고 같은 번호의 결과가 오면 갱신합니다.
>
> 틀린 메시지가 오면 임의로 해석을 이어가지 않고 연결을 닫고 다시 연결합니다. thread는 별도로 실행되는 작업 흐름이며, lock은 여러 작업이 상태를 동시에 바꿔 데이터가 섞이지 않도록 하는 장치입니다. snapshot은 특정 시점의 상태를 모은 사본입니다.

---

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


> **한국어 해설**
>
> API는 화면이 백엔드에 요청하는 정해진 창구입니다. GET은 상태를 읽고, POST는 명령 전송을 요청합니다. /api/health는 프로그램 작동과 로버 연결 여부를, /api/state는 표시할 상태 전체를 제공합니다.
>
> 127.0.0.1:8000은 사용자 PC 안의 백엔드 주소입니다. PC 브라우저와 PC 백엔드 사이에서는 JSON 형태의 데이터를 사용할 수 있습니다.
>
> 화면의 요청을 PC가 접수한 것과 로버가 명령을 받아 처리한 결과는 서로 다른 단계입니다. 따라서 HTTP 성공만 보고 ‘로버 작업 완료’라고 표시하면 안 됩니다.
>
> polling은 화면이 주기적으로 상태를 물어보는 방식이고, WebSocket은 연결을 유지하면서 상태 갱신을 전달하는 방식입니다. 처음에는 1초마다 물어보는 방식으로 충분하다는 안내입니다.

---

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


> **한국어 해설**
>
> 첫 화면에는 연결 여부, 로버의 실제 모드, 조종 버튼, 명령 결과, 차량 측정값, 장치 상태, 이벤트 기록, 향후 기능 영역을 표시합니다.
>
> 사용자는 ‘내가 무엇을 요청했는가’와 ‘로버가 실제로 어떤 상태인가’를 구별할 수 있어야 합니다. AUTO를 눌렀다는 이유만으로 현재 모드 표시를 AUTO로 바꾸지 않습니다.
>
> 수동 조종은 화면에 표시된 직진·회전 속도 그대로 전송합니다. STOP 버튼은 항상 보이도록 합니다. 아직 구현되지 않은 기능은 미완성으로 표시합니다.

---

## Development stages and acceptance tests


> **한국어 해설**
>
> 아래 단계는 개발 순서와 각 단계의 통과 기준입니다. acceptance test는 ‘이 단계가 끝났다고 판단할 확인 항목’이라는 뜻입니다. 명령 예시는 관련 파일을 구현한 뒤 실행하는 것이며, README만 있는 상태에서 모두 바로 실행되는 것은 아닙니다.

---

### Stage 1 — project starts locally

- Create the virtual environment and a FastAPI `/api/health` endpoint.
- Run `uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000`.
- Open `http://127.0.0.1:8000/docs` and verify the health route.


> **한국어 해설**
>
> 첫 목표는 내 PC에서 서버 하나가 정상 실행되는지 확인하는 것입니다. 가상환경과 최소 FastAPI 코드를 만든 후 uvicorn으로 실행합니다. /docs는 API를 확인하는 문서 화면입니다. 아직 로버 조종 단계가 아닙니다.

---

### Stage 2 — protocol unit tests

- Implement header encode/decode and buffered frame parser.
- Write tests for: split header, split payload, two frames in one receive,
  wrong magic, wrong version, payload length 513, and MANUAL payload round trip.
- Run `python -m unittest discover -s tests -v` until all pass.


> **한국어 해설**
>
> 두 번째는 메시지 포장과 해석이 정확한지 검사합니다. 메시지가 여러 조각으로 도착하거나 여러 개가 함께 도착해도 처리해야 합니다. 최대 길이 512를 넘는 513바이트 메시지를 거부하는지도 검사합니다. unittest 명령은 만든 테스트들을 실행합니다.

---

### Stage 3 — live telemetry monitor

- Implement TCP connection/reconnection and parse only received telemetry.
- Connect to the rover with no command buttons wired yet.
- Verify `GatewayStatus` and `VehicleStatus` appear in `/api/state`.
- Disconnect Wi-Fi briefly; verify UI shows disconnected and reconnects without
  changing displayed rover mode after telemetry resumes.


> **한국어 해설**
>
> 세 번째는 실제 로버에 연결해서 상태만 받아보는 단계입니다. 버튼으로 명령을 보내기 전에 통신과 표시부터 확인합니다. Wi-Fi 복구 후에도 자동 명령 없이 상태 수신이 다시 되는지 확인합니다.

---

### Stage 4 — discrete commands

- Add STOP, AUTO, then MANUAL APIs and buttons.
- For each click, show a pending sequence then show its matching
  `COMMAND_RESULT`.
- Start with `MANUAL(0.0, 0.0)` during bench testing.
- When a physical motion test is authorized, use a small value chosen by the
  operator and finish with explicit STOP.


> **한국어 해설**
>
> 네 번째는 STOP, AUTO, MANUAL을 차례로 붙이는 단계입니다. 버튼을 누르면 ‘응답 대기’를 표시하고 로버 결과가 오면 갱신합니다. MANUAL(0.0, 0.0)은 직진·회전 속도 모두 0인 수동 명령입니다. 실제 이동 시험은 작업자가 승인한 조건과 선택한 속도로 진행하고 명시적으로 STOP을 보내는 절차입니다.

---

### Stage 5 — complete display

- Add fields guarded by `valid_flags`, device states, event log, and activity
  placeholders.
- Add WebSocket push updates only if one-second polling is no longer sufficient.


> **한국어 해설**
>
> 다섯 번째는 상태 화면을 완성합니다. 센서 정보의 유효 여부, 장치 연결 상태, 사건 기록 등을 추가합니다. 1초 단위 조회로 충분하지 않을 때 WebSocket을 추가합니다.

---

### Stage 6 — video convenience

- Keep `ffplay`/GStreamer working as the reference receiver.
- Optional: add a UI button that launches the known video-player command, or
  document it next to the UI. Do not couple it to GroundLink TCP.


> **한국어 해설**
>
> 여섯 번째는 영상 사용을 편하게 하는 단계입니다. ffplay/GStreamer 수신을 유지하면서 재생기 실행 버튼 등을 선택적으로 추가할 수 있습니다. 영상 편의 기능과 조종 연결은 독립적으로 유지합니다.

---

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


> **한국어 해설**
>
> 이 절은 로버 안에서 GroundLink가 상태를 보내는지 확인하는 진단 방법입니다. 앞의 PC 설치·수신 명령과 달리 로버 터미널에서 실행하도록 되어 있습니다.
>
> MOCK 변수에 진단 프로그램 경로를 넣고, timeout 5로 5초 동안 monitor를 실행합니다. 여기서 127.0.0.1은 명령을 실행하는 로버 자신입니다. 원문의 빌드 경로에 실행 파일이 실제로 있어야 사용할 수 있습니다.
>
> 출력 예시의 mode=3은 STOP, battery_voltage=11.6은 배터리 전압입니다. 종료 코드 124는 제한 시간으로 종료했다는 뜻입니다. GCS와 동시에 연결하지 말라는 앞 절의 조건도 적용됩니다.

---

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


> **한국어 해설**
>
> 한 번에 전체 개발을 요청하기보다 ‘현재 어느 단계이고 무엇만 만들 것인지’를 명확히 하라는 안내입니다. 예시들은 통신 테스트만 구현하기, 상태 수신만 구현하기, STOP 버튼만 추가하기처럼 범위를 정합니다.
>
> git diff는 파일의 변경 전후 차이를 보는 명령입니다. commit은 변경을 Git 기록에 저장하는 것입니다. 이번 프로젝트에서는 사용자 지시에 따라 GCS 안에서만 수정할 수 있습니다.

---

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


> **한국어 해설**
>
> 첫 버전이 완성되었다고 부를 조건입니다. 영상 수신, 제어 연결과 재접속, 정확한 상태 표시, 명령과 결과 확인, 미완성 기능의 정직한 표시, 메시지 해석 테스트가 모두 필요합니다.
>
> 이 목록은 현재 완료 상태를 보고하는 것이 아니라 앞으로 충족할 목표입니다.

---

## Related source documents

- [GroundLink protocol](../docs/ground_link_protocol.md)
- [Ground-control implementation plan](../docs/ground_control_implementation_plan.md)
- [cFS GroundLink integration](../cfs/README.md)
- [Direct video pipeline](../common/video/README.md)
- [LIMO camera validation notes](../platforms/limo/video/README.md)

> **한국어 해설**
>
> 더 자세한 설명이 있는 관련 문서 목록입니다. 통신 코드를 구현할 때에는 GroundLink protocol 문서를 기준으로 확인하라고 앞 절에서 지정합니다. 나머지는 구현 계획, 로버의 cFS 연동, 영상 전송, LIMO 시험 기록에 관한 자료입니다.

---
