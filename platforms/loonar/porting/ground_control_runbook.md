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

Payload 서비스는 기본으로 함께 시작하며 `20356570` 보드의 USB by-id 경로를 사용한다.
미연결 상태에서는 OFFLINE을 보고하고 1초마다 연결을 재시도한다. 주행·영상은 계속 실행된다.
다른 보드는 `--payload-device /dev/serial/by-id/...` 또는 `PAYLOAD_DEVICE` 환경변수로 지정한다.
전체 localization은 별도 실행한다. Payload 설정은 [별도 안내](payload_pca_runbook.md)를 따른다.
checkout bench를 사용할 때 systemd Payload/gateway/cFS/Control을 중복 실행하지 않는다.
`loonar-mcu@control.service`가 없으면 systemd runtime이 설치되지 않은 것이다.
checkout 실행에는 그 unit이 필요하지 않다.
