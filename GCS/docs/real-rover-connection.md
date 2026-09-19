# 실제 로버 통신 시작 방법

이 문서는 실제 GroundLink v1 로버에서 **상태 정보만 수신**하는 첫 연결 절차다.
스크립트는 로버에 어떤 명령 바이트도 보내지 않는다.

## 1. 네트워크와 포트 확인

GCS PC 터미널에서 실행한다. 아래 주소는 예시이므로 실제 로버 IP로 바꾼다.

```bash
ROVER_IP=192.168.1.50
ping -c 3 "$ROVER_IP"
nc -vz -w 3 "$ROVER_IP" 7443
```

`ping` 성공은 두 기기가 네트워크에서 서로 보인다는 뜻이다. `nc` 성공은 로버의
GroundLink TCP 서버가 7443 포트에서 실행 중이라는 뜻이다.

## 2. 텔레메트리 수신

```bash
cd $HOME/LOONAR/LOONARover/GCS
python3 -m cli.groundlink_monitor "$ROVER_IP"
```

정상 연결되면 `[연결 성공]` 다음에 `GATEWAY_STATUS`, `VEHICLE_STATUS` 등의
한 줄 JSON 정보가 표시된다. 종료는 `Ctrl+C`다.

연결 단절 뒤 자동으로 다시 접속하려면 다음과 같이 실행한다.

```bash
python3 -m cli.groundlink_monitor "$ROVER_IP" --reconnect
```

다른 포트를 사용하도록 로버가 설정된 경우에만 `--port`를 지정한다.

```bash
python3 -m cli.groundlink_monitor "$ROVER_IP" --port 7443
```

`Connection refused`는 대개 해당 IP의 7443 포트에서 GroundLink가 실행되지
않는다는 뜻이다. `timed out`은 IP, Wi-Fi 격리, 방화벽 또는 라우팅 문제일 수 있다.
`잘못된 magic`은 상대 프로그램이 GroundLink v1 `LNK1` 형식이 아니라는 뜻이다.

현재 Mock 전용 `backend.app` 및 `mock.rover`와 이 스크립트를 혼용하지 않는다.
GroundLink 첫 버전은 한 번에 하나의 지상 클라이언트 연결을 전제로 한다.

## 3. 키보드 수동 조종

실제 로버가 움직일 수 있는 안전한 장소에서 실행한다. 속도와 키 이름은
`config/gcs.toml`의 `[manual_control]`에 있다.

```bash
cd $HOME/LOONAR/LOONARover/GCS
python3 -m cli.keyboard_control "$ROVER_IP"
```

| 키 | 전송 값 |
| --- | --- |
| Page Up | `MANUAL(+0.1, 0.0)` 전진 |
| Home | `MANUAL(0.0, +0.5)` 좌회전 |
| Page Down | `MANUAL(-0.1, 0.0)` 후진 |
| End | `MANUAL(0.0, -0.5)` 우회전 |
| Space | 명시적인 `STOP` |
| Q | 프로그램 종료; STOP을 전송하지 않음 |

키를 놓는 동작은 별도 메시지를 만들지 않는다. 움직임을 끝낼 때 반드시 Space를
눌러 STOP 결과를 확인한 뒤 Q로 종료한다. 이 프로그램과 읽기 전용
`groundlink_monitor`는 GroundLink 연결을 각각 하나씩 사용하므로 동시에 실행하지 않는다.

## 4. 실제 로버 웹 UI

로버 GroundLink가 실행 중일 때 GCS PC에서 다음 한 명령으로 실제 백엔드와 웹 UI를
함께 시작한다. 같은 포트의 `groundlink_monitor`나 `keyboard_control`은 먼저 종료한다.

```bash
cd $HOME/LOONAR/LOONARover/GCS
python3 -B -m webui.server --real-host 192.168.1.50
```

브라우저에서 `http://127.0.0.1:8080`을 연다. 상단에 `REAL ROVER`가 표시되어야 한다.
STOP, AUTO와 MANUAL(0,0)은 실제 GroundLink 명령으로 전송한다. opcode가 정해지지 않은
PAYLOAD와 REACTION은 전송하지 않는다. 웹 서버 종료는 로버 모드를 자동 변경하지 않는다.
# REMOTE 폴더에서 한 번에 실행

`LOONAR 로버 시작` 아이콘은 `user@IP` 형식의 SSH 주소를 입력받아 로버의
`limo_base`, `vehicle_gatewayd`, `loonar_limo_backend`, `core-cpu1`을 순서대로
확인하고, 실행되지 않은 구성요소만 시작한다. 각 구성요소가 준비된 뒤 다음
구성요소를 시작하며, 실패하면 이후 단계는 실행하지 않는다. SSH 암호는 한 번 입력한다.

`LOONAR 실시간 지상국` 아이콘은 현재 로버 IP를 입력받아 실제 GroundLink
모드로 웹 서버를 시작하고 브라우저를 연다. 화면의 `REAL ROVER`,
`TCP CONNECTED`, 증가하는 `RX` 값으로 실제 데이터 수신을 확인할 수 있다.

`LOONAR 로버 종료` 아이콘은 먼저 속도 0 명령을 전달한 뒤 `core-cpu1`,
`loonar_limo_backend`, `vehicle_gatewayd`, `limo_base`의 역순으로 종료한다.

세 실행 파일은 `$HOME/LOONAR/REMOTE`에 있다. 이 파일들은 해당 폴더에서
텍스트로 열리지 않도록 작은 실행 프로그램으로 만들었으며, 클릭하면 터미널에서
GCS 내부 Bash 스크립트를 실행한다.

`LOONAR 영상 수신`은 지상국의 UDP 5600에서 H.264/MPEG-TS 영상을 기다리고
별도 ffplay 영상 창에 표시한다. 로버 `loonar-video.service`의
`GROUND_STATION_IP`는 현재 지상국 Wi-Fi IP와 같아야 한다.

`LOONAR 로버 시작`은 SSH 연결에서 현재 지상국 IP를 판별하고 로버의 영상
목적지를 자동 갱신한 뒤 영상 서비스를 시작한다. 설정 변경 시 로버의 sudo
암호를 추가로 요구할 수 있다. 로버 준비가 끝나면 별도 영상 수신 창도 연다.
SSH 인증 후 네 구성요소와 영상 송신이 모두 준비된 경우에만 영상 수신 창을
연다. 같은 SSH 연결을 재사용해 로버 셸을 유지하며, `exit`를 입력하면 로버
프로그램은 유지한 채 SSH 연결과 시작 창만 종료한다.

실시간 웹 지상국에 포커스가 있을 때 일반 방향키 ↑/←/↓/→를 누르면 각각
전진/좌회전/후진/우회전 MANUAL 명령을 보낸다. PgUp/Home/PgDn/End도 같은
보조 키로 사용할 수 있다. 속도는 `config/gcs.toml`의
`manual_control` 값을 사용한다. 키를 놓거나 창이 포커스를 잃으면 MANUAL
속도 `(0, 0)`을 보내므로 정지하지만 MANUAL 모드는 유지한다. STOP 모드는
화면의 STOP 버튼을 눌렀을 때만 요청한다.
키를 누르는 동안 `repeat_interval_ms` 간격으로 같은 MANUAL 명령을 갱신하므로
로버 안전 타임아웃이 동작하지 않고 누른 시간만큼 이동한다.
명령 창의 선속도 조절 영역에서 마우스 휠을 사용하면 `0.01~1.00 m/s`
범위를 `0.01 m/s` 단위로 바꿀 수 있다. 이 값은 전진과 후진에만 적용된다.
방향키의 최초 입력과 키 반복 입력 모두 브라우저 기본 스크롤을 차단한다.
