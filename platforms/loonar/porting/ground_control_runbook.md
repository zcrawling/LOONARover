# Pi 지원 프로그램 실행

Pi는 `~/LOONAR`에 현재 소스, gateway/cFS 빌드 결과와 장치 registry가 있어야 한다.
최초 설치는 [배포 안내](../deploy/README.md), 펌웨어는
[Control 빌드·업로드](../firmware/control/README.md)를 따른다.

## 빌드와 장치 등록

Pi에서 gateway와 cFS를 빌드한다. MCU를 업로드하거나 주행시키지 않는다.

```bash
cd ~/LOONAR
bash platforms/loonar/deploy/prepare-ground-control.sh
```

`~/loonar-motor-bench/control.json`에는 연결된 MCU UID, bound UID,
USB by-id 경로와 차체 설정이 맞아야 한다.
[registry 예제](../config/mcu-registry.example.json)와
[장치 조회 도구](../tools/mcu_v2/inspect.py)를 참고한다.
`MCU UID/binding does not match role registry`는 실제 보드·펌웨어 binding·registry
불일치다. 식별 검사를 우회하지 말고 대상 보드와 빌드 UID를 확인한다.

## 실행

### 지상국 하드웨어 모니터

`GCS/scripts/start_loonar_gcs.sh PI_IP` 실행 시 별도 하드웨어 터미널을 자동으로 연다.
이미 지상국을 실행 중이면 PC에서 다음 명령으로 모니터만 열 수 있다.

```bash
gnome-terminal --geometry=100x24 -- bash /home/sb/LOONAR/GCS/scripts/start_hardware_monitor.sh --host 10.254.254.3
```

SSH `loonar` 계정으로 약 1초마다 `vcgencmd measure_temp`, `pmic_read_adc EXT5V_V`,
`get_throttled`, `/proc/net/wireless`와 MCU 상태 파일을 읽는다.
기본 비밀번호는 기존 로버 설정 `loonar`이며 `LOONAR_SSH_PASSWORD`로 바꿀 수 있다.
sshpass가 없으면 SSH 키 인증을 사용한다. 모니터는 MCU 포트를 열지 않는다.

- `EXT5V_V`는 Pi PMIC ADC가 측정한 입력 전압이다. 별도 외장 ADC 측정값은 아니다.
- PMIC는 입력 전압만 조회한다. 내부 레일별 전압·전류 목록은 수집하거나 표시하지 않는다.
- 배터리 전압과 드라이버 온도는 기존 RoboClaw MOTOR 표본의 유효 비트를 확인한다.
  RoboClaw 온도는 모터 본체 온도가 아니다. 모터 본체에는 별도 온도 센서가 필요하다.
- Control/Payload 시리얼 소유 프로세스가 `/tmp/loonar-monitor-UID/{control,payload}.json`을
  작업 스레드에서 기록한다. TX는 쓰기 완료, RX는 수신 바이트 시각이며 명령 ACK와 다르다.
  절대 시각은 Pi 시스템 시간, 경과 시간과 만료 판단은 Pi monotonic 시계 기준이다.
- 3초 이상 상태 파일 갱신이 없거나 SSH 수신이 4초 이상 지연되면 오래된 온도/전압을 숨긴다.
  마지막 송수신 시각은 유지하며 경과 시간을 계속 증가시킨다.
- Payload MCU 내부 온도는 최신 payload 펌웨어가 필요하다. 구형 펌웨어도 통신 가능하며
  내부 온도만 미지원으로 표시한다. Control 펌웨어 재업로드는 필요 없다.

Pi backend/service 수정 후 기존 ground-support를 종료하고 다시 실행한다.
systemd 배포에서는 `install-runtime.sh`로 새 Python 모듈과 payload 서비스 환경도 반영한다.
웹 UI의 Pi CPU 및 Control MCU 온도 카드는 제거했으며 별도 터미널에서 확인한다.

### Pi 실행

지상국 PC에서 접속한 SSH 터미널에서:

```bash
ssh loonar@192.168.0.14
bash ~/LOONAR/platforms/loonar/tools/start-ground-support.sh --video
```

`--video`는 첫 번째 인자로 주며 SSH 접속 PC로 송신한다.
영상 목적지를 직접 지정할 수도 있다.

```bash
bash ~/LOONAR/platforms/loonar/tools/start-ground-support.sh --video-ip 192.168.0.20
```

| 인자 | 효과 / 저장 위치 |
| --- | --- |
| 없음 | gateway, cFS, Control backend, ROS 표본 발행 |
| `--encoder-verify` | 명령/엔코더 비교, `~/loonar-motor-bench/runtime/encoder-*.csv` |
| `--record` | 이미 발행 중인 ROS 토픽만 MCAP bag으로 저장, `~/loonar-bags/` |
| `--record-all` | ToF·카메라 ROS를 함께 시작하고 IMU·모터 전체 피드백과 MCAP 저장 |
| `--bag-dir /경로` | bag 상위 디렉터리 변경. 기본값 `~/loonar-bags` |
| `--bag-camera-fps 10` | bag 카메라 JPEG 발행률 변경(1~30, 기본 30). 송신 영상은 30fps 유지 |
| `--record-video` | Pi 로컬 카메라 H.264/MPEG-TS, `~/loonar-videos/` |
| `--video-record-dir /경로` | Pi 영상 저장 디렉터리 변경 |

```bash
bash ~/LOONAR/platforms/loonar/tools/start-ground-support.sh --video --encoder-verify --record --record-video
```

ROS 기록에는 Jazzy와 MCAP 의존성이 필요하다. 영상 녹화만 필요하면
`--record-video`만 추가한다. Pi 영상 기본 프로필은 low(640×360, 30fps, 1Mbps)다.
영상은 UDP 송신·파일 저장에 같은 인코더를 사용한다. 부하로 인한 프레임 누락을
완전히 막는 무손실 녹화는 아니다.

시작만으로 주행 명령은 전송하지 않는다. `health online: true`와 최신 motor/imu
표본을 확인한 뒤 [PC 지상국](../../../GCS/README.md)을 실행한다.
`--encoder-verify`는 피드백 기록 옵션이며 IMU 제외 진단 펌웨어를 강제하지 않는다.

## ToF·카메라·IMU·모터 통합 기록

Pi에서 실행한다. 펌웨어 재빌드/업로드는 필요하지 않으며, 기존 MCU의 IMU·모터
패킷과 설치된 CubeEye 수신기를 사용한다.

```bash
# 지상국 영상 송신 + 네 종류 센서 기록 (SSH 접속 PC로 영상 송신)
bash ~/LOONAR/platforms/loonar/tools/start-ground-support.sh --video --record-all

# 지상국 영상 송신 없이 Pi 로컬에만 기록
bash ~/LOONAR/platforms/loonar/tools/start-ground-support.sh --record-all
```

둘 중 하나만 실행한다. `--record`나 `--record-video`를 함께 넣을 필요는 없다.
별도 H.264 TS 파일도 원할 때만 `--record-video`를 추가한다.
카메라는 한 번만 열고 기존 H.264 송신 경로에서 JPEG 기록 분기를 나눈다.
객체인식 모델이나 ultralytics 설치는 기록에 필요하지 않다.
기존 `loonar-video.service`가 실행 중이면 중지 후 시작한다.
`loonar-tof.service`가 이미 active이면 재사용하고, 아니면 ToF를 자식 프로세스로 시작한다.
재사용한 서비스는 종료 시 그대로 두며 직접 시작한 프로세스는 함께 종료한다.

| 데이터 | bag 토픽 / 형식 |
| --- | --- |
| ToF XYZ | `/tof/depth/points` — PointCloud2, `/tof/status` — SDK 시각 등 메타데이터 |
| 카메라 | `/camera/image_raw/compressed` — CompressedImage JPEG, 기본 640×360 30fps / `/camera/timing` |
| IMU | `/imu/data` 자이로, `/imu/accel`, `/imu/orientation_raw`, 그 외 실제 발행 중인 `/imu/*` |
| 모터 전체 피드백 | `/motor/feedback` — DiagnosticArray, `status[0].values`에 좌/우 명령·엔코더 count·qpps·전류(A)·PWM(raw)·전압(V)·온도(°C)·오류·valid·age |
| MCU 원본 | `/mcu/control/raw` — JSON String, 원본 payload hex와 MCU 시각·Pi 시각·동기화 offset/RTT |
| 계산값 / 기록 상태 | `/wheel/odom`, `/battery_state`, `/recording/status`, 실제 발행 중인 TF 등 |

좌측=M2, 우측=M1이다. 모터 전류는 배터리 입력 전류가 아니다.
센서 상태가 유효하지 않아도 raw/모터 snapshot은 남기며 valid 필드로 구분한다.
늦게 도착한 MCU 데이터도 원본에 저장하지만 200ms를 넘은 데이터는 기존 live IMU/odom에 넣지 않는다.

### 시각의 의미

- 공통 기준은 **Pi CLOCK_REALTIME(Unix ns)**. 각 메시지의 `header.stamp`를 기준으로 비교한다.
- MCU: `mcu_stamp_us × 1000 + clock_offset_ns`. 원본 JSON에 이 값과 동기화 왕복시간
  `sync_rtt_ns`를 보존한다. 통신 비대칭·센서 내부 지연까지 제거하는 동기화는 아니다.
- ToF: Pi SDK callback 시각. 장치 timestamp는 `/tof/status`에 보존한다.
- 카메라: GStreamer PTS와 파이프라인 clock을 Pi 시각으로 변환한다. JPEG 처리/큐 지연을
  차감하며 원본 PTS·지연·수신 시각을 `/camera/timing`에 남긴다. PTS가 유효하지 않으면
  `PI_RECEIVE_FALLBACK`으로 표시한다. 검증된 노출 시각이나 하드웨어 trigger 동기화는 아니다.
- 모터는 여러 UART 질의 결과의 캐시 snapshot이다. count/speed의 실제 나이는
  `count_age_ms`/`speed_age_ms`에 있고 `/wheel/odom`은 speed age를 차감한다.
  전류 등 다른 항목은 개별 age가 기존 프로토콜에 없으며 valid만으로 500ms 미만인지 확인한다.
- bag 자체의 기록 시각은 recorder 수신 시각이다. 분석 시 메시지 header 또는 JSON의
  `stamp_ns`를 사용한다. 모든 센서에 강제로 같은 시각을 덮어쓰지 않는다.

### 저장 확인과 제한

터미널에서 `MCAP output: /home/loonar/loonar-bags/drive_...` 경로를 출력한다.
`RECORD streams=OK recorder=RUNNING`은 센서 데이터의 최신성 및 프로세스 실행 상태이다.
`MISSING/STALE`이면 해당 토픽에 데이터가 없거나 오래됐거나 모터 valid가 불완전한 상태다.
기록 실패·센서 누락을 표시하면서 나머지 데이터와 제어는 계속 동작한다.

```bash
cat ~/loonar-motor-bench/runtime/recording-status.json
tail -n 30 ~/loonar-motor-bench/runtime/record.log
# GCS STOP 후 support 터미널에서 Ctrl+C, 종료 완료 후 실제 출력된 폴더 확인
source /opt/ros/jazzy/setup.bash
ros2 bag info ~/loonar-bags/drive_실제폴더명
```

Pi의 홈 파일시스템에 MCAP과 metadata.yaml을 저장하고 약 1GiB마다 분할한다.
여유 공간이 1GiB 미만이면 `LOW DISK`를 표시한다. 자동 삭제·전체 용량 제한은 없다.
ToF는 `/etc/loonar/tof.env`의 Hz/stride와 기존 유효점 필터를 그대로 따른다.
기존 전체 공간해상도 ToF 시험은 약 52GiB/h였으므로 카메라까지 저장할 공간을 확보한다.
raw depth/amplitude 이미지나 SDK의 모든 시간 프레임까지 보존하는 것은 아니다.
카메라 분기는 큐를 제한하므로 부하가 높으면 프레임이 누락될 수 있다.
`/camera/timing`의 published_frames, 기록 상태 count와 bag 메시지 수를 함께 확인한다.
`streams=OK`만으로 무손실 저장이 증명되는 것은 아니다.

새 Pi에서 카메라 ROS 바인딩/MCAP이 없으면 설치한다(기존 Jazzy·CubeEye·카메라 런타임 필요).

```bash
sudo apt install python3-gi gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 \
  gstreamer1.0-plugins-good ros-jazzy-diagnostic-msgs ros-jazzy-rosbag2-storage-mcap
```

노트북의 변경사항만 Pi 체크아웃에 복사하려면 support를 종료한 뒤 노트북에서 실행한다.
현재 Pi 주소가 다르면 아래 주소를 바꾼다. 기존 MCU 펌웨어나 registry는 덮어쓰지 않는다.

```bash
cd /home/sb/LOONAR
rsync -avR --exclude=__pycache__ \
  common/video/loonar-video-stream common/video/camera_ros.py \
  platforms/loonar/tools/mcu_v2/ \
  platforms/loonar/tools/run-recording-monitor.sh platforms/loonar/tools/record-drive.sh \
  platforms/loonar/config/tof-bag-qos.yaml \
  platforms/loonar/deploy/run-video.sh platforms/loonar/deploy/run-tof.sh \
  loonar@10.254.254.3:/home/loonar/LOONAR/
```

검증: `tools/tests/recording_smoke.py`는 Jazzy/GStreamer 환경에서 가상 카메라·MCU·ToF를
입력하고 실제 MCAP을 다시 읽어 JPEG, 전류 단위, Pi 시각 변환, 늦은 데이터 보존,
중단된 센서의 stale 감지를 확인한다. 실기 USB 수신·CubeEye SDK·Pi 부하는 별도 검증 대상이다.

## 확인과 종료

- 로그: `~/loonar-motor-bench/runtime/{backend,gateway,cfs,sensors,video,record}.log`
- Pi: GroundLink TCP 7443. PC: 영상 UDP 5600, 웹 localhost TCP 8080.
- `imu`: gyro/accel/quaternion 수신 값. health의 `imu_progress`와 `gyro_age_ms`도 확인한다.
- ROS 표본: `/imu/*`, `/wheel/odom`, `/battery_state`, `/motor/feedback`, `/mcu/control/raw`. 기록 여부는 bag 메시지 수로 확인한다.
- 영상·기록 실패는 해당 로그를 확인한다. core 프로세스 종료는 전체 bench 종료로 이어진다.

GCS STOP 후 Pi 터미널에서 Ctrl+C한다. backend는 STOP을 요청하고 기록 프로세스를
정리한다. 파일 마무리를 위해 종료를 기다린다. 실행 중인 backend와 시리얼 모니터가
같은 USB 장치를 동시에 열면 안 된다.

## Payload와 systemd

Payload 서비스는 기본으로 함께 시작하며 `21147480` 보드의 USB by-id 경로를 사용한다.
미연결 상태에서는 OFFLINE을 보고하고 1초마다 연결을 재시도한다. 주행·영상은 계속 실행된다.
다른 보드는 `--payload-device /dev/serial/by-id/...` 또는 `PAYLOAD_DEVICE` 환경변수로 지정한다.
전체 localization은 별도 실행한다. Payload 설정은 [별도 안내](payload_pca_runbook.md)를 따른다.
checkout bench를 사용할 때 systemd Payload/gateway/cFS/Control을 중복 실행하지 않는다.
`loonar-mcu@control.service`가 없으면 systemd runtime이 설치되지 않은 것이다.
checkout 실행에는 그 unit이 필요하지 않다.

## NeoPixel: BCM GPIO22 / 흰색 / 밝기 30

`platforms/loonar/tools/neopixel.py`는 Pi 5 RP1 PIO 드라이버를 사용한다.
데이터 DIN은 **BCM GPIO22 = 물리 핀 15번**이다. 물리 핀 22번(GPIO25)이 아니다.
RGB WS2812/NeoPixel, GRB 순서, **16개**, 밝기 **30/255**가 기본이다.
흰색의 실제 채널 값은 R=30, G=30, B=30이다.
[사용자가 지정한 제품](https://www.coupang.com/vp/products/7501017272?itemId=19635286527)은
상품명 기준 5V WS2812 RGB **12구** 원형 패널이다. 실제 12구이면 `--count 12`로
맞출 수 있다. 16개 분량을 보내도 체인의 앞 12개는 정상적으로 받는다.
LED 전원은 해당 스트립의 5V 전원에 연결하고 Pi와 GND를 공통으로 연결한다.

### 최초 준비 / 커널 업데이트 후 재빌드

Pi에서 일반 사용자로 실행한다. 개별 시스템 설치 단계에서 sudo를 사용한다.

```bash
bash ~/LOONAR/platforms/loonar/tools/setup-neopixel.sh
```

이 설치기는 **Pi 5 / Ubuntu 6.8.x-raspi 전용**이다. 커널/펌웨어를 교체하거나
재부팅하지 않는다. 커널에 맞는 헤더로 Raspberry Pi upstream의 RP1 mailbox,
firmware, PIO 모듈 세 개를 빌드하고 runtime device-tree overlay를 적용한다.
`/boot/firmware/config.txt`는 수정하지 않는다. 빌드 소스는
`5d39807272da852e10f3fc4467c33b57f59ecc61`로 고정하고 파일별 SHA256을 검증한다.
Upstream GPL 라이선스/저작권 헤더는 다운로드된 소스에 보존한다.
호환 수정은 6.8의 remove_new callback, firmware 초기화 순서의 deferred probe,
runtime overlay의 명시적 PIO id뿐이다. Overlay는 기존 RP1 레지스터 BAR 매핑을
유지하면서 이미 할당된 SRAM BAR 매핑과 mailbox/firmware/PIO 노드를 추가한다.

설치 결과:

- 빌드·원본 소스·manifest: `~/.cache/loonar-neopixel/<kernel>/`
- 모듈: `/lib/modules/<kernel>/updates/loonar-neopixel/`
- Overlay/활성화 스크립트: `/usr/local/lib/loonar-neopixel/`
- 부팅 시 PIO 준비: `loonar-neopixel-pio.service` (system service)
- 장치 권한: `/etc/udev/rules.d/70-loonar-neopixel-pio.rules`, 설치 사용자의 primary group에 rw
- Python 드라이버: `~/.venvs/loonar-neopixel/`에 `Adafruit-Blinka-Raspberry-Pi5-Neopixel==1.0.0rc2`

서비스는 PIO 장치만 준비한다. 부팅할 때 LED를 자동으로 켜지는 않는다.
커널 버전이 바뀌면 새 커널에서 설치기를 다시 실행해 해당 버전의 모듈을 만든다.
6.8 이외의 커널에는 이 backport 설치기를 사용하지 않는다. Native PIO가 있는
환경은 [Adafruit 안내](https://learn.adafruit.com/circuitpython-on-raspberrypi-linux/using-neopixels-on-the-pi-5)를 따른다.

### 실행

일반 `python3`로 실행하면 필요한 경우 설치한 전용 가상환경으로 자동 전환한다.

```bash
# 드라이버/권한/라이브러리 확인 (GPIO 출력 없음)
python3 ~/LOONAR/platforms/loonar/tools/neopixel.py --check

# 모두 흰색으로 켜고 종료: LED는 켜진 상태 유지
python3 ~/LOONAR/platforms/loonar/tools/neopixel.py

# 모두 끄기
python3 ~/LOONAR/platforms/loonar/tools/neopixel.py --off

# 실행 유지, Ctrl+C/SIGTERM 시 끄기
python3 ~/LOONAR/platforms/loonar/tools/neopixel.py --hold
```

`--dry-run`은 GPIO를 열지 않고 핀/밝기/전송량을 출력한다.
`--rgb 255 0 0`, `--brightness 30`, `--count 12`, `--gpio 22`로 설정을 바꿀 수 있다.
`--hold` 실행 중에는 해당 프로세스를 Ctrl+C로 종료해 끈다.
단발 실행도 전송 후 PIO state machine을 해제하므로 반복 실행할 수 있다.

2026-10-16, `6.8.0-1065-raspi`에서 `/dev/pio0` 생성, 사용자 권한 전송을 확인했고,
사용자가 연결한 링의 모든 LED가 흰색으로 켜졌음을 확인했다.

### 주행 모드 자동 LED (부팅 자동 실행)

Pi에 PIO 준비가 끝난 뒤 모드 표시 서비스를 설치한다:

```bash
bash ~/LOONAR/platforms/loonar/tools/setup-mode-led.sh
```

`loonar-mode-led.service`는 부팅 시 흰색으로 시작한다. BCM GPIO22 / 16개 / 밝기
30/255를 유지한다. 다음 주행부터 새로 빌드한 `lnr_ground.so`가 LED 전용 Unix
데이터그램(`/run/loonar-led/status.sock`)으로 모드/지상국 연결을 10Hz 발행한다.
배포 시 cFS `loonar_ground_link`도 재빌드해야 하며 기존 cFS는 재실행 때 반영된다.
LED는 제어 소켓이나 GroundLink TCP 클라이언트에 접속하지 않고 명령을 보내지 않는다.
LED 서비스가 없거나 실패해도 cFS 명령 처리는 그대로 진행한다.

| 조건 | 표시 |
| --- | --- |
| 부팅 직후 / 지상국 미연결 / 기본 대기 | 흰색 고정 |
| MANUAL 모드 | 파랑 고정 |
| AUTO 모드 | 노랑 고정 |
| 사용자가 명시적으로 STOP 선택 | 빨강 고정 |
| 실제 payload sequence 실행 중 | 초록 2Hz 점멸 |
| REACTION 모드 | 인접한 빨간 LED 2개가 시계방향으로 이동 (0.1초/스텝) |

링 앞면 기준 시계방향이며, 실제 연결에서 방향을 확인했다. 기본 STOP 모드만
있는 부팅 직후와 사용자가 선택한 STOP을 구분한다. 지상국 연결이 끊기거나 cFS
텔레메트리가 1초 이상 없거나 gateway 상태가 2초 이상 갱신되지 않으면 흰색이다.
동시 상태 우선순위는 미연결/오래된 상태→흰색, REACTION, 명시적 STOP,
실행 중 payload, MANUAL/AUTO, 기본 흰색 순서다.

Payload는 `mcu_v2.monitor.StatusPublisher`의 `payload.json`에서 현재 부팅의
유효한 `online && sequence_active`를 확인한다. 단순 PAYLOAD 모드 선택만으로
점멸하지 않으며 완료/실패/MCU 연결 유실/오래된 상태에서는 점멸을 끝낸다.
Payload 서비스 수정도 다음 ground-support 실행 시 적용된다.
리액션휠의 기존 실제 구동 명령은 아직 미구현이며 LED 표시가 그 기능을 활성화하지 않는다.

```bash
systemctl status loonar-mode-led.service
journalctl -u loonar-mode-led.service -n 30
cat /run/loonar-led/status.json
```

단발 `neopixel.py`와 모드 서비스는 GPIO 소유권 lock을 공유한다. 수동 색상 시험은
먼저 서비스를 정지하고 실행한 후 자동 표시를 다시 시작한다:

```bash
sudo systemctl stop loonar-mode-led.service
python3 ~/LOONAR/platforms/loonar/tools/neopixel.py --rgb 0 0 255
sudo systemctl start loonar-mode-led.service
```

다른 링/배선의 주소 증가 방향이 반대이면 `/etc/loonar/mode-led.env`에
`LOONAR_LED_REVERSE=1`을 저장하고 `sudo systemctl restart loonar-mode-led.service`로
방향을 반전할 수 있다. `mode_led.py --count N --chase-step 초 --blink-hz Hz`도 지원한다.

장치 없는 검증:

```bash
python3 -m unittest discover -s platforms/loonar/tools/tests -p test_mode_led.py
python3 -m unittest discover -s platforms/loonar/tools/tests -p test_payload_pca_service.py
# 빌드된 cFS + 모터 backend가 없는 격리 gateway로 텔레메트리 경로 검증
python3 platforms/loonar/tools/tests/mode_led_telemetry_smoke.py
```

### 리액션휠 시험 설정

지상국의 ‘리액션휠 시험 설정’ 패널에서 ESC 중립·방향별 1/2단계 오프셋과
유지시간, 서보 중립·좌/우 위치·유지시간·ESC 중립 이후 대기시간을 입력한다.
각 입력 아래에는 펌웨어 기본값을 표시하며 아래쪽에서 실제 PWM 순서를 미리 보여준다.
입력/기본값 복원만으로는 실행하지 않는다. ‘왼쪽 1회 실행’ 또는 ‘오른쪽 1회 실행’으로
선택값 전체를 전송한다. 요청 이력에는 `reaction_settings`가 함께 남는다.

기본값: ESC 중립1488 µs, 서보 중립1500 µs. 왼쪽+25 µs 5초 → +50 µs 10초,
오른쪽−25 µs 10초 → −50 µs 10초. ESC 중립 후10ms 대기, 왼쪽서보800 /
오른쪽서보2200 µs로3초 유지 후 중립. 부팅 준비는 중립5초다.

GCS → cFS → Gateway → 기존 Control backend가 설정을 전달한다. USB 소유자는
추가하지 않는다. MCU가 설정을 수락한 뒤에만 실행 명령을 보내며 실패/timeout은
자동 재전송하지 않는다. 동작 중 재실행은 거부한다. MCU의 실제 수락·단계·오류가
지상국에 표시되며, 완료는 STOP 모드로 돌아간다. STOP, 다른 주행 명령/모드 전환,
GCS TCP 또는 Gateway 단절은 리액션휠 취소를 전달한다.
설정은 RAM에 유지되고 재부팅 시 기본값으로 돌아간다. 강도 입력은 PWM 오프셋이며
RPM·토크 또는 측정된 정지 상태를 의미하지 않는다.
