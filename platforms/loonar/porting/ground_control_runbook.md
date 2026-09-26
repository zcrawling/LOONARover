# LOONAR 지상국 실행: 사용자 실기 검증용

현재 사용자가 Control Teensy 업로드와 게이트웨이 주행 성공을 확인했다.
이 절차는 그 경로에 cFS GroundLink와 실제 지상국을 연결한다.
에이전트는 Pi 접속, MCU 업로드, 실기 주행을 실행하지 않았다.

```text
PC 브라우저 → GCS 실제 백엔드 → TCP 7443 → Pi cFS → gateway → Control Teensy → RoboClaw
PC 상태 화면 ← GCS 실제 백엔드 ← cFS ← gateway 측정값 / MCU health
PC ffplay ← UDP 5600 H.264/MPEG-TS ← Pi 카메라 (독립 경로)
```

## 2026-09-21 수동 기록·배터리 전압 변경 적용

현재 변경은 로컬 소스에 반영했다. Pi 전원이 꺼져 있어 배포/실제 bag 기록은 수행하지 않았다.
기존 지상국 주행이 준비된 Pi에는 아래 Python/스크립트 묶음만 적용하면 된다.
이번 기록·전압 표시 변경에는 cFS 재빌드나 MCU 펌웨어 교체가 필요하지 않다.

PC에서 `LOONAR_IP`를 현재 주소로 바꿔 실행한다.

```bash
PI=loonar@LOONAR_IP
scp /home/sb/LOONAR/build/loonar-recording-update.tar.gz "$PI":~/
ssh "$PI"
```

Pi에서 기존 지원 스크립트가 종료된 상태로 적용한다.

```bash
tar -xzf ~/loonar-recording-update.tar.gz -C ~/LOONAR
bash ~/LOONAR/platforms/loonar/tools/start-ground-support.sh
```

이 실행은 ROS 토픽을 발행하지만 저장하지 않는다. 아래 “별도 명령으로 주행 ROS 데이터 저장”
절차를 다른 Pi 터미널에서 실행해야 bag이 생성된다. PC 지상국은 웹페이지를 새로고침하면
업데이트한 전압 요약을 표시한다. ROS 2 Jazzy와 MCAP 플러그인은 기존 apt 목록에 포함되어 있다.

로컬 검증: MCU/Pi 단위 테스트 18개, 지상국 MCU/전압 테스트 6개, JS 조작/전압 표시 테스트 3개 통과.
이 PC는 Python 3.14와 Jazzy의 Python 3.12 모듈이 맞지 않아 실제 ROS→MCAP 기록 시험은 실행하지 못했다.
Pi에서 기록 후 `ros2 bag info`로 토픽·메시지 수를 확인해야 한다.

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
MCU 표본은 별도의 ROS publisher에도 전달한다. `/imu/*`, `/wheel/odom`,
`/battery_state`가 발행되며 직렬 포트는 기존 backend만 소유한다.
**rosbag은 자동으로 기록하지 않는다.** 저장은 아래 별도 명령으로만 시작한다.
기존 `~/loonar-motor-bench/control.json`의 실제 UID·USB 경로·차체 값을 사용한다.
시작만으로 주행 명령을 보내지 않는다. `health`의 `online: true`와 모터 피드백을 확인한다.
로그는 `~/loonar-motor-bench/runtime/{gateway,cfs,backend}.log`에 있다.
ROS 발행 로그는 같은 폴더의 `sensors.log`다. ROS publisher 실패는 보고하며 주행을 중단하지 않는다.

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

### PC에 카메라 영상 녹화 (선택)

기존 영상 창을 닫고 **PC 터미널**에서 아래 명령을 실행한다. 로버 변경은 필요 없다.

```bash
bash /home/sb/LOONAR/GCS/scripts/start_video.sh --rotate-left --record
```

UDP 수신 영상을 화면에 표시하면서 PC의 `~/Videos/LOONAR/camera_날짜_시간.ts`에 저장한다.
영상 창을 닫거나 Ctrl+C를 누르면 녹화가 끝난다. `--record`가 없으면 저장하지 않는다.
재인코딩 없이 수신한 H.264를 MPEG-TS 파일에 저장하므로 저장 영상은 카메라 원본 방향이다.
녹화 파일도 보정해서 보려면 `ffplay -vf transpose=cclock 파일.ts`로 재생한다.
저장 경로는 `LOONAR_VIDEO_DIR=/원하는/경로` 환경변수로 변경할 수 있다.
이 파일은 rosbag과 별개이며 UDP에서 수신하지 못한 프레임은 복구할 수 없다.

### 카메라 바깥 테두리의 상대 방위

`start_gcs.sh`는 이제 `--record --compass`를 전달한다. 영상 픽셀 위에 글자를 덮지 않고,
별도 테두리에서 N/E/S/W가 회전각에 따라 연속적으로 이동한다. 시작 방향은 N, 오른쪽은 E다.
좌회전하면 N은 화면 오른쪽으로 이동한다. 이것은 영상을 둘러싼 평면 나침반이며
각 문자가 카메라의 시야 안에 있다는 뜻은 아니다. 녹화 파일에는 원본 영상만 들어간다.

센서 +Y축을 전방으로 사용한다. 시작 시 SH2_GRAVITY로 위쪽과 초기 수평면을 정하고,
SH2_GYROSCOPE_CALIBRATED의 X/Y/Z(rad/s)를 센서 시각에 따라 quaternion으로 적분한다.
자기장이나 자기 북쪽 기준 rotation vector는 이 표시 계산에 사용하지 않는다.
정지 상태에서 시작하고 첫 방위 문자가 표시된 뒤 주행한다. 자이로 적분 오차는 시간이 지나면 누적된다.
`R` 또는 `Set start=N`으로 현재 방향을 새 기준으로 잡을 수 있다.
IMU 수신 중단 시 문자는 숨겨진다. 자이로 누락/재시작으로 적분 연속성을 잃으면 재초기화 후 새 기준을 잡는다.
이 처리는 표시용이며 주행 명령·PID·정지 조건을 변경하지 않는다.

PC 의존성은 `ffmpeg`, `/usr/bin/python3`, `python3-tk`, `python3-pil`, `python3-pil.imagetk`다.
현재 PC에서는 확인되었다. 별도 실행은 다음과 같다.

```bash
bash /home/sb/LOONAR/GCS/scripts/start_video.sh --rotate-left --record --compass
```

현재 Teensy 펌웨어는 필요한 gyro/gravity 표본을 이미 전송한다. Pi에는 다음 **두 Python 파일**을
반영하고 support를 재시작해야 한다. Teensy 업로드와 cFS/gateway 재빌드는 필요 없다.
아직 배포하지 않은 Pi는 IMU 대기 표시만 보인다.

```bash
# PC에서, 아래 주소는 현재 접속 가능한 Pi 주소로 지정
PI=loonar@10.42.0.103
scp /home/sb/LOONAR/platforms/loonar/tools/mcu_v2/backend.py \
    /home/sb/LOONAR/platforms/loonar/tools/mcu_v2/gyro_attitude.py \
    "$PI":~/LOONAR/platforms/loonar/tools/mcu_v2/
```

기존 VEHICLE_STATUS 92바이트를 그대로 사용한다. IMU 유효 비트 4와 함께 비트 5를 세워
gyro 상대 자세임을 표시하고 기존 roll/pitch/yaw 필드에 rad 단위로 전달한다.
PC는 지상국의 로컬 상태 API를 읽으므로 로버 TCP 연결이나 UDP 영상 수신을 중복 생성하지 않는다.

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
화면에서 바꾸는 선속도와 각속도는 실제로 전송되는 값이다.
각속도 슬라이더는 **0.01~1.00 rad/s**, 간격 **0.01 rad/s**이며 좌·우 회전에 적용된다.
슬라이더 또는 마우스 휠로 변경하며, 회전 키를 누르는 중 변경하면 다음 명령부터 적용된다.
슬라이더에 초점이 있을 때 방향키는 값 조절에 쓰인다. 주행하려면 화면의 빈 곳을 클릭해 초점을 해제한다.
새로고침하면 설정 파일의 초기값을 다시 읽는다. 이 기능은 PC의 GCS만 업데이트하고 재시작하면 되며 로버 변경은 필요 없다.

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

## 별도 명령으로 주행 ROS 데이터 저장 (LOONAR에서만)

위 지원 스크립트를 실행한 상태에서 **다른 Pi SSH 터미널**에서 시작한다.
PC 지상국 실행이나 로버 지원 스크립트 시작만으로 기록을 시작하지 않는다.

```bash
bash ~/LOONAR/platforms/loonar/tools/record-drive.sh
```

저장 위치는 **Pi의 `/home/loonar/loonar-bags/drive_날짜_시각/`**, 형식은 MCAP이다.
PC로 복사·업로드하는 동작은 없다. 모든 발견되는 ROS 토픽을 기록하며,
파일당 1 GiB에서 다음 파일로 나눠 계속 기록한다. Ctrl+C로 기록을 종료하고 metadata를 마무리한다.
주행 종료와 기록 종료는 독립적이다. 두 터미널을 각각 종료한다.

저장 폴더를 지정할 수도 있다. 이미 존재하는 bag 폴더 이름은 새 이름으로 바꾼다.

```bash
bash ~/LOONAR/platforms/loonar/tools/record-drive.sh ~/loonar-bags/trial01
```

MCU가 연결되어 있으면 `/imu/data`, `/imu/accel`, `/imu/orientation_raw`,
`/imu/magnetic_field`, `/imu/linear_acceleration`, `/imu/gravity`, `/wheel/odom`,
`/battery_state`를 기록할 수 있다. **ToF와 EKF는 해당 노드가 별도로 실행 중일 때만** 기록된다.
ToF가 필요하면 기존 `loonar-tof.service`를 시작한 뒤 해당 토픽 수신을 확인한다.
카메라의 독립 UDP 영상은 ROS 토픽이 아니므로 이 bag에 포함되지 않는다.
Gateway 명령 역시 자동으로 `/cmd_vel` 토픽이 되지는 않는다.
기존 ToF 전용 `record-tof.sh` / `loonar-tof-record.service`와 동시에 기록할 필요는 없다.

기록을 종료한 뒤 Pi에서 실제 포함 토픽과 메시지 수를 확인한다.

```bash
source /opt/ros/jazzy/setup.bash
ros2 bag info ~/loonar-bags/trial01
```

## RoboClaw 배터리 전압

전송 경로는 이미 구현되어 있다: RoboClaw main battery 조회(command 24) → MCU motor sample →
Pi gateway status → cFS vehicle/ground link → GCS 차량 상태. 응답의 0.1 V 단위를 Pi에서 V로 변환한다.
별도의 MCU 펌웨어나 cFS 변경 없이, 유효한 조회값이 있으면 지상국에 전달된다.

웹 상단 배터리 요약은 실기 차량 전압을 `16.7 V`처럼 표시한다. 유효 전압이 없으면 `—`다.
배터리 잔량 %는 전압에서 임의로 추정하지 않는다. ROS `/battery_state`에도 같은 main voltage를
발행하며 미제공 percentage/current/용량 등은 NaN(미측정)으로 둔다.
값은 RoboClaw 전원 단자에서 측정한 전압이며 별도 BMS의 잔량 측정값이 아니다.

## 로컬 소프트웨어 검증

GCS 파서/백엔드/런처 회귀 테스트와 실제 PC용 cFS·gateway를 이용한 로컬 통신을 검증한다.
로컬 통신의 MCU health와 차량 측정값은 합성 입력이며 실제 MCU·카메라·모터 검증과 구분한다.
Pi ARM64 빌드 및 무선 링크 실기 결과는 사용자가 위 절차로 확인해야 한다.

이번 로컬 검증: GCS 테스트 34개 중 33개 통과, 설치하지 않은 선택적 REMOTE 데스크톱
아이콘 검사 1개 skip. 실제 cFS/gateway에서 FORWARD(0.03, 0), STOP 전달 및
MCU2 양쪽 역할·유효 전압/속도·미제공 필드의 왕복 디코딩을 확인했다.
