# LOONAR Pi 사전 준비와 하드웨어 검증 순서

현재 장비의 실제 설치·빌드 결과는 [2026-09-18 준비 기록](preparation-20260918.md)에 있다.

대상: `loonar@10.42.0.103`, Raspberry Pi 5, Ubuntu 24.04 arm64, ROS 2 Jazzy.
암호는 소스/설정 파일에 저장하지 않는다. 이번 단계에서는 설치와 컴파일만 하고
테스트·센서 열거·촬영·통신 프로브·펌웨어 업로드·로버 서비스 실행을 하지 않는다.

## 설치/빌드 재현

APT 패키지 전체 목록은 [apt-packages.txt](apt-packages.txt)다.
이미 `~/LOONAR` 소스가 있는 Pi에서 다음 명령으로 설치한다.

```bash
cd ~/LOONAR
sudo bash platforms/loonar/deploy/install-deps.sh
```

Ubuntu sources에는 `noble`, `noble-updates`, `noble-security` 및 `universe`가
필요하다. 업데이트된 runtime과 오래된 `-dev` 패키지가 충돌하면 강제 downgrade하지
말고 저장소 설정을 복구한다. 이번 Pi는 `noble-updates`가 누락되어 있었으며
`ubuntu.sources.loonar-backup`을 남기고 복구했다. 전체 OS upgrade/재부팅은 하지 않았다.

```bash
cd ~/LOONAR
bash tools/run_gcs_test.sh --build-only --skip-tests --jobs 2
bash platforms/loonar/deploy/build-camera-stack.sh
```

카메라는 RPi libcamera `v0.7.2+rpt20260817` 및 rpicam-apps `v1.13.0`의 정확한
commit을 스크립트에 고정했다. `/usr`의 Ubuntu libcamera를 교체하지 않고
`/opt/loonar/camera-stack/`에 설치한다. 이 빌드 성공만으로 Noble kernel/CSI 호환성이
검증되지는 않는다. 실제 장치 단계에서 확인한다.

rpicam 1.13의 libav encoder는 Noble의 FFmpeg 6.1보다 새 API를 요구하므로 빌드에서
비활성화한다. `rpicam-still`의 사진 취득을 준비하고, 지상국 동영상은 별도의
GStreamer `libcamerasrc → x264enc` 경로를 사용한다. Pi 5에서 `rpicam-vid`의
기본 H.264 인코딩이 된다고 가정하지 않는다.

CubeEye SDK는 [vendor-assets.md](../vendor-assets.md)의 별도 archive를
`~/loonar-staging/cubeeye/`에 풀고 다음을 실행한다.

```bash
bash ~/LOONAR/platforms/loonar/deploy/build-tof-helper.sh
```

SDK의 구형 OpenCV/FFmpeg library path는 helper 자식 프로세스에만 적용한다.
ROS/카메라 서비스의 전역 library path로 등록하지 않는다.

ROS는 중복 이름의 실험 패키지를 포함하지 않고 Pi 최소 EKF 패키지만 빌드한다.

```bash
# rosdep 초기화는 /etc/ros/rosdep/sources.list.d/20-default.list가 없을 때만 실행
test -f /etc/ros/rosdep/sources.list.d/20-default.list || sudo rosdep init
rosdep update --rosdistro jazzy
source /opt/ros/jazzy/setup.bash
rosdep install --from-paths ~/LOONAR/platforms/loonar/ros2/loonar_localization \
  --ignore-src --rosdistro jazzy -y
mkdir -p ~/loonar_jazzy_ws
cd ~/loonar_jazzy_ws
colcon build --base-paths ~/LOONAR/platforms/loonar/ros2/loonar_localization \
  --merge-install --cmake-args -DBUILD_TESTING=OFF
```

완성된 build artifact는 새 release ID로 배치한다. 같은 release를 덮어쓰지 않는다.

```bash
sudo bash ~/LOONAR/platforms/loonar/deploy/install-runtime.sh 20260918-pre-camera
```

설치 파일과 서비스 상태만 기록하려면 다음을 실행한다. 센서/서비스를 시작하지 않는다.

```bash
python3 ~/LOONAR/platforms/loonar/deploy/record-preparation.py
```

설치 위치:

| 경로 | 내용 |
| --- | --- |
| `/opt/loonar/current` | 선택한 release symlink |
| `/opt/loonar/current/bin` | ARM64 gateway/ctl 및 CubeEye helper |
| `/opt/loonar/current/cfs` | cFS core와 app startup/runtime 파일 |
| `/var/lib/loonar/cfs` | cFS writable working directory와 `cf` |
| `/opt/loonar/current/ros/install` | 최소 Jazzy EKF launch/config |
| `/opt/loonar/camera-stack/current` | 전용 libcamera/rpicam |
| `/opt/loonar/vendor/cubeeye/2.5.9/release` | 별도 배치한 ARM64 SDK |
| `/etc/loonar` | 영상/ROS 설정, Control/Payload/ToF 설정 예시 |
| `/home/loonar/loonar-staging` | 설치·빌드 로그와 준비 기록 |

서비스 `vehicle_gatewayd`, `loonar-cfs`, `loonar-localization`, `loonar-video`,
`loonar-tof`와 `loonar-core.target`은 **disabled/inactive**로 설치한다.
`loonar-core.target`을 수동 시작하면 gateway와 cFS만 시작한다.
영상, EKF, ToF는 독립 서비스다. Control/Payload backend와 motion restrict는
구현이 완료되지 않았으므로 존재하는 것처럼 서비스만 만들어 두지 않는다.
처음 설치하는 `cf`만 복사하므로 후속 cFS release 교체 시 startup/app 파일은
기존 상태를 백업하고 별도로 갱신해야 한다.

`loonar` 사용자에 `dialout,video,render,plugdev`를 추가한다. 기존 SSH 세션은
그룹 변경이 바로 반영되지 않으므로 다음 실기 단계 전에 재접속한다.
udev 규칙은 reload만 하고 장치에 강제 trigger하지 않는다.

## 이후 사용자가 실행할 실기 단계 — 이번 작업에서는 실행하지 않음

### 1. 카메라

카메라 연결 후 Pi에서 아래 명령을 순서대로 실행한다. 중간 실패 시 다음 단계로
넘어가지 않고 출력과 kernel 로그를 기록한다.

```bash
loonar-camera rpicam-hello --list-cameras
loonar-camera rpicam-still --nopreview --timeout 2000 -o ~/camera-first.jpg
```

지상국 PC에서 먼저 수신기를 실행한다.

```bash
ffplay -fflags nobuffer -flags low_delay -framedrop 'udp://@:5600'
```

Pi의 `/etc/loonar/video.env`에서 `GROUND_STATION_IP`를 확인한다. 최초 값은
현재 SSH를 접속한 개발 PC의 `10.42.0.1`이며 Pi 자신의 IP가 아니다.
초기 영상은 640×360/30 fps, H.264 약 1 Mbps, MPEG-TS/UDP 5600이다.

```bash
sudo systemctl start loonar-video.service
journalctl -u loonar-video.service -f
# 종료할 때
sudo systemctl stop loonar-video.service
```

합격 조건은 지상국에 실제 새 프레임이 표시되고 손/시계의 움직임을 확인하는 것이다.
패킷 수신만으로 합격 처리하지 않는다. fps/지연/CPU/온도를 기록한 뒤 다음 단계로 간다.
카메라가 열거되지 않으면 케이블 방향, device-tree, kernel/libcamera 조합을 조사한다.
부팅 설정이나 kernel을 사전에 임의 교체하지 않는다.

### 2. Teensy USB

Control의 `teensy41_usb` 환경은 USB `Serial`, 기본 `teensy41`은 기존 `Serial1`을
사용한다. binary wire/CRC는 동일하다. 빌드 명령은 다음과 같으며 업로드는 별도다.

```bash
cd ~/LOONAR/platforms/loonar/firmware/control
pio run -e teensy41_usb
```

빌드된 hex가 있어도 자동 업로드하지 않는다. 연결 후 실제 `/dev/serial/by-id/`를
확인하여 `/etc/loonar/control.env.example`을 복사·수정한다. Payload와 Control은
각각 다른 serial ID로 지정한다. `ttyACM0` 순서에 역할을 고정하지 않는다.
baud 2000000은 USB에서는 line coding이다. Pi HAT 연결 시 물리 baud로 맞춘다.
호스트가 USB CDC 포트를 열 때 DTR을 올려야 Teensy의 status TX가 활성화된다.

먼저 비구동 상태에서 수신, CRC, health timeout, 분리/재연결을 확인해야 한다.
Pi backend와 실측 encoder/IMU telemetry가 아직 구현되지 않았으므로 USB enumerate나
firmware compile 성공을 cFS↔MCU/odom 완료로 해석하지 않는다.
`controller_tbd`의 출력은 현재 항상 0이다.

### 3. 라이다/ToF

현재 확보된 드라이버는 CubeEye I200DK용이다. 별도 라이다를 의미한다면 모델과
인터페이스 확정 후 그 드라이버를 추가한다. 장착 실측값을 `/etc/loonar/tof.env`에
입력하기 전에는 ToF 서비스를 시작하지 않는다. 기존 LIMO의 mount offset을 복사하지 않는다.
XYZ 수신 → ROS 점군/timestamp → 분리/재연결 순서로 확인한다.

### 4. 모터 및 주행 / 전체 파이프라인

Control backend, encoder/BNO085 측정, 실제 제어기와 health/motion freshness 보호,
실측 TF, motion restrict 실행기를 먼저 완성해야 한다. EKF에는 명령 속도가 아닌
실측 `/wheel/odom` vx와 `/imu/data` gyro-z만 입력한다.
최소 EKF의 서비스 설치는 실제 odom 입력을 만들어 주지 않는다.

이후 비구동 MCU 확인 → 최소 구동 → 정지/직진/회전/취소 →
cFS 지상국 상태와 독립 영상 동시 운용을 검증한다.
[포팅 계획의 acceptance 항목](../porting/limo_to_loonar_plan.md)을 사용하고
실행 시각, 로그, rosbag, 영상, PASS/FAIL을 남긴다.
Payload의 `PAYLOAD_EXEC` MID 이후 앱/transport는 여전히 별도 구현 대상이다.
