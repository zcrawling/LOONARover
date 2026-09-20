# LOONAR 지상국 실행: 사용자 실기 검증용

현재 사용자가 Control Teensy 업로드와 게이트웨이 주행 성공을 확인했다.
이 절차는 그 경로에 cFS GroundLink와 실제 지상국을 연결한다.
에이전트는 Pi 접속, MCU 업로드, 실기 주행을 실행하지 않았다.

```text
PC 브라우저 → GCS 실제 백엔드 → TCP 7443 → Pi cFS → gateway → Control Teensy → RoboClaw
PC 상태 화면 ← GCS 실제 백엔드 ← cFS ← gateway 측정값 / MCU health
PC ffplay ← UDP 5600 H.264/MPEG-TS ← Pi 카메라 (독립 경로)
```

## 1. PC에서 소스 전달 (이번 변경 반영 시 한 번)

Pi 주소는 최근 확인된 `192.168.0.99`다. 바뀌었으면 아래 두 명령에서 수정한다.
`build/loonar-ground-control.tar.gz`는 이번 변경을 포함한 소스 묶음이다.
Pi의 기존 registry, 빌드 캐시, 카메라 설치를 지우지 않는다.

```bash
scp /home/sb/LOONAR/build/loonar-ground-control.tar.gz loonar@192.168.0.99:~/
ssh loonar@192.168.0.99
```

## 2. Pi에서 갱신 및 준비 (이번 변경 반영 시 한 번)

기존 `motor_bench`, `drive-forward.sh`는 먼저 종료한다. 같은 USB를 두 프로세스가 사용하지 않는다.

```bash
tar -xzf ~/loonar-ground-control.tar.gz -C ~/LOONAR
cd ~/LOONAR
bash platforms/loonar/deploy/prepare-ground-control.sh
```

이 단계는 **Pi용 gateway와 cFS 앱만 빌드**한다. Teensy 빌드/업로드, 모터 명령,
서비스 시작, 카메라 촬영은 없다. 기존 NASA cFS 소스/빌드 캐시를 재사용한다.
첫 cFS 준비라면 소스 다운로드가 필요하다. 빌드 로그: `~/LOONAR/build/gcs-test/build.log`.
이미 구축한 Pi에는 필요한 CMake/GCC/Python이 설치돼 있다.

## 3. 매번 Pi에서 실행: 지상국 지원

```bash
bash ~/LOONAR/platforms/loonar/tools/start-ground-support.sh
```

이 스크립트는 빌드하지 않는다. 새 cFS, gateway, Control backend를 실행하고,
IMU/모터 표본을 계속 수신하면서 health를 cFS로 전달한다. 부팅 자동 시작은 설정하지 않는다.
기존 `~/loonar-motor-bench/control.json`의 실제 UID·USB 경로·차체 값을 사용한다.
시작만으로 주행 명령을 보내지 않는다. `health`의 `online: true`와 모터 피드백을 확인한다.
로그는 `~/loonar-motor-bench/runtime/{gateway,cfs,backend}.log`에 있다.

영상까지 함께 보려면 위 명령 대신, **지상국 PC에서 접속한 Pi SSH 터미널**에서 실행한다.

```bash
bash ~/LOONAR/platforms/loonar/tools/start-ground-support.sh --video
```

SSH 접속 PC 주소를 영상 목적지로 자동 사용한다. 다른 PC로 보내려면 `--video-ip 192.168.0.X`를 쓴다.
기존 `loonar-video.service`가 실행 중이면 먼저 사용자가 중지한다.
영상 설정은 runtime 폴더에 만들며 `/etc/loonar/video.env`는 변경하지 않는다.
카메라 장착 방향 보정은 PC의 LOONAR 영상 수신기가 반시계 방향 90°로 적용한다.
Pi의 원본 스트림은 변경하지 않는다. 따라서 Pi 재빌드나 재배포는 필요 없다.
보정 전 영상 창이 열려 있으면 닫은 뒤 LOONAR 지상국을 다시 실행한다.
영상 창만 실행하려면 PC에서 `bash GCS/scripts/start_video.sh --rotate-left`를 사용한다.

## 4. 매번 개발 PC에서 실행: 실제 지상국

```bash
cd /home/sb/LOONAR
bash GCS/scripts/start_loonar_gcs.sh 192.168.0.99
```

브라우저 `http://127.0.0.1:8080`, 진단 창, 영상 수신 창을 연다. PC에는 Python 3.11 이상,
ffplay, gnome-terminal, xdg-open이 필요하며 현재 개발 PC에 존재함을 확인했다.
Python pip 패키지는 필요 없다. 이미 이전 GCS가 실행 중이면 종료한 뒤 다시 시작한다.
브라우저가 자동으로 열리지 않으면 위 주소를 직접 연다.

초기값은 `GCS/config/loonar.toml`의 선속도 **0.03 m/s**, 각속도 **0.2 rad/s**, 갱신 주기 **50ms**다.
화면에서 바꾸는 선속도는 실제로 전송되는 값이다.

| 입력 | 동작 |
| --- | --- |
| ↑ / ↓ | 전진 / 후진 |
| ← / → | 좌회전 / 우회전 |
| 방향키 해제 / 창 포커스 해제 | MANUAL 속도 0 전송 |
| STOP 버튼 | 명시적인 STOP 모드 요청 |

STOP 버튼으로 먼저 정지한 후 PC 지상국을 Ctrl+C로 종료한다.
Pi 지원 터미널도 Ctrl+C로 종료하면 Control backend가 STOP을 보내고 시작한 프로세스를 정리한다.
PC 웹 서버 종료만으로 STOP 전송을 보장하지 않으며, MCU의 기존 명령 만료는 별도로 동작한다.

## 사용자 확인 항목

- 상단 `REAL ROVER / 192.168.0.99`, `CONNECTED`, 증가하는 RX.
- Control MCU `ONLINE`, UID 및 온도 표시. 미연결 Payload는 `OFFLINE`.
- STOP 결과 `Forwarded`, 로버 모드 `STOP`. `Forwarded`는 cFS가 gateway로 전달했다는 뜻이며 실제 모터 정지 완료를 뜻하지 않는다.
- 방향키를 누를 때 실제 구동과 측정 선속도·각속도 변화. 키를 놓았을 때 정지.
- 모터 측정값이 유효할 때 배터리 전압과 선속도·각속도 표시.
- 옵션 영상은 별도 ffplay 창에서 실제 새 프레임이 보이는지 확인.

현재 지원 스크립트는 ROS EKF/ToF를 시작하지 않는다. 자세·위치·IMU 각도·배터리 잔량은
입력이 없으면 `—`다. Payload 센서 및 reaction 명령은 이번 주행 검증 범위에 포함하지 않는다.
같은 TCP 7443에 CLI 모니터나 다른 GCS를 동시에 연결하지 않는다.

기존 `GCS/scripts/start_rover.sh` / `rover_start_remote.sh`와 REMOTE 로버 시작 아이콘은
LIMO/Humble용이다. LOONAR에서는 이 문서의 `start-ground-support.sh`를 사용한다.
TCP 7443과 UDP 5600이 통과하는 동일 네트워크가 필요하다. 방화벽/AP 클라이언트 격리는 자동 변경하지 않는다.

## 로컬 소프트웨어 검증

GCS 파서/백엔드/런처 회귀 테스트와 실제 PC용 cFS·gateway를 이용한 로컬 통신을 검증한다.
로컬 통신의 MCU health와 차량 측정값은 합성 입력이며 실제 MCU·카메라·모터 검증과 구분한다.
Pi ARM64 빌드 및 무선 링크 실기 결과는 사용자가 위 절차로 확인해야 한다.

이번 로컬 검증: GCS 테스트 34개 중 33개 통과, 설치하지 않은 선택적 REMOTE 데스크톱
아이콘 검사 1개 skip. 실제 cFS/gateway에서 FORWARD(0.03, 0), STOP 전달 및
MCU2 양쪽 역할·유효 전압/속도·미제공 필드의 왕복 디코딩을 확인했다.
