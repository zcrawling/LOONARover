# Ubuntu 24.04 GCS 프로토타입 실행

Python 3.12 표준 라이브러리만 사용한다. pip 설치나 가상환경은 필수가 아니다. 이 버전은 실제 로버에 접속하지 않는 **Mock 전용**이다. 터미널과 상태 화면은 항상 MOCK/예시 데이터로 표시한다.

## 1. 작업 위치

각 터미널에서 아래 위치로 이동한다.

```bash
cd $HOME/LOONAR/LOONARover/GCS
python3 --version
```

## 2. 가상 로버와 백엔드

첫 번째 터미널에서 실행한다.

```bash
python3 -m mock.rover
```

두 번째 터미널에서 실행한다.

```bash
python3 -m backend.app
```

위 두 프로세스는 시험용 상대와 통신 백엔드다. 운용자가 읽는 창은 다음 명령·상태 창이며, 향후 영상 창을 함께 사용한다. 프로토타입에서는 실행 과정이 보이도록 백그라운드 서비스로 설치하지 않는다.

## 3. 명령 입력·응답 창

세 번째 터미널에서 실행한다.

```bash
python3 -m cli.commands
```

다음 명령을 한 줄씩 입력한다.

```text
status
MANUAL
AUTO
PAYLOAD
STOP
REACTION
help
quit
```

PAYLOAD는 Received를 표시하고 측정값을 별도 상태 창에 보낸다. 측정 중 STOP을 보내면 Mock은 PAYLOAD Aborted와 STOP Completed를 각각 반환한다. 이 응답은 예시이며 하드웨어 실행을 의미하지 않는다. 입력 중 비동기 응답이 출력될 수 있다.

단발 전송은 `python3 -m cli.commands --command STOP`으로 가능하다. 단발 모드는 송신 결과만 출력하고 종료한다. 이후 로버 응답은 대화형 명령 창 또는 상태 창에서 확인한다.

## 4. 상태 출력 창

네 번째 터미널에서 실행한다.

```bash
python3 -m cli.monitor
```

현재 상태를 한 번만 보려면 다음 명령을 사용한다.

```bash
python3 -m cli.monitor --once
python3 -m cli.monitor --once --json
```

CONNECTING 대신 초기 확인 중에는 SYNCING, 정상은 CONNECTED, PONG 지연은 DEGRADED, 연결 실패·단절은 RECONNECTING으로 표시한다. 마지막 값과 수신 경과 시간을 보존하며 오래된 값은 구별한다.

## 5. 설정

`config/gcs.toml` 한 곳에서 주소, 시간, 재접속, Keepalive, 표시 주기, Mock 데이터를 설정한다. TOML은 Python 3.12에 기본 지원되어 YAML용 패키지를 설치할 필요가 없다. 변경 후 해당 프로세스를 재시작한다. 별도 설정은 각 명령의 `--config 경로`로 지정한다. local API 경로는 GCS 내부 `.runtime/backend.sock`이다. 백엔드는 하나만 실행할 수 있다.

- PAYLOAD 수신 확인: `command.payload_receipt_timeout = 20.0`
- PING: `heartbeat.interval = 2.0`
- PONG 지연: `degraded_after = 6.0`, `disconnect_after = 20.0`
- 연결 시도: `network.connect_timeout = 3.0`
- 재시도: `network.reconnect_delays = [1.0, 2.0, 4.0, 8.0, 10.0]`
- 가상 PAYLOAD 측정 시간: `mock.payload_duration = 30.0`

`target = "mock"`과 loopback 주소만 허용한다. IP만 라즈베리파이로 바꾸어도 실제 GroundLink에 연결되는 제품이 아니다. 실제 인터페이스가 정해지면 `backend/protocol.py`와 관련 메시지 처리를 맞춰야 한다.

## 6. 장애 시험

Mock을 Ctrl+C로 종료하면 GCS가 재접속한다. Mock을 다시 실행하면 상태를 새로 받는다. 종료된 Mock의 측정 상태는 복구되지 않는다.

Mock 자체는 유지하면서 TCP만 끊는 시험은 `mock.disconnect_after = 5.0`으로 설정하고 Mock을 재시작한다. 각 연결을 5초 후 끊으며, PAYLOAD는 프로세스 내부에서 계속 진행한다. 0.0으로 복원하면 강제 단절을 끈다.

`mock.send_pong = false`로 실행하면 상태 데이터가 계속 와도 GCS는 6초 후 DEGRADED, 20초 후 재접속한다. 이 값은 정상 운용에서 true다.

`mock.receipt_delay = 22.0`으로 실행하면 PAYLOAD Received가 20초를 넘겨 도착한다. GCS가 Command Result Unknown을 표시한 뒤 늦은 Received를 처리하는지 확인한다. 정상값은 0.0이다.

## 7. 테스트

GCS 디렉터리에서 실행한다.

```bash
python3 -m unittest discover -s tests -v
```

테스트는 loopback의 임시 포트를 사용하고 실제 로버에 명령을 보내지 않는다. 테스트의 시간값은 실행 시간을 줄이기 위해 짧게 설정하며 운영 설정의 20초는 별도로 확인한다.

## 8. 별도 GStreamer 영상 수신

영상 송신기가 준비되면 지상국에 GStreamer가 설치되어 있는지 먼저 확인한다.

```bash
gst-launch-1.0 --version
```

필요한 Ubuntu 패키지: `gstreamer1.0-tools`, `gstreamer1.0-plugins-base`, `gstreamer1.0-plugins-good`, `gstreamer1.0-plugins-bad`, `gstreamer1.0-libav`. 이 프로젝트는 시스템 패키지를 자동 설치하지 않는다.

설정 파일의 영상 포트를 사용하는 실행기는 다음과 같다.

```bash
python3 -m cli.video --check
python3 -m cli.video
```

`--check`는 필수 요소만 확인하고 영상 창을 열지 않는다. 실행기는 GStreamer 레지스트리 캐시를 GCS 내부 `.runtime`에 둔다. 영상 송신기가 없으면 화면은 나오지 않는다.

직접 실행하는 다음 명령도 UDP 5600의 H.264/MPEG-TS를 수신·압축 해제·표시한다.

```bash
GST_REGISTRY="$PWD/.runtime/gstreamer-registry.bin" gst-launch-1.0 -v udpsrc port=5600 caps='video/mpegts,systemstream=(boolean)true,packetsize=(int)188' ! tsdemux ! h264parse ! avdec_h264 ! videoconvert ! autovideosink sync=false
```

백엔드를 한 번 실행하여 `.runtime`을 만든 뒤 사용한다. Wi-Fi AP에서 지상국과 로버가 서로 통신 가능해야 하고 송신 대상은 지상국 IP여야 한다. 영상은 Mock이 생성하지 않는다. 영상 원격 제어와 ROS 관측 도구는 후속 연동 범위다.

## 9. 종료와 다음 단계

각 프로세스는 Ctrl+C로 종료한다. 명령 창만 닫는 것은 로버 STOP이 아니다. GCS 재접속·종료는 차량 모드를 자동 변경하지 않는다.

실제 연동에 필요한 것은 라즈베리파이 IP·포트, 합의된 명령/상태/Heartbeat 패킷, 응답 의미, 영상 송신 정보다. Wi-Fi 비밀번호는 GCS에 입력하지 않고 Ubuntu 네트워크 설정으로 연결한다. 상세 계약은 `interface-draft.md`를 참고한다.

## 지상국 시작과 별도 진단 터미널

`start_rover.sh`는 기존 로버 프로그램 및 영상 송신 준비를 수행하고 SSH
터미널을 유지합니다. 영상 **수신 창**은 여기서 열지 않습니다.
`start_gcs.sh`는 백엔드가 준비된 후 웹 UI → 별도 진단 터미널 → 영상
수신 창 순으로 엽니다. 같은 지상국이 이미 실행 중이어도 창 열기를
수행하며, 진단과 영상 수신의 중복 프로세스는 잠금으로 방지합니다.

```bash
cd $HOME/LOONAR/LOONARover/GCS
bash scripts/start_gcs.sh
```

직접 `python3 -B -m webui.server --real-host IP`를 실행하면 별도 창은
자동으로 열리지 않습니다. 진단만 따로 열려면:

```bash
bash scripts/start_diagnostics.sh --host 192.168.1.50
```

진단 창은 GCS 백엔드의 로컬 API를 읽으며 GroundLink에 추가로 접속하지
않습니다. 위쪽에는 타임스탬프와 상태 변경 이력이 쌓이고 아래쪽에는
현재 상태가 갱신됩니다. 상세는 확인 시간이 먼저 표시됩니다.
전체 이력은 `.runtime/diagnostics/*.jsonl`에 저장되며 검사 간격은
`config/gcs.toml`의 `[diagnostics]`에서 조정합니다.

SSH 검사는 로버 시작 때 저장된 계정과 인증 연결을 재사용하거나 기존
SSH 키로 인증합니다. 비밀번호를 저장하거나 반복 입력하지 않습니다.
로버 시작 SSH 창을 닫아 인증 연결이 종료되면 키 인증이 없는 경우
SSH 검사에 실패할 수 있습니다. 이 경우 드라이버는 `확인 불가`로 표시되고,
GroundLink 및 데이터 수신은 별도로 계속 확인합니다.
프로세스 실행 확인 및 `/limo_status` 한 건 수신을 검사하며,
설치·재시작·주행 명령은 수행하지 않습니다. Backend와 Gateway의
프로세스 실행 여부만으로 내부 전달 전체가 정상이라고 단정하지 않습니다.
ping 응답 없음도 네트워크 고장으로 단정하지 않습니다.
Ctrl+C는 진단만 종료하며 웹 지상국 통신은 계속 유지됩니다.
