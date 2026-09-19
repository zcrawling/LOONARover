# 사용자 실행: PC 빌드 → Pi SSH로 Control Teensy 업로드 → 게이트웨이 모터 벤치

에이전트가 Pi 접속, 업로드, 모터 구동을 실행하지 않는다. 아래는 사용자가 실행할 명령이다.
카메라는 사용자 테스트 정상, 왼쪽 90° 회전 보정은 후속 작업이다.
RoboClaw는 M1=오른쪽/M2=왼쪽, Motion Studio 튜닝 및 Write Settings 완료 상태다.

## 1. 현재 소스를 Pi로 복사

개발 PC에서 현재 로컬 변경을 전송한다. main을 새로 clone하는 것만으로는 이 미커밋 코드를 얻을 수 없다.

```bash
cd /home/sb/LOONAR
PI_IP=192.168.0.99  # 현재 Pi 주소로 수정
tar --exclude=.pio --exclude=__pycache__ -czf /tmp/loonar-control-bench.tar.gz \
  platforms/loonar/firmware/control platforms/loonar/tools platforms/loonar/config \
  platforms/loonar/deploy/prepare-control-upload.sh \
  platforms/loonar/deploy/99-loonar-usb.rules \
  platforms/loonar/porting/motor_usb_bench.md
scp /tmp/loonar-control-bench.tar.gz loonar@"$PI_IP":~/
ssh loonar@"$PI_IP"
```

이하 Pi SSH 터미널에서 실행한다. 기존 `~/LOONAR` 사전 준비 저장소와
`/opt/loonar/current/bin/vehicle_gatewayd`, `vehicle_gatewayctl`을 사용한다.

```bash
mkdir -p ~/LOONAR
tar -xzf ~/loonar-control-bench.tar.gz -C ~/LOONAR
cd ~/LOONAR
bash platforms/loonar/deploy/prepare-control-upload.sh
export PATH="$HOME/.local/bin:$PATH"
export PYTHONPATH="$HOME/LOONAR/platforms/loonar/tools"
```

준비 스크립트는 Pi에 apt 의존성과 GUI 없는 TyTools 0.9.8을 설치한다.
이미 설치했다면 매번 실행하지 않는다. PlatformIO와 MCU 툴체인은 개발 PC에서 사용한다.
Ubuntu의 일반 `gcc-arm-none-eabi`는 이 FreeRTOS 포트가 요구하는 newlib locking ABI와
맞지 않으므로 Pi 빌드에 사용하지 않는다. `_LOCK_T`를 억지로 포인터로 바꾸거나
locking 기능을 끄지 않는다. 이전에 설치한 Pi 컴파일러를 제거할 필요는 없다.
firmware를 설치하거나 모터 명령을 보내지 않는다. dialout 그룹을 새로 추가했다면 SSH 재접속이 필요하다.

## 2. Control만 지정해 업로드

업로드 중에는 모터 전원을 끄고 Teensy USB를 유지한다. 실행 중인 bench/serial monitor는 종료한다.

```bash
if systemctl is-active --quiet loonar-mcu@control.service; then
  sudo systemctl stop loonar-mcu@control.service
fi
tycmd list --verbose
```

Control 보드의 **출력된 tag 그대로**를 선택한다. 예를 들어
`add 19971280-Teensy Teensy 4.1 (USB Serial)`이면 tag는 `19971280-Teensy`다.
별도 `location: usb-2-2` 값을 tag에 덧붙이지 않는다.
예시 대신 자신의 출력값을 사용한다. 두 보드 중 어느 것이 Control인지는 최초에 사용자가 물리적으로 확인해야 한다.
부트로더/기존 앱만으로는 Control·Payload라는 사용 목적을 알아낼 수 없다.
이미 LNR2 Payload로 응답하는 보드는 업로드 코드에서 거부한다.

이제 **개발 PC 터미널**에서 실행한다. Teensy USB는 Pi에 연결한 채 유지한다.

```bash
cd /home/sb/LOONAR
python3 platforms/loonar/tools/remote-flash-control.py \
  --host loonar@192.168.0.99 \
  --board '19971280-Teensy'
```

PC에서 빌드한 HEX만 Pi로 전송하고, Pi의 `tycmd`로 업로드한다. 필요한 업로드용 Python
모듈도 자동 복사한다. SSH 연결은 공유하므로 인증은 한 번만 한다. Pi에는 PlatformIO를
실행하지 않는다. 설정은 Pi의 `~/loonar-motor-bench/control.json`에 저장된다.
PC의 `.pio`와 `~/.platformio`를 유지해 설치된 패키지와 이전 빌드 결과를 재사용한다.
UID를 바꿀 때는 UID를 사용하는 `runtime.cpp`만 다시 컴파일하고 링크한다.

처음 LNR2가 없는 보드는 UID 미등록 식별용 firmware를 먼저 빌드·업로드한다.
이 이미지는 RoboClaw/BNO085를 구동하지 않는다. 실제 silicon UID를 읽은 뒤,
그 UID용 현재 Control firmware를 빌드·업로드하고 HELLO의 역할·UID·binding을 확인한다.
LNR2 Control이 이미 있으면 식별용 업로드는 생략한다. 갱신도 같은 명령을 사용한다.
geometry는 아래 사용자 확정값으로 갱신하고 기존 driver 설정은 유지한다.

이 코드는 **선택한 tag만** `tycmd upload --board ...`로 지정한다. 첫 장치 자동 선택,
서명·키·이미지 해시·release manifest·자체 부트로더·GPIO 복구 훅은 없다.
정상 Teensyduino USB의 reboot 요청을 사용하므로 별도 MCU PROGRAM 명령도 추가하지 않았다.
현재 USB 앱이 응답하지 않거나 soft reboot를 지원하지 않으면 버튼 없는 업로드가 실패할 수 있다.
그때는 오류를 보내고 중단한다. 이 코드가 USB/부트로더 고장까지 복구한다고 보장하지 않는다.

## 3. 확정된 차체·드라이버 값

`devices.control.geometry`는 업로드 코드가 아래 사용자 확정값으로 기록한다.

| 필드 | 실제값 |
|---|---|
| `radius_m` | 0.098m — 지름 196mm |
| `track_m` | 0.210m — 중심 간격 210mm |
| `counts_per_rev` | 485681 count / 바퀴·감속기 출력축 1회전 |
| `left_sign`, `right_sign` | 각각 +1 — 전진 시 양쪽 count 증가 |

이전 버전으로 이미 업로드했다면 펌웨어를 다시 올릴 필요 없이, **새 코드를 Pi에 복사한 뒤**
벤치를 종료하고 아래 명령으로 기존 설정만 갱신한다. UID·장치 경로·드라이버 설정은 유지한다.

```bash
export PYTHONPATH="$HOME/LOONAR/platforms/loonar/tools"
python3 - <<'PY'
import json
from pathlib import Path
from mcu_v2.config import CONTROL_GEOMETRY
p = Path.home() / "loonar-motor-bench/control.json"
config = json.loads(p.read_text())
config["devices"]["control"]["geometry"] = dict(CONTROL_GEOMETRY)
p.write_text(json.dumps(config, indent=2) + "\n")
print(config["devices"]["control"]["geometry"])
PY
```

서비스용 `/etc/loonar/mcu-registry.json`을 사용한다면 해당 파일의 Control geometry에도 같은 값을 적용한다.

`roboclaw.address`/`baud`는 Motion Studio에서 저장한 값과 같아야 한다. 코드 초기값은 128/115200이다.
PID는 다시 쓰지 않는다. `counts_per_rev`는 Motion Studio의 최대 속도 QPPS와 다른 값이다.
현재 변환은 좌우 동일한 바퀴 반지름·count/rev를 전제로 한다.

## 4. 터미널 A: 실제 게이트웨이와 Control backend

바퀴를 뺀 벤치 상태에서 모터 전원을 켜고 실행한다.

```bash
export PATH="$HOME/.local/bin:$PATH"
export PYTHONPATH="$HOME/LOONAR/platforms/loonar/tools"
python3 -m mcu_v2.motor_bench \
  --registry "$HOME/loonar-motor-bench/control.json"
```

이 프로그램은 기존 실제 `vehicle_gatewayd`와 현재 Python Control backend를 시작한다.
벤치 전용 socket은 `~/loonar-motor-bench/runtime/gateway/`다. cFS/ROS 서비스는 시작하지 않는다.
센서 표본은 계속 수신해 RAM 버퍼가 막히지 않게 하고, 1초마다 health/모터 피드백을 출력한다.
시작 자체는 주행 명령을 보내지 않는다.

진행 조건: `online=true`, `motor age_ms`가 작고 `valid`에 count/speed bit가 켜져 있어야 한다.
명령 전 `inhibit=8`은 명령 만료/정지 상태로 정상이다. 32는 driver 통신/오류,
128은 CPU 온도 90°C 이상, 1/2는 identity/session 문제다. `error`도 함께 확인한다.
현재 firmware의 driver error 명령90은 32bit 응답을 전제로 한다.

로그는 `~/loonar-motor-bench/runtime/gateway.log`, `backend.log`다.

## 5. 터미널 B: 게이트웨이에 주행 신호 전달

새 Pi SSH 터미널에서 실행한다. 순서는 선속도(m/s), 각속도(rad/s), 지속시간(ms)다.
각 명령은 50ms마다 갱신된다. 아래 예시는 바퀴를 뺀 벤치에서 각각 3초만 실행한다.

```bash
CTL=/opt/loonar/current/bin/vehicle_gatewayctl
SOCK="$HOME/loonar-motor-bench/runtime/gateway/cfs.sock"

# 전진 방향: 0.05 m/s, 3초
"$CTL" manual "$SOCK" 0.05 0 3000
"$CTL" stop "$SOCK"

# 후진 방향: -0.05 m/s, 3초
"$CTL" manual "$SOCK" -0.05 0 3000
"$CTL" stop "$SOCK"

# 제자리 좌회전: +0.2 rad/s, 3초
"$CTL" manual "$SOCK" 0 0.2 3000
"$CTL" stop "$SOCK"

# 정지 명령은 언제든 별도로 실행 가능
"$CTL" stop "$SOCK"
```

모두 한꺼번에 붙여넣지 말고 한 동작씩 확인한다.
터미널 A의 `left(M2)`/`right(M1)`에서 command와 speed가 따라가는지, count가 변하는지 본다.
전진 명령에서는 두 출력축이 각각 로봇 전진 방향으로 회전해야 한다.
정지 명령이 누락돼도 마지막 새 주행 명령 후 150ms에 MCU 명령 lease가 만료된다.
실제 모터 정지 지연은 드라이버 응답과 기계 관성에 따라 달라진다.
벤치를 끝낼 때 터미널 B에서 STOP, 터미널 A에서 Ctrl-C를 실행한다.

현재 코드는 이 절차를 위해 작성한 상태이며, 에이전트가 새 업로드/벤치 코드를 실기 검증하지 않았다.

## 6. 선속도 0.03 m/s로 계속 주행하고 Ctrl+C로 정지

위 터미널 A의 `motor_bench`를 유지하고, 별도 Pi SSH 터미널에서 실행한다.

```bash
bash ~/LOONAR/platforms/loonar/tools/drive-forward.sh
```

각속도는 0 rad/s이고 주행 명령은 50ms마다 갱신한다. 이 스크립트를 실행한
터미널에서 Ctrl+C를 누르면 주행 명령 프로세스를 먼저 종료한 뒤 게이트웨이에
STOP을 전송한다. SIGTERM/SIGHUP과 명령 실행 오류로 종료될 때에도 STOP을 시도한다.
출력의 전송 완료는 게이트웨이 소켓에 명령을 보냈다는 뜻이며 실제 정지는 터미널 A의 피드백으로 확인한다.
강제 종료(SIGKILL)나 전원 차단에서는 스크립트가 STOP을 보낼 수 없으며 기존 MCU 명령 만료가 적용된다.

## 사용 도구 근거

- [TyTools의 장치 tag 지정과 기본 software reboot 업로드](https://github.com/Koromix/tytools/tree/v0.9.8#using-tycmd)
- [PJRC CLI 설명: 기본 soft reboot의 첫 장치 선택 동작](https://www.pjrc.com/teensy/loader_cli.html)
