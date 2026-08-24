# LOONAR MPU Implementation Plan

## 1. 목표

Framework별 완성 후 통합하지 않고, 실행 가능한 end-to-end 경로를 하나씩 추가한다. 각 단계는 bounded resource, stale command 차단, 장애 격리를 함께 증명해야 완료된다.

## 2. 고정 제약

- Ubuntu 24.04 arm64 + ROS 2 Jazzy
- systemd unit 4개: `mcu-io`, `cfs`, `ros2`, `camera`
- cFS App 3개: `LNR_CTRL`, `LNR_IO`, `GCS_IF`
- serial과 Camera의 single owner
- 모든 motion은 cFS 승인 경로 사용
- Control/Payload link 완전 분리
- cFS는 control plane만 수용
- queue와 retry는 모두 상한 보유

## 3. 구현 순서

| Slice | 결과물 | 통과조건 |
| ---: | --- | --- |
| 0 | build, catalog, common IPC | clean build + contract test |
| 1 | `mcu-io` + virtual Control MCU | health/motion/status SIL |
| 2 | cFS 3-App + GCS MANUAL | operator→MCU end-to-end |
| 3 | ROS bridge + AUTO candidate | Nav2→MCU end-to-end |
| 4 | I200DK Jazzy port + localization | point cloud와 quality gate |
| 5 | Payload vertical slice | start/status/sample/file |
| 6 | Camera Vision/Video | bounded tee와 장애 격리 |
| 7 | kill/fault/HIL/soak | 안전정지와 자원 상한 |

## 4. Slice 0 — Foundation

### 구현

- Ubuntu 24.04 arm64 build image와 dependency lock
- `interfaces/catalog/` numeric ID source와 generator
- 공통 8-byte IPC header codec
- `SOCK_SEQPACKET` peer credential/HELLO helper
- monotonic time, boot ID, sequence, request ID helper
- four-service unit skeleton과 log/resource limit

### 완료조건

- clean checkout에서 host build와 test 재현
- C/C++의 header golden vector 일치
- duplicate/reserved ID 0건
- unbounded queue 또는 외부 입력 경로 0건

## 5. Slice 1 — Control Link

### 구현

- `mcu-io` 단일 epoll loop
- 공통 `link.c`와 Control instance
- serial nonblocking reconnect
- `control.sock`, `sensors.sock`
- virtual MCU/PTY test executable
- 기존 `wire_c`와 Control firmware 연결

### 시나리오

1. `MPU_HEALTH` 송신
2. 승인 motion 최신값 송신
3. `MCU_STATUS` 수신과 적용 sequence 확인
4. `mcu-io` kill/serial disconnect 후 MCU 500 ms timeout 정지
5. reconnect 후 새 motion 전까지 0 유지

### 완료조건

- wire fuzz/CRC/fragmentation 통과
- 30분 SIL에서 memory 증가 없음
- reconnect 후 과거 motion 적용 0건

## 6. Slice 2 — MANUAL과 GCS

### 구현

- `LNR_CTRL` mode/authority/arbiter/safety 순수 모듈
- `LNR_IO` cFS SB↔local IPC
- `GCS_IF` TLS session, role, lease, command/tlm
- GCS CLI 또는 최소 operator client
- `SYSTEM_STATUS`와 critical event

### 시나리오

```text
GCS lease + velocity
  -> GCS_IF MANUAL_CANDIDATE
  -> LNR_CTRL 승인
  -> LNR_IO
  -> mcu-io
  -> virtual/real Control MCU
```

lease, command TTL, mode, epoch, MCU readiness 중 하나라도 무효이면 0속도를 승인한다.

### 완료조건

- ROS가 종료된 상태에서 MANUAL 유지
- GCS disconnect/lease timeout 후 요구시간 내 정지
- velocity flood에서 memory 상한 유지
- cFS 재시작 후 새 lease 전 motion 0건

## 7. Slice 3 — ROS AUTO

### 구현

- `loonar_bridge` sensor IPC와 cFS IPC
- IMU와 wheel odometry topic
- `robot_localization`, URDF, 단일 TF authority
- Nav2 `/cmd_vel_nav`을 AUTO candidate로 변환
- ROS readiness와 diagnostics

### 완료조건

- Nav2 candidate가 승인 전 MCU에 도달하지 않음
- localization invalid 또는 ROS kill 시 AUTO 정지
- 같은 조건에서 MANUAL 전환 가능
- timestamp/unit/QoS contract 통과

## 8. Slice 4 — I200DK Port

### 8.1 Port Gate

장비 수령 즉시 다음을 기록한다.

- SDK/driver source 확보 범위와 license
- arm64 library 존재 여부와 linked dependency
- Ubuntu 22.04/Humble reference build 결과
- USB protocol이 SDK 없이 접근 가능한지 여부

Noble용 SDK core를 build/load할 수 있어야 wrapper 포팅을 진행한다. 22.04 전용 binary만 있고 source/protocol이 없으면 공급사 지원 없이는 block으로 판정한다.

### 8.2 Port 작업

- CMake/package manifest를 Jazzy와 C++17 기준으로 정리
- ROS API를 표준 depth image, camera info, PointCloud2로 한정
- OpenCV/PCL/Boost와 ament dependency 수정
- udev/device reconnect와 parameter/launch 정리
- frame ID, unit, invalid point, timestamp source 명시
- driver core와 ROS wrapper 분리

### 8.3 Integration

- Wheel+IMU를 primary odometry로 유지
- I200DK registration 결과는 quality가 유효할 때만 correction에 사용
- rough/featureless/sunlight dataset에서 reject 조건 측정
- recovery의 RELOCALIZE 단계와 연결

### 완료조건

- Jazzy arm64에서 30분 point cloud 발행
- cable reconnect 후 자동 복구
- malformed/empty frame에서 crash 없음
- quality invalid 시 AUTO correction 적용 0건

## 9. Slice 5 — Payload

### 구현

- `mcu-io` Payload link instance
- HEARTBEAT/COMMAND/STATUS/SAMPLE codec
- cFS Payload activity state
- bounded rotating raw writer
- opaque file ID와 공통 Bulk/File transfer

### 완료조건

- start→running→complete/fault가 GCS에 표시
- command dedup과 restart 재동기화
- disk stall/queue full이 Control latency에 영향 없음
- Payload link kill 중 drive 유지

## 10. Slice 6 — Camera

### 구현

- libcamera/GStreamer capture pipeline
- latest-frame Vision branch depth 1
- hardware encoder와 authenticated video token
- Camera status와 drop/restart counter

### 완료조건

- Vision/GCS consumer 정지 시 capture nonblocking
- video 정체가 Vision/drive에 영향 없음
- 30분 thermal/CPU/memory 측정 통과
- copy 비용이 요구를 넘을 때만 zero-copy 최적화 승인

## 11. Slice 7 — Fault, HIL, Soak

- cFS, ROS, `mcu-io`, Camera 개별 kill
- Control/Payload cable 분리와 CRC burst
- GCS packet loss와 reconnect
- CPU, storage, network, thermal pressure
- real MCU/RS-485 timing과 motor interlock
- I200DK/Camera 동시 부하
- brownout와 MPU reboot

완료조건은 `verification_gates.md`의 모든 mandatory Gate 통과다.

## 12. 공통 구현 규칙

- production 경로에는 test transport 다형성을 넣지 않는다.
- pure state logic은 clock/I/O를 인자로 받아 unit test한다.
- periodic state는 latest, discrete event는 bounded FIFO를 사용한다.
- 상태·source·reason이 바뀔 때만 event를 발행한다.
- external string으로 shell, path, device, unit을 선택하지 않는다.
- config에는 version, 범위, default, owner, reload 정책을 둔다.

## 13. 병렬 작업 경계

Control 기반 Slice 0~2는 순차 진행한다. 이후 다음은 interface가 고정되면 병렬 가능하다.

- ROS bridge/Nav2
- I200DK port
- Payload MCU와 record writer
- Camera pipeline
- GCS UI

각 branch는 실제 control path를 우회하는 임시 direct writer를 만들지 않는다.

## 14. 완료 정의

각 Slice는 코드가 build되는 것만으로 끝나지 않는다.

1. public schema와 owner 문서화
2. unit/contract/integration test
3. timeout/restart/overflow test
4. CPU/memory/queue counter 관측
5. clean start/stop과 stale replay 0건
6. 관련 문서와 catalog 동시 갱신
