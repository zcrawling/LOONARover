# LIMO → LOONAR 포팅 계획 및 검증 절차

작성일: 2026-09-18. 대상은 **Intel NUC / Ubuntu 22.04 / ROS 2 Humble →
Raspberry Pi 5 / Ubuntu 24.04 LTS arm64 / ROS 2 Jazzy**다.
재검토 기준은 기존 main `1f9a156`, 별도 root의 master `5049941`, 이를 연결한
merge `2bea6db` 및 함께 반영하는 이 컴퓨터의 개발 작업물이다.
이 문서는 구현·배포 계획이며, Pi 실기 검증 완료 보고서가 아니다.

**2026-09-18 하드웨어 제작 중 준비 지침:** 실기 검증 순서는 사용자 요청에 따라
**카메라 → Teensy USB → 라이다/ToF → 모터 및 주행**으로 변경한다.
그 전에는 의존성 설치, native build, 비활성 서비스 배포와 문서 준비만 수행한다.
테스트 실행·센서 열거·촬영·MCU 업로드·주행은 이번 준비 작업에 포함하지 않는다.
Teensy 최초 연결은 Pi HAT UART 대신 USB CDC이며, 최종 UART 구성도 유지한다.
구체적인 준비 명령과 다음 실기 절차는 [배포 안내](../deploy/README.md)에 기록한다.

### 병합 후 다시 확인한 사항

- main과 master는 공통 조상이 없었지만 소스 내용은 같았다. master의 차이는 셸 파일
  5개의 실행 권한 제거뿐이었다. main을 첫 부모로 병합하고 실행 권한을 유지했다.
- 로컬 추가분은 GCS/cFS 통합 실행·시험 도구, localization/ToF/AprilTag 실험 코드,
  PCB B4 설계 자료다. `cfs/apps`에는 `ground_link`, `vehicle_adapter` 두 앱만 있다.
- 현재 로컬에서도 독립 Payload Transport/cFS payload 앱과 MCU payload firmware는
  확인되지 않는다. `PAYLOAD_EXEC` MID 발행 경로를 통신 앱 구현 완료로 계산하지 않는다.
- 소프트웨어 작업은 의존성/공통부 배포와 payload 통신 계약 정리를 먼저 한다.
  실기 검증 순서는 위의 최신 사용자 지침을 따른다. payload 구현은 별도 미완료 항목이다.
- CubeEye vendor archive는 소스 checkout에 포함되지 않는다.
  [SDK 체크섬과 별도 배치 절차](../vendor-assets.md)를 P0에 포함한다.

## 1. 결론: 재컴파일만으로 되는 범위

**Gateway·GroundLink·cFS 공통 앱은 ARM64 재빌드 중심으로 이식할 수 있다.
그러나 전체 로버는 바이너리를 컴파일해서 복사하는 것만으로 동작하지 않는다.**
실제 주행과 odom을 막는 항목은 LOONAR backend, MCU 측정/제어 구현,
센서 연결, 서비스 구성이다. CSI 카메라는 Ubuntu 24.04 호환성도 별도로 해결해야 한다.

| 구성 | 소스에서 확인한 현재 상태 | 필요한 포팅 | 판정 |
| --- | --- | --- | --- |
| `vehicle_gatewayd`, `vehicle_gatewayctl` | C++20, Linux Unix `SOCK_SEQPACKET`, 명시적 wire codec | Pi에서 재빌드, runtime path/권한 조정, 동일 회귀 테스트 | 재빌드 + 배포 설정 |
| cFS GroundLink / VehicleAdapter | POSIX socket 기반 C 앱, cFS v7.0.1 테스트 runner 존재 | cFE·OSAL·PSP·앱 전체를 같은 ARM64 mission으로 빌드, runtime 전체 배포 | 재빌드 + mission/service 설정 |
| systemd | LIMO user units는 Humble, `/home/wego`, `%t`에 의존. 영상은 system unit | Pi용 system units와 환경·경로·장치 권한·재시작 정책 작성 | 설정 포팅 필요 |
| LOONAR Control backend | LIMO ROS backend만 구현됨 | `backend.sock` 뒤의 Teensy RS-485 backend와 sensor bridge 구현 | 신규 구현 |
| Control Teensy | wire/CRC/health gate 보유. `controller_tbd.c` 출력은 항상 0. encoder/BNO085 수집 없음 | 센서 수집, 실제 제어기, 측정 telemetry, MCU 보호 조건 검증 | 신규 구현 |
| odom | Pi용 최소 `robot_localization` launch/YAML 존재 | 센서 입력·TF 연결, motion restrict executor/상태 연결, Jazzy 검증 | 설정 재사용 + 연결 구현 |
| CubeEye I200DK | Pi5/Noble ARM64 SDK 2.5.9 압축파일, 별도 실험 ROS bridge 존재 | SDK native load, helper 재빌드, Jazzy wrapper·udev·측정 TF | 재사용 가능, 실기 검증 필요 |
| 지상국 영상 | 공통 GStreamer 송신기와 Pi libcamera 설정 존재 | 24.04 CSI 스택 검증/구축, camera 설정, CPU·열·수신 시험 | 바이너리 복사만으로 불가 |
| 지상국 실제 상태 | VehicleStatus relay 구현, MCU/Device/Event envelope 존재 | 실제 producer, 내부 전달 경로와 freshness/validity 연결 | 추가 구현 |
| Payload 통신 | PAYLOAD command와 EXEC MID만 구현; 별도 앱/transport 없음 | cFS app/transport, MCU wire, 완료·실패 결과와 sensor telemetry 연결 | 계약 확정 + 구현 필요 |

ROS 2 Jazzy는 Noble의 arm64를 지원하므로 이 조합을 포팅 기준으로 삼는다.
Humble의 `build/`, `install/`, Python 환경과 x86 SDK는 복사하지 않는다.
[공식 지원 플랫폼](https://www.ros.org/reps/rep-2000.html#jazzy-jalisco-may-2024-may-2029).

## 2. 1차 포팅 범위와 기준 데이터 흐름

1차 범위는 시스템 기동, 실제 센서, **robot_localization + motion restrict**, cFS 지상국
명령/상태, 독립 영상, 운용자 검증이다. 실험 중인 custom DR 교체, C_accel,
연속 ICP/RGB-D odometry, SLAM/Nav2, ToF 기반 pose 보정은 기본 서비스에 넣지 않는다.
ToF는 먼저 데이터 취득·기록·진단까지 연결한다.

```text
GCS ── TCP 7443 / GroundLink ── cFS GroundLink / VehicleAdapter
                                      │ cfs.sock
                               vehicle_gatewayd
                                      │ backend.sock
                         LOONAR backend (Control link 단독 소유)
                                      │ 초기 USB CDC → 이후 Pi HAT UART/RS-485
                                Control Teensy
                              encoder / BNO085 / motor
                                      │ 측정값 fan-out
                         ROS sensor bridge (serial 직접 접근 없음)
                         /wheel/odom + /imu/data
                                      │
                         robot_localization EKF
                         /odometry/filtered + odom→base_link

motion restrict executor ── AUTO 요청 / ros.sock ── Gateway
                           ↑ odom / stationary / mode feedback

I200DK ── isolated CubeEye helper ── ROS /tof/depth/points + /tof/status
Camera Module 3 Wide ── libcamera → x264 → MPEG-TS / UDP 5600 ── GCS

cFS PAYLOAD_EXEC ── PayloadAdapter/Transport (구현 대상) ── 별도 RS-485 ── Payload Teensy
       ↑                     │ 실제 상태/완료/오류
       └──────── cFS SB / GroundLink ── GCS
```

Camera Module 3 Wide와 BNO085의 Control MCU 소유권은
[hardware baseline](../hardware/hardware_baseline.md)을 따른다.
기존 Pi video README의 “카메라 미정”과 최소 EKF README의 “BNO driver” 표현은
이 하드웨어 경계에 맞춰 후속 구현에서 정리한다. BNO085를 Pi I²C에 직접
연결하는 별도 경로를 가정하지 않는다.

## 3. systemd 포팅

### 배포 단위와 경로

Pi 무인 기동 기준으로 **system service + 전용 `loonar` 사용자**로 통일한다.
LIMO user service를 그대로 설치하면 `%t`가 가리키는 위치와 로그인 수명에 따라
cFS 연결이 깨질 수 있다. 모든 프로세스가 같은 socket 경로를 사용해야 한다.

| 목적 | 계획 경로 |
| --- | --- |
| 버전별 실행물 | `/opt/loonar/releases/<release-id>/` |
| 활성 버전 | `/opt/loonar/current` |
| 설정 | `/etc/loonar/` |
| Gateway runtime | `/run/loonar/vehicle-gateway/{cfs,ros,backend}.sock` |
| cFS writable runtime | `/var/lib/loonar/cfs/` (`core-cpu1`, `cf/`, startup, writable files의 설치 layout 명시) |
| ToF SDK | `/opt/loonar/vendor/cubeeye/2.5.9/release/` |
| 기록·진단 | `/var/log/loonar/`, journald, 별도 용량 제한 rosbag 경로 |

다음 unit 이름은 **구현 예정**이며 현재 파일이 존재한다는 뜻이 아니다.

| Unit | 실행/의존 관계 | 필수 설정/기동 판정 |
| --- | --- | --- |
| `vehicle_gatewayd.service` | 공통 daemon | `User=loonar`, `RuntimeDirectory=loonar`, 일관된 `--runtime-dir`; 세 socket과 STOP 상태 확인 |
| `loonar-control-backend.service` | 유일한 Control serial 소유자 | Gateway 이후 시작, stable device alias·`dialout`, reconnect 검증 |
| `loonar-cfs.service` | `core-cpu1` 및 두 앱 | Gateway 이후 시작, `LOONAR_GATEWAY_SOCKET` 명시, 정확한 `WorkingDirectory`, startup/module load 로그 |
| `loonar-sensors.service` | backend 측정 fan-out → ROS + fixed TF | Jazzy와 배포 overlay 명시 source, sensor topic freshness로 ready 판정 |
| `loonar-localization.service` | 최소 EKF | sensor service 이후 시작, TF와 입력 최신성 확인 |
| `loonar-motion-restrict.service` | primitive executor / AUTO bridge | 초기 비활성, 연결만으로 운동 시작 금지, 운용 요청으로 실행 |
| `loonar-tof.service` | SDK helper + Jazzy wrapper | USB 권한, SDK 자식 프로세스에만 library path 적용 |
| `loonar-video.service` | 기존 공통 송신기 재사용 | `video`/필요시 `render` 권한, `/etc/loonar/video.env`, 다른 서비스와 독립 재시작 |
| `loonar.target` | 운용 stack 묶음 | 설치/시작/중지 entrypoint, 종료와 재기동 시험 포함 |

payload를 cFS 앱으로 구현하면 기존 `loonar-cfs.service`가 그 앱까지 로드한다.
별도 serial daemon을 채택할 때만 `loonar-payload-transport.service`를 추가한다.
두 구현이 같은 payload UART를 동시에 열지 않는다. payload 앱 실패가 전체 cFS를
재시작시키는지는 startup exception action 및 실제 fault 시험으로 확인한다.

`After=`는 실행 순서일 뿐 topic/socket readiness를 보장하지 않는다. 초기에는
프로세스 내부 재연결과 제한 시간 readiness check를 사용한다. `Requires=`의
연쇄 종료가 필요한 서비스만 묶고, ToF/영상 실패로 cFS/Gateway를 같이 끄지 않는다.
Gateway 재시작으로 socket이 재생성되면 adapter와 backend가 재접속해야 한다.

설치 스크립트는 사용자/그룹, runtime/state directory ownership, udev,
Jazzy overlay wrapper, units와 configuration을 함께 배포해야 한다.
shell 로그인 설정에 의존하는 `bash -lc`와 `/home/wego` 경로를 없앤다.
기존 영상 unit에는 `User=`가 없으므로 그대로 복사하지 않고 서비스 사용자와
카메라 권한을 명시한다. foreground 실행과 `Restart=on-failure`를 기본으로 하고,
반복 실패는 journald와 실패 상태로 확인할 수 있게 한다.

## 4. cFS: 공통부 재빌드와 실제 차량 연결을 분리

### 먼저 할 ARM64 검증

기존 [GCS runner](../../../tools/gcs_test/run.py)는 NASA cFS v7.0.1 commit
`088b2fa828db9ff7e00733f1908e0eeb59f66ce3`를 고정하고 `native_std` mission을 만든다.
Pi에서 **새 build 디렉터리로 native build**하는 것을 1차 방법으로 삼는다.
NASA의 Raspberry Pi target 존재만으로 Pi5/Noble의 이 mission이 통과했다고
판정하지 않는다. [NASA cFS](https://github.com/nasa/cFS).

- `core-cpu1`만 옮기지 않는다. 동일 빌드의 cFE/OSAL/PSP, `cf/lnr_ground.so`,
  `cf/lnr_vehicle.so`, startup script와 mission 산출물을 함께 배포한다.
- [mission fragments](../../../cfs/mission/targets.cmake.fragment)를 반영한다.
  현재 앱의 엔트리와 짧은 module 이름을 유지하고 MID 충돌을 점검한다.
- `.so`와 core 모두 `file`/`readelf`로 AArch64 확인, `ldd`로 누락 라이브러리 확인.
  x86_64 산출물과 혼합하지 않는다. cFS SB header/config ABI도 같은 mission으로 맞춘다.
- 외부 GroundLink와 Gateway wire는 명시적 직렬화이므로 CPU struct padding을
  직접 전송하지 않는다. 그래도 ARM64에서 golden vector·fragmentation 테스트를 다시 한다.
- `/cf` 매핑과 `WorkingDirectory`, writable cFS 파일, thread/priority 관련 경고를
  Pi 로그로 확인한다. privileged 실행으로 문제를 숨기지 않는다.

### 실제 하드웨어 연결은 별도 구현

`TeensyRs485Backend`가 UART를 단독 소유한다. 초기에는 기존 `backend.sock` 계약에
맞춘 독립 프로세스로 구현하고, encoder/IMU를 ROS bridge에 전달할 read-only IPC를
추가한다. ROS 노드가 serial을 다시 열지 않도록 한다.

Control wire v1에는 `MPU_HEALTH`, 목표 속도, `MCU_STATUS`만 있다.
**encoder/gyro 측정 메시지는 없으며 `applied_*`는 제어기로 전달한 지령이다.**
이를 `/wheel/odom` 또는 측정 속도로 사용하면 안 된다. 실제 encoder sample,
gyro, measurement counter/time, validity와 error 정보를 담을 wire 개정이 선행된다.
version/length/CRC와 구버전 거부 동작을 codec·firmware·Pi backend에서 함께 검증한다.

현재 [project.md](../../../project.md)는 Gateway TTL/lease/watchdog와 자동 mode 변경을
두지 않는다고 명시하지만, 오래된 platform/interface README에는 “project.md가 MCU
lease를 요구한다”는 문구가 남아 있다. 이번 포팅에서는 **Gateway 의미를 유지**하고,
MCU의 명령 freshness/재접속 동작을 별도 하드웨어 계약으로 확정한다.
기존 health 500 ms timeout은 health가 계속 들어오는 동안 오래된 motion을
막아주지 않는다. 이 경우와 MCU/Pi 재부팅을 실주행 전 HIL에서 검증해야 한다.

### 지상국 telemetry 완성 조건

| 데이터 | producer / 필요한 연결 | 지상국 판정 |
| --- | --- | --- |
| `COMMAND_RESULT`, `GATEWAY_STATUS` | 기존 cFS ↔ Gateway 재사용 | 요청 sequence 일치, 실제 선택 mode 확인 |
| `VEHICLE_STATUS` | backend 측정 + EKF odom 집계 → 기존 relay | 실측한 필드만 valid, synthetic 11.7 V 제거 |
| `LOONAR_MCU_STATUS` | 실제 MCU frame → 새 status ingress → cFS MID | 온도/uptime/inhibit/RX error, applied command와 실측 속도 구분 |
| `DEVICE_STATUS`, `EVENT` | 센서·링크·카메라·Wi-Fi 진단 producer → cFS SB | 상태·마지막 갱신·끊김/복구 표시 |

Gateway 로컬 protocol은 현재 일반 `VehicleStatus`까지 지원한다. MCU/Device/Event의
GroundLink envelope가 있다는 것만으로 producer 연결이 완료된 것은 아니다.
후속 구현에서는 **명령 경로와 분리된 telemetry ingress를 VehicleAdapter에 추가**해
backend/ROS/영상 진단을 SB로 올리는 방안을 기본으로 상세 설계한다. 타입·길이·source·
timestamp·validity와 회귀 테스트를 포함하고 기존 wire를 무표시로 바꾸지 않는다.

`backend.sock`은 한 backend 연결을 유지한다. 별도 상태 주입기가 실 backend와
경쟁하게 하지 않는다. EKF pose 집계는 backend 또는 정한 read-only IPC 경로를 통한다.
관측 끊김은 값 0으로 보이지 않게 invalid/stale로 드러낸다.
PAYLOAD/REACTION envelope 시험과 actuator 완료는 별도이며 REACTION은 현재
`NOT_IMPLEMENTED`다. GCS 웹 UI는 현재 `GCS/README.md`의 설계 단계이므로
1차 합격 기준은 기존 mock/실제 사용하는 GCS의 프로토콜 수신까지다.

### Payload 중심의 추가 이식 작업

현재 실행 경로는 다음에서 끝난다.

```text
GCS PAYLOAD_CMD (0x0004)
  → GroundLink: LOONAR_PAYLOAD_CMD_MID_VALUE (0x19A3)
  → VehicleAdapter: 명시적 STOP, PAYLOAD mode 선택
  → LOONAR_PAYLOAD_EXEC_CMD_MID_VALUE (0x19A5) 발행
  → [별도 subscriber/실제 UART 처리 없음]
```

`VA_Activity()`의 `OK`는 SB 전송 성공을 뜻한다. payload 장치가 요청을 받았거나
완료했다는 뜻이 아니다. 기존 smoke의 PAYLOAD PASS 역시 이 경계까지만 검증한다.
이 구분을 GCS 표시와 포팅 완료 기준에 반영한다.

| 순서 | 구현/확인 대상 | 완료 조건 |
| --- | --- | --- |
| PL0 계약 | MCU 소스·firmware 버전, UART path/baud, frame/CRC, opcode/단위, sample schema, timeout | Pi/MCU/GCS 공통 계약표. 미확정 숫자를 임의로 할당하지 않음 |
| PL1 cFS 통합 | PayloadAdapter의 EXEC MID 구독, app CMake/entrypoint, mission targets/startup, pipe depth·처리 주기 | CPU native build와 앱 로드/구독 확인, MID 중복 없음 |
| PL2 전송 | payload 전용 UART/decoder, bounded command/sample queue, partial/CRC frame 처리 | pseudo-terminal MCU simulator 왕복 후 실제 MCU 검증 |
| PL3 상태/결과 | request/activity ID, accepted와 completed/failed 구분, sensor validity·시각·진행률 | GCS 요청부터 MCU 응답 및 cFS/GCS 최종 결과까지 상관관계 확인 |
| PL4 복구/격리 | 중복 request, timeout, USB/UART 끊김, MCU/cFS 재시작, disk stall | START 자동 재전송 없음, STATUS로 재동기화, Control/영상 지연 기준 유지 |

[payload MCU reference](../interfaces/payload_mcu_reference.md)의 별도 link 소유권,
bounded queue, discrete request dedup 및 재접속 시 상태 조회 원칙을 따른다.
MLX90614/MAX31865/LIS3MDL 샘플의 실제 packet schema와 측정 주기는 아직 고정되지
않았으므로 공급받은 firmware/실측 sample에 맞춰 확정한다.

기본 구현안은 **cFS payload 앱이 mission 상태와 명령을 소유하고, 전용 transport
worker가 serial을 소유**하는 형태다. cFS 명령 처리 task에서 blocking serial read나
disk flush를 하지 않는다. 별도 프로세스로 나누더라도 이 책임 경계는 유지한다.
Control UART와 parser/buffer/health를 공유하지 않으며, 최종 PCB B4의 실제 UART
핀·트랜시버·전원·종단을 [제조 기준](../hardware/pcb/rbphat-xa-b4/manufacturing/FABRICATION_NOTES.md)과
대조한다. 오래된 하드웨어 문서의 부품명만으로 설정하지 않는다.

GroundLink의 현재 activity parameter 상한은 64 B, 전체 frame payload 상한은 512 B다.
payload 원시 센서 덩어리를 기존 activity parameter에 끼워 넣지 않는다.
최초 통합에서는 승인된 status/event 요약을 사용하고, 별도 payload 결과/샘플 MID나
GroundLink type이 필요하면 C/C++ codec와 GCS parser, 길이·버전·잘못된 frame 테스트를
같이 추가한다. 파일 전송은 제어/상태 경로와 분리하고 1차 통신 수락 이후로 둔다.

**Payload 앱을 이미 구현했다고 주장하려면** 앱 소스, build 등록, startup 등록,
EXEC 구독, 실제 frame log, 완료 결과 중 어느 단계까지 존재하는지 파일/시험으로
확인해야 한다. 현재 병합 대상에는 그 신규 앱이 없으므로 위 작업은 미완료로 남는다.

## 5. ROS 2: 의존성 먼저, 최소 odom부터

### 의존성 설치를 포팅 시작의 선행 조건으로 둔다

공식 Jazzy 설치 절차로 locale, Ubuntu 저장소와 ROS apt source를 설정한 **Pi에서**
아래 기본 목록을 설치한다. 저장소 설정은
[공식 Jazzy 설치 안내](https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html)를 따른다.

```bash
sudo apt update
sudo apt install -y build-essential cmake ninja-build git pkg-config binutils \
  python3-dev python3-venv python3-numpy python3-scipy python3-pytest \
  ros-dev-tools ros-jazzy-ros-base ros-jazzy-robot-localization \
  ros-jazzy-robot-state-publisher ros-jazzy-xacro ros-jazzy-tf2-tools \
  ros-jazzy-sensor-msgs-py ros-jazzy-message-filters ros-jazzy-rosbag2 \
  ros-jazzy-diagnostic-updater libusb-1.0-0-dev \
  gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav \
  ffmpeg v4l-utils usbutils chrony sysstat
```

이 목록은 초기 운용 범위의 기본 의존성이다. CSI 카메라와 SDK의 native 의존성은
아래의 별도 검증을 거친다. 설치 성공과 센서 동작 성공을 구분한다.
Teensy의 PlatformIO/toolchain은 firmware 빌드 환경에 고정하며 Pi runtime에 반드시
설치할 필요는 없다.

```bash
# Pi의 checkout과 전용 workspace. Humble overlay를 source하지 않는다.
export LOONAR_SRC="$HOME/LOONAR"
export LOONAR_WS="$HOME/loonar_jazzy_ws"
source /opt/ros/jazzy/setup.bash
# 새 OS에서 초기화하지 않은 경우에만 sudo rosdep init을 한 번 실행한다.
rosdep update
rosdep install --from-paths "$LOONAR_SRC/platforms/loonar/ros2" \
  --ignore-src --rosdistro jazzy -y
rosdep check --from-paths "$LOONAR_SRC/platforms/loonar/ros2" \
  --ignore-src --rosdistro jazzy
mkdir -p "$LOONAR_WS"
cd "$LOONAR_WS"
colcon list --base-paths "$LOONAR_SRC/platforms/loonar/ros2"
colcon build --base-paths "$LOONAR_SRC/platforms/loonar/ros2" \
  --packages-select loonar_localization --symlink-install
source install/setup.bash
ros2 pkg prefix robot_localization
ros2 pkg prefix loonar_localization
```

`common/ros2/loonar_localization`과 `platforms/loonar/ros2/loonar_localization`은
**동명 패키지**다. 저장소 전체를 colcon/rosdep 탐색 대상으로 지정하지 않는다.
초기에는 후자만 선택하고, motion restrict를 옮길 때 별도 패키지 이름을 사용한다.
신규 bridge/executor의 `package.xml`에는 실제 import/build 의존성을 모두 선언하고,
위 rosdep install/check를 **빌드 전에** 다시 실행한다. 현재 최소 패키지에는
launch가 사용하는 `ament_index_python`의 직접 의존성 선언도 보완한다.
Python은 Ubuntu/Jazzy의 system Python을 사용하고, SDK 동봉 Python이나 NUC의
venv를 복사하지 않는다.

### odom 고정 구성

기존 [minimal EKF](../ros2/loonar_localization/config/loonar_minimal_ekf.yaml)를 사용한다.

| 항목 | 초기 구성과 계약 |
| --- | --- |
| wheel 입력 | `/wheel/odom`의 실측 `vx`만 사용. frame=`odom`, child=`base_link` |
| IMU 입력 | `/imu/data`의 gyro `wz`만 사용. frame=`imu_link`, rad/s, CCW 양수 |
| EKF | 50 Hz, `two_d_mode=true`, `use_control=false` |
| 출력 | `/odometry/filtered`, 단독 동적 TF `odom → base_link` |
| covariance | wheel vx `0.0225`, gyro wz `0.001`은 시작값. LOONAR에서 실측하여 조정 |
| fixed TF | 실측 `base_link → imu_link`, `base_link → cubeeye_optical`. 각 edge의 발행자는 하나 |
| 시간 | Pi ROS time으로 수신 stamp, MCU sample counter/time 별도 보존. 재부팅과 wrap 진단 |

wheel pose, IMU yaw/orientation, 가속도, 지령 속도, ToF는 초기 EKF에 넣지 않는다.
`two_d_mode`는 평면 모델 설정이며 직진/회전 제한이나 미끄러짐 검출 구현이 아니다.
차체 pitch/roll을 무시할 수 있는 범위를 실험으로 확인하고, 단차와 접촉 상실 시의
정확도까지 보장하지 않는다.

### 이번 motion restrict의 의미와 구현 범위

이번 계획에서는 기존 설계에 맞춰 **ROTATE → STOP → STRAIGHT → STOP의
primitive 실행 제약**으로 정의한다. 추정기의 soft constraint/ZUPT와 구분하여 구현한다.

- 첫 executor는 `STOP / STRAIGHT_SLOW / STRAIGHT_NORMAL / ROTATE_LEFT / ROTATE_RIGHT`를
  지원한다. 초기 AUTO는 곡선 명령을 만들지 않고, 속도·거리·각도·허용오차는 LOONAR
  설정으로 받는다. Gateway에서 MANUAL 입력값을 바꾸는 수정은 하지 않는다.
- executor는 현재 mode, EKF feedback, stationary 진단을 받아 AUTO에서만 `ros.sock`으로
  요청한다. 완료·취소 시 명시적 zero/STOP을 처리하며 재시작으로 이전 동작을 재개하지 않는다.
- 공통 `PrimitiveNode`는 현재 `localization/primitive_intent`만 출력한다. Gateway 실행
  연결은 아직 없다. 실험 runner의 직접 `/cmd_vel` 경로를 운용 경로로 복사하지 않는다.
- EKF 단독 검증 후 별도 stationary/primitive 노드를 추가한다. STOP 지령만으로 정지라고
  판정하지 않는다. 연속 window의 wheel/gyro/필요한 accel과 stamp 최신성을 확인하고,
  없는 신호는 unknown으로 남긴다.
- NHC/ZUPT를 추가할 때에는 측정 adapter에서 명시적 covariance를 가진 관측으로
  EKF에 연결하는 설계와 테스트를 별도로 만든다. 현재 공통 실험 노드는 custom DR용이며
  **robot_localization에 제약을 입력하는 완성된 노드가 아니다**. soft weight 출력만으로
  NHC 구현 완료라고 판단하지 않는다.
- 회전 지령이라는 이유로 실측 translation을 0으로, 직진 지령이라는 이유로 gyro를
  0으로 덮어쓰지 않는다. slip/contact 의심 시 제약을 약화한다. 실험 DR의 TF 발행은
  초기 운용에서 비활성화한다.

## 6. CubeEye I200DK 포팅

SDK는 `platforms/loonar/arm64-pi5-linux-ubuntu_24_04_v2.5.9_20250311.tar.gz`다.
내부 경로는 `arm64-pi5-linux-ubuntu_24_04/release/`이며, `lib/libCubeEye.so`는
ELF64 AArch64 (`e_machine=183`)다. `include/CubeEye`와 `udev/98-CubeEye.rules`도 있다.

기존 [bridge.py](../../../tools/cubeeye_ros/bridge.py)와
[capture_xyz.cpp](../../../tools/cubeeye_ros/capture_xyz.cpp)를 활용한다.
LIMO 시험은 SDK 2.5.11 기반이지만 이번 조사에서 2.5.9 header에 대한 helper의
C++ syntax check는 통과했다. **ARM64 link, shared library load, USB 수신은 미검증**이다.

1. archive SHA256, SDK 버전, Pi OS/kernel, 장치 firmware/USB ID를 기록하고 SDK를 고정 배치한다.
2. Pi에서 helper를 빌드하고 transitive dependency와 `GLIBC/GLIBCXX` 요구를 확인한다.
   `LD_LIBRARY_PATH`는 helper에만 적용한다. SDK의 Python 3.8, OpenCV/FFmpeg를
   Jazzy와 시스템 GStreamer의 검색 경로에 섞지 않는다.
3. 동봉 udev rule을 검토하여 서비스 사용자의 USB 접근을 설정한다. GUI의 임시 ACL에
   의존하지 않는다.
4. headless XYZ 수신 후 Jazzy의 `/tof/depth/points`, `/tof/status` 발행을 검증한다.
   초기 5 Hz, stride 4를 출발점으로 사용하고 유효점 수·단위·거리·stamp를 기록한다.
5. ROS package/launch로 정리하여 매 실행 시 컴파일과 home cache 의존성을 없앤다.
   SDK 자식 종료, USB 분리, 일정 시간 frame 없음에 대한 오류·재연결 처리를 보완한다.
6. LOONAR에서 실측한 extrinsic으로 바꾼다. bridge의 LIMO 값 `(0.15, 0, 0.033)`을
   그대로 사용하지 않는다. optical/FLU 변환을 두 번 적용하지 않는다.

현재 bridge 출력은 점군과 status뿐이며 depth image/CameraInfo는 없다. 필요하면
SDK의 실제 보정 정보로 구현하고 가상의 intrinsic을 만들지 않는다.
SDK callback의 host 시각은 노출 시각이 아니므로 stamp 단조성과 지연을 측정한다.
초기 EKF는 ToF에 의존하지 않는다. 점군 수신 성공과 ICP 정확도 검증은 별개다.

## 7. 독립된 지상국 카메라 스트림

`common/video/loonar-video-stream`을 재사용하고 제어 TCP/ROS와 독립된
**H.264 / MPEG-TS / UDP 5600**을 유지한다. Pi5에서는 software H.264 인코더를 사용한다.
[Raspberry Pi 카메라 문서](https://www.raspberrypi.com/documentation/computers/camera_software.html).
기존 `hardware/camera_pi_reference.md`의 hardware encoder/token 방식은 초기 구현 기준으로
사용하지 않는다.

### Ubuntu 24.04의 CSI 카메라 검증을 선행한다

Canonical의 현행 문서에서는 Raspberry Pi CSI camera stack을 Ubuntu 25.04부터 지원한다.
**Noble에서 `gstreamer1.0-libcamera` 설치만으로 Camera Module 3 Wide가 작동한다고
판정할 수 없다.** [Ubuntu CSI 카메라 지원](https://ubuntu.com/hardware/docs/boards/how-to/special_hardware/rpi-camera/),
[Ubuntu Raspberry Pi 제약](https://ubuntu.com/hardware/docs/boards/how-to/ubuntu_supported/raspberry-pi/).

요구된 24.04를 유지하면서 Pi용 libcamera/IPA/pipeline handler, rpicam-apps,
GStreamer plugin, kernel/device-tree 조합을 실제 장치에서 검증한다.
backport/source build가 필요하면 동작 commit과 의존성을 고정하고 별도 prefix/package로
관리한다. OS 라이브러리를 임의로 덮어쓰지 않는다. `rpicam-hello --list-cameras`는
rpicam-apps 도입 후의 확인 명령이며 Noble에 기본 제공된다고 가정하지 않는다.

초기 네트워크 시험은 test pattern이나 임시 USB UVC로 진행할 수 있지만, 그 결과로
최종 CSI 카메라를 합격 처리하지 않는다. CSI 문제는 cFS/odom 개발과 독립적으로 해결하되
최종 하드웨어 수락의 미완료 항목으로 유지한다.

### 스트림 수락 시험

- low (640×360/30 fps/1 Mbps)부터 시작하고 medium/high는 실측 후 사용한다.
- 카메라 열거 → 단독 capture → `libcamerasrc` → encode → Pi 내부 UDP → GCS 표시 순서다.
  `gst-inspect` 성공은 capture 성공을 뜻하지 않는다.
- `/etc/loonar/video.env`에 실제 GCS IP, camera identifier, profile을 넣는다.
  example IP를 그대로 사용하지 않는다.
- ToF/EKF/cFS/bag 녹화 동시 부하에서 CPU, RSS, 온도, 실제 fps, 표시 지연을 측정한다.
  카메라 앞의 시계나 움직이는 물체로 화면 갱신을 확인한다. 패킷 수신만으로 합격하지 않는다.
- 영상 재시작/수신 중단 중에도 제어 응답과 odom이 유지되어야 한다. 동일 카메라를
  별도 ROS 프로세스가 중복 open하지 않는다. Vision 분기는 이후 단계로 둔다.

## 8. 실시 순서와 단계별 완료 조건

| 단계 | 작업과 산출물 | 다음 단계 진입 조건 |
| --- | --- | --- |
| P0 환경/의존성 | Noble arm64, Jazzy, apt/rosdep/SDK 목록, 선택 package 목록, CSI 기술 검증 | 미해결 항목 명시. ROS build 의존성 전체 해결 |
| P1 공통부 | Pi native Gateway/cFS, system units/install, test pattern | Pi CTest와 실제 cFS smoke 통과, 재부팅 후 연결 |
| P1-P payload | PL0~PL4 계약·앱·독립 transport·결과 연결 | pseudo-terminal 및 실 MCU 왕복, GCS 최종 결과, 장애 격리 통과 |
| P2 센서 backend | MCU wire 개정, encoder/BNO085 수집, serial backend, ROS sensor bridge, udev/TF | 비구동 상태에서 실제 wheel/IMU/MCU status 갱신과 끊김 검출 |
| P3 최소 odom | Jazzy EKF, motion restrict executor/상태 bridge, 기록 | TF 단독 소유, 정지/직진/회전/취소 및 mode 계약 통과 |
| P4 ToF/실제 카메라 | ARM64 SDK wrapper, 독립 서비스, CSI stack | 실제 점군/영상, 분리·재연결과 동시 부하 시험 통과 |
| P5 운용 통합 | 실제 telemetry producer/ingress, 통합 시험 runner, release manifest | GCS 명령/실측 상태/영상, 30분 soak, 재부팅/rollback 통과 |

P0의 CSI 조사는 처음부터 시작하고 P2/P3과 독립적으로 진행한다.
P1-P는 P2와 병행하되 P5 전에 실제 MCU까지 통과해야 한다. payload 미연결 상태에서
SB 발행만 성공한 결과는 PL1 부분 합격이며 전체 payload 합격으로 올리지 않는다.
일정은 P0의 CSI/SDK 동작과 MCU wire·제어 구현 규모를 확인한 후 산정한다.
바이너리 몇 개를 복사하는 작업으로 전체 공수를 잡지 않는다.

## 9. 운용자가 직접 확인하는 테스트

### A. 현재 코드로 실행 가능한 회귀 시험

저장소 루트에서 실행한다. PC 통과 후 Pi에서 **Pi로 빌드한 산출물**로 다시 검사한다.

```bash
cmake -S . -B build/loonar-porting-review -DBUILD_TESTING=ON -DCMAKE_BUILD_TYPE=Debug
cmake --build build/loonar-porting-review -j 2
ctest --test-dir build/loonar-porting-review --output-on-failure

# 최초 실행은 NASA cFS를 다운로드하고 빌드한다. 실차 backend는 실행하지 않는다.
bash tools/run_gcs_test.sh --build-only
python3 tools/gcs_test/smoke.py
```

기대 결과는 CTest 전체 성공과 smoke의 mode/sequence/synthetic battery/UDP MPEG-TS/
중복 실행 거부/종료 후 port 정리 `PASS`다. 실제 카메라, MCU, odom 정확도는 포함하지 않는다.
smoke는 nonzero MANUAL도 사용하므로 **운용 서비스와 분리하고 실제 backend를 연결하지 않는다**.
TCP 7443을 사용하는 기존 stack/GCS tester와 동시에 실행하지 않는다.

지상국까지의 통신은 다음으로 따로 확인한다.

```bash
# Pi 측. 예시 IP를 실제 GCS IP로 변경한다.
bash tools/run_gcs_test.sh --skip-build --gcs-ip 192.168.0.100 --video test
# GCS 측. ffmpeg가 설치되어 있어야 한다.
ffplay -fflags nobuffer -flags low_delay -framedrop 'udp://@:5600'
```

GCS는 Pi IP의 7443/TCP로 접속한다. HTTP/TLS가 아니다.
GroundLink client는 한 개만 허용하므로 mock과 GUI를 동시에 연결하지 않는다.

### B. Pi 실기의 단계별 점검

아래 서비스 이름과 설치 경로는 **본 계획의 구현·배포 후** 사용하는 것이다.
`systemctl active`만으로 합격하지 않고 데이터의 실제 갱신 증거를 남긴다.

```bash
systemctl --no-pager --full status vehicle_gatewayd loonar-cfs loonar-control-backend
journalctl -b -u vehicle_gatewayd -u loonar-cfs -u loonar-control-backend --no-pager
ss -lxnp
ss -ltnp 'sport = :7443'

source /opt/ros/jazzy/setup.bash
source /opt/loonar/current/ros/install/setup.bash
ros2 node list
ros2 topic info /wheel/odom --verbose
ros2 topic info /imu/data --verbose
ros2 topic echo --once /odometry/filtered
ros2 run tf2_ros tf2_echo odom base_link
# 별도 터미널에서 TF와 센서 갱신율을 확인한다.
ros2 run tf2_ros tf2_echo base_link imu_link
ros2 run tf2_ros tf2_echo base_link cubeeye_optical
ros2 topic hz /wheel/odom
ros2 topic hz /imu/data
ros2 topic hz /tof/depth/points
```

연속 명령은 관측 후 Ctrl+C로 끝낸다. 서비스와 터미널의 `ROS_DOMAIN_ID`, RMW,
overlay를 맞춘다. ROS 관측용 GCS PC도 Jazzy로 맞추고 Humble과의 직접 호환을 가정하지 않는다.
다음 topic과 구현 시 확정한 primitive/state topic을 bag으로 기록한다.

```bash
ros2 bag record -o loonar_acceptance \
  /wheel/odom /imu/data /odometry/filtered /tf /tf_static /diagnostics \
  /tof/depth/points /tof/status
```

미구현 topic은 누락 상태로 표시한다. bag 파일이 만들어졌다는 이유만으로 합격하지 않는다.
반복 실행 시 output 이름을 바꾸고 점군 녹화의 용량을 제한한다.

| 시험 | 조작/입력 | 합격 증거 | 기록 |
| --- | --- | --- | --- |
| T0 cold boot | Pi 재부팅, 로그인 없이 대기 | 서비스 기동, Gateway STOP, primitive 자동 재개 없음 | boot journal/unit 목록 |
| T1 Control | 비구동 상태에서 wheel/차체를 손으로 회전 | encoder 부호·scale, gyro CCW 양수, fresh stamp, 실제 온도/error | wire log/sensor bag |
| T2 정지 odom | 60초 정지 | NaN 없음, stamp 갱신, TF 중복 없음, drift 수치 | bag/stationary 진단 |
| T3 primitive | 저속 직진·좌우 회전·각 STOP을 3회씩, 외부 거리/각도와 비교 | 순서·완료·취소 확인, MANUAL/STOP 중 AUTO 억제, 실측값 강제 0 없음 | 요청/응답, bag, 외부 GT |
| T4 실제 cFS 상태 | GCS/mock의 STOP, MANUAL(0,0), telemetry 관측 | sequence/result 일치, EKF pose·battery 실측 및 validity 일치 | GCS/cFS log |
| T5 ToF | 알려진 거리의 표적, 30분 수신 | 유효점·거리 단위·frame·stamp, 지속 갱신 | 점군/rate/error |
| T6 실제 영상 | 실제 카메라로 GCS 수신, 시계/손 움직임 | 새 프레임 표시, 설정 fps/지연 목표 충족 | 수신 기록/fps/CPU/온도 |
| T7 장애 분리 | 정지 bench에서 영상 종료, ToF 분리, Gateway/backend/cFS 개별 재시작 | 다른 경로 유지, stale 표시, 규정 재접속, 숨은 명령 재송신 없음 | 장애 시각/journal |
| T8 동시 부하 | 전체 서비스/GCS/bag 30분 | crash/OOM 없음, 지속 메모리 증가 없음, 누락/지연 목표 충족 | sysstat/bag/온도/summary |
| T9 MCU 보호 | 비구동 HIL에서 health 중단, health 유지+motion 중단, 재부팅 | 확정한 MCU 계약 충족. Gateway 연결 끊김을 자동 STOP으로 오인하지 않음 | MCU log/출력 계측 |
| TP1 payload 모사 | pseudo-terminal MCU로 정상/분할/CRC 오류/과대 길이 frame 주입 | decoder 복구, 실제 응답만 유효, queue 상한 유지 | simulator와 cFS log |
| TP2 payload 종단 | 확정 opcode로 요청, 중복 request와 완료/실패 응답 | accepted와 completed 구분, ID 일치, 중복 동작 없음 | GCS/SB/UART log |
| TP3 payload 복구 | UART 끊김/MCU reset/cFS app 재시작 | timeout 상태, STATUS 재조회, 과거 START 자동 재전송 없음 | 상태 전이 log |
| TP4 payload 격리 | sample burst/느린 저장과 전체 stack 동시 실행 | bounded drop counter, Control·odom·영상 목표 유지 | queue/latency/CPU 통계 |

주파수·지연·정확도의 합격값을 Pi 실측 완료처럼 쓰지 않는다.
**초기 제안값**은 EKF 목표 50 Hz에 지속 45 Hz 이상, ToF 목표 5 Hz에 4.5 Hz 이상,
명령 결과 1초 이내, 1 Hz 상태는 3초 초과 시 stale 표시, low 영상 지연 500 ms 이하다.
센서 입력률은 MCU sampling 사양에서 확정한다. 정지 drift, 1 m 직진, 90도 회전의
허용오차와 재접속 시간은 P0~P3에서 결정하여 설정에 보존한다.
**정확도 기준 미설정은 PASS가 아니다.** 합의한 측정 환경과 profile을 결과에 남긴다.

### C. 포팅 시 제공할 통합 테스트 runner

기존 GCS smoke만으로 전체 pipeline을 검사할 수 없다. 다음을 구현 산출물에 포함한다.
아래는 **신규 구현 예정 파일**이며 지금 실행 가능한 도구가 아니다.

| 계획 파일 | 역할 |
| --- | --- |
| `platforms/loonar/scripts/preflight.sh` | OS/arch/의존성/SDK/권한/units/socket/ROS 환경 검사. 운동 명령 없음 |
| `platforms/loonar/tests/pipeline_smoke.py` | mock/live-readonly 분리, cFS/실제 상태/stamp 진행/TF 소유권/topic freshness 확인 |
| `platforms/loonar/tests/motion_acceptance.py` | 명시적 `--move`에서만 Gateway 경유 primitive 시험. 완료/중단 STOP, 외부 GT 비교 |
| `platforms/loonar/tests/soak.sh` | 30분 동시 부하, 기록 용량 제한, CPU/RSS/온도/topic gap 집계 |
| `platforms/loonar/tests/payload_simulator.py` | 실제 wire 계약을 구현한 pseudo-terminal MCU. 정상/오류/분리/중복 요청 시나리오 |
| `platforms/loonar/tests/payload_acceptance.py` | `--sim`과 실기 모드 분리. GCS→cFS→transport→MCU→GCS 결과 검증 및 TP1~TP4 기록 |

각 runner는 timeout, 실패 시 nonzero 종료 코드, `PASS/FAIL/SKIP/BLOCKED`와 실패 위치를
출력한다. `results/<UTC-run-id>/summary.json`에 repo 버전/미커밋 차이, OS/kernel/arch,
apt 목록, cFS commit, SDK SHA256, 설정, topic 통계, GCS/cFS/systemd 로그, bag 경로를 남긴다.
mock 성공, 센서 미연결, 미구현, 하드웨어 불합격을 구별한다.
운용 socket/port/장치와 충돌하면 종료하고 기존 프로세스를 임의로 끄지 않는다.
영상 원격 표시는 GCS receiver 결과나 운용자 확인이 필요하며 송신 측만으로 PASS하지 않는다.

## 10. 릴리스와 되돌리기

Pi native release manifest에 repo 차이를 포함한 소스 버전, cFS/SDK/ROS/apt 버전,
MCU firmware/wire version, unit/config hash, camera stack 버전을 기록한다.
`/opt/loonar/current`를 바꾸기 전에 명시적 STOP과 구동 정지를 확인하고 stack을 종료한다.
전환 후 T0/T1/T2/T4를 다시 수행하고 실패하면 이전 release와 설정으로 복원한다.
MCU wire를 바꾼 경우 Pi 바이너리만 되돌리지 않고 호환 firmware와 함께 복원한다.
SDK/camera stack의 라이선스와 재배포 조건은 배포 방식 확정 시 확인한다.

## 11. 이번 조사에서 실시한 검증

실행 환경은 개발 PC의 **x86_64**다. Pi나 차량에 접속하거나 배포하지 않았다.

| 검증 | 결과 | 검증하지 않은 범위 |
| --- | --- | --- |
| 새 `build/loonar-porting-review`의 CMake build/CTest | **15/15 PASS** | ARM64 실행, 실제 MCU 제어 |
| 기존 빌드의 실제 cFS로 `tools/gcs_test/smoke.py` | **PASS**: mode/sequence/synthetic voltage/UDP TS/cleanup | Pi 재빌드, 실제 battery/odom, 카메라/원격 GCS 표시 |
| SDK archive ELF 확인 | `libCubeEye.so`는 ELF64 AArch64 | Pi 의존성 해결/USB 수신 |
| SDK 2.5.9 header와 `capture_xyz.cpp`의 `g++ -fsyntax-only` | **PASS** | ARM64 link, 실행 중 SDK ABI 호환성 |

병합 후 재검증에서 별도 clean worktree의 CTest 15개, 공통 localization 20개,
odom V1/V2/C 분석 10개 및 기존 실제 cFS smoke가 통과했다. 이 결과에 신규 payload
통신 앱 시험은 포함되지 않는다. AprilTag는 18개 통과, 격리 ROS 환경이 필요한 1개는
건너뛰었다. 상세 범위는 [병합 기록](../../../docs/main-master-merge-20260918.md)에 남긴다.

다음 작업은 P0 의존성·Pi SDK/CSI 확인, P1 공통부 ARM64 재빌드와 PL0 payload 계약 확정이다.
P2의 실측 wire/MCU 구현이 끝나기 전에는 실제 차량의 odom/주행까지 이식했다고 판단하지 않는다.
