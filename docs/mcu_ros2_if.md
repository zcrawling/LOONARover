# MPU Native I/O and ROS 2 Interface

## 1. 실행영역

| systemd unit | 단일 책임 |
| --- | --- |
| `mcu-io.service` | Control/Payload serial owner와 local IPC |
| `cfs.service` | 임무·권한·안전·GCS control plane |
| `ros2.service` | 센서 변환, localization, navigation, perception |
| `camera.service` | Camera capture, Vision frame, GCS video |

기능별 systemd unit은 추가하지 않는다. 각 실행영역 내부의 모듈, cFS App, ROS node로 확장한다.

## 2. mcu-io 구조

`mcu-io`는 C 또는 C++ 단일 binary와 단일 `epoll` event loop로 구현한다.

```text
mcu_io/
  main.c          epoll loop, timer, signal, lifecycle
  link.c          공통 serial link 상태기계
  serial.c        termios, nonblocking read/write, reconnect
  ipc.c           SOCK_SEQPACKET server와 peer 검사
  health.c        age, error, reconnect counter
  record_writer.c 선택적 Payload raw writer
```

`link.c`는 Control과 Payload에 두 번 instantiate하지만 다음 상태는 절대 공유하지 않는다.

- serial file descriptor
- RX parser와 scratch buffer
- TX queue
- sequence와 reconnect state
- error/health counter

disk write만 bounded worker thread로 분리할 수 있다. 직렬 I/O와 IPC는 event loop에서 nonblocking으로 처리한다.

## 3. Backend 정책

운용 binary는 실제 serial 경로만 포함한다. 단위시험은 `read`/`write` callback을 주입하고, SIL은 PTY 또는 Unix shim을 사용한다. 기록 재생은 별도 test executable이 PTY에 wire byte를 공급한다. Gazebo virtual MCU도 실제 wire codec을 사용한다.

이 원칙으로 운용 코드에 transport 상속계층과 사용하지 않는 구현을 넣지 않는다.

## 4. Local IPC

모든 endpoint는 Unix domain `SOCK_SEQPACKET`, nonblocking, bounded queue를 사용한다.

| Endpoint | Producer/Consumer | 내용 | 정책 |
| --- | --- | --- | --- |
| `/run/loonar/control.sock` | `LNR_IO` ↔ `mcu-io` | 승인 motion, MCU status | TX/RX latest 1 |
| `/run/loonar/sensors.sock` | `mcu-io` → `loonar_bridge` | IMU, encoder sample | bounded latest/ring |
| `/run/loonar/payload.sock` | `LNR_IO` ↔ `mcu-io` | Payload command/status | command FIFO, status latest |
| `/run/loonar/ros-cfs.sock` | `loonar_bridge` ↔ `LNR_IO` | AUTO candidate, system state | latest + bounded event |

Control과 Payload endpoint는 합치지 않는다. Payload burst나 parser fault가 motion 경로의 queue와 lock을 점유하면 안 된다.

### 4.1 공통 header

| Field | Type | Size |
| --- | --- | ---: |
| `version` | `uint8` | 1 |
| `message_type` | `uint8` | 1 |
| `payload_length` | `uint16` | 2 |
| `sequence` | `uint32` | 4 |

공통 header는 8 byte다. packet boundary는 socket이 보존한다. peer identity는 `SO_PEERCRED`로 확인하고 연결 직후 `HELLO`의 전체 `boot_id`를 교환한다. 매 packet에 process name, boot ID, 일반 목적 timestamp를 반복하지 않는다.

### 4.2 메시지별 필드

- motion: `control_epoch`, `valid_for_ms`
- discrete request: `request_id`
- sensor: `sample_sequence`, `acquisition_time_ns`, `validity`
- status: validity bit와 `reason`
- Payload: `activity_id` 또는 `sample_sequence`

`mcu-io` reconnect 시 송신 queue와 마지막 승인 motion을 지우고, 새로운 `HELLO`가 끝날 때까지 motion을 전달하지 않는다.

## 5. loonar_bridge

초기 ROS 2 custom node는 `loonar_bridge` 하나다.

```text
sensor IPC -> IMU/encoder decode -> /imu/data, /odom/wheel
Nav2 velocity -> candidate encode -> ros-cfs IPC
cFS state IPC -> /loonar/system_status, diagnostics
Payload state IPC -> /loonar/payload_status
```

wheel tick에서 differential odometry를 계산하되 `odom -> base_link` TF는 발행하지 않는다. 최종 TF는 `robot_localization`만 발행한다.

## 6. ROS 2 node 경계

| Node | 책임 |
| --- | --- |
| `loonar_bridge` | MPU IPC와 ROS 표준 topic 변환 |
| `robot_state_publisher` | URDF static/kinematic TF |
| `robot_localization` | Wheel+IMU와 유효한 depth correction 융합, 최종 TF |
| I200DK driver | depth/point cloud 취득 |
| registration/mapper | 조건부 위치보정과 terrain layer |
| Nav2 | planning, control, AUTO velocity 생성 |
| Vision node | Camera 최신 frame의 비동기 처리 |

I200DK driver는 ROS 실행영역에 포함한다. Ubuntu 24.04/ROS 2 Jazzy 포팅이 완료되기 전에는 ROS mock source로 interface를 검증한다.

## 7. Topic과 QoS

표준 message를 우선 사용한다.

| Topic | Type | QoS |
| --- | --- | --- |
| `/imu/data` | `sensor_msgs/Imu` | `SENSOR_QOS` |
| `/odom/wheel` | `nav_msgs/Odometry` | `SENSOR_QOS` |
| `/points` | `sensor_msgs/PointCloud2` | `SENSOR_QOS` |
| `/cmd_vel_nav` | `geometry_msgs/TwistStamped` | `STATE_QOS` |
| `/loonar/system_status` | `loonar_msgs/SystemStatus` | `STATE_QOS` |
| `/loonar/payload_status` | `loonar_msgs/PayloadStatus` | `STATE_QOS` |
| `/loonar/events` | `diagnostic_msgs/DiagnosticArray` | `EVENT_QOS` |

필요한 custom type은 `MotionCandidate`, `SystemStatus`, `PayloadStatus`로 제한한다.

| Profile | Reliability | History/Depth | 용도 |
| --- | --- | --- | --- |
| `SENSOR_QOS` | best effort | keep last 5 | IMU, odom, point cloud |
| `STATE_QOS` | reliable | keep last 1 | mode, readiness, status |
| `EVENT_QOS` | reliable | keep last 32 | fault와 상태전이 |

## 8. 시작과 종료

1. `mcu-io`가 serial과 IPC를 열고 link status를 발행한다.
2. cFS가 `INIT`으로 시작해 MCU status를 기다린다.
3. ROS bridge가 IPC `HELLO` 후 sensor topic을 발행한다.
4. localization이 valid가 되면 cFS readiness가 갱신된다.
5. 종료 시 cFS가 0속도를 승인하고 `mcu-io`가 TX를 flush한 뒤 fd를 닫는다.

어떤 재시작에서도 저장된 motion을 자동 복원하지 않는다.

## 9. 자원 제한

- motion latest queue depth 1
- status latest queue depth 1
- event FIFO 기본 depth 32
- sensor ring은 측정 rate와 최악 consumer pause로 산정하고 고정
- payload record queue는 byte 상한과 drop counter 보유
- 모든 socket은 peer별 TX byte 상한과 disconnect 정책 보유

## 10. 시험

- wire golden vector, fragmentation, CRC, reconnect
- 두 link 동시 부하에서 Control latency 격리
- IPC header/length/version/credential contract
- ROS bridge timestamp와 단위 변환
- ROS kill 중 MANUAL end-to-end 유지
- queue 포화 시 memory 상한과 drop counter
- PTY SIL과 실제 serial의 동일 wire 결과
