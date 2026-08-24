# LOONAR Software Execution Plan

## 1. 목표 저장소 구조

```text
interfaces/
  catalog/                 공개 numeric ID source
  generated/               생성 상수와 문서
libs/
  wire_c/                  MCU 공통 wire codec
  ipc_c/                   8-byte header, seqpacket helper
firmware/
  control/                 Control MCU
  payload/                 Payload MCU
mpu/
  native/mcu_io/           serial owner와 epoll loop
  cfs/apps/lnr_ctrl/       mode, authority, safety, recovery
  cfs/apps/lnr_io/         local IPC와 SB 변환
  cfs/apps/gcs_if/         authenticated GCS control plane
  ros2/loonar_bridge/      MPU↔ROS bridge
  ros2/loonar_msgs/        최소 custom message
  camera/                  libcamera/GStreamer pipeline
  systemd/                 네 unit과 고정 helper policy
tests/
  unit/                    pure logic, codec
  contract/                schema/golden vector
  sil/                     PTY, virtual MCU, multi-process
  hil/                     실제 장비 runner와 checklist
tools/
  gen_catalog.py
  virtual_mcu/
  replay_to_pty/
```

디렉터리는 해당 Slice가 시작될 때 만든다. 빈 framework skeleton을 미리 대량 생성하지 않는다.

## 2. 모듈 크기 기준

- source file은 한 owner와 한 상태기계만 가진다.
- 순수 판단 함수와 transport callback을 같은 함수에 섞지 않는다.
- public header는 다른 실행영역이 실제 사용하는 type만 노출한다.
- 동일 endpoint별 class를 만들지 않고 하나의 IPC 구현을 config로 instantiate한다.
- Control/Payload link는 구현을 공유해도 runtime state는 별도 struct다.

## 3. Build target

| Target | 산출물 | Dependency |
| --- | --- | --- |
| `loonar_wire_c` | static library | 없음 |
| `loonar_ipc_c` | static library | libc |
| `mcu-io` | native binary | wire/ipc |
| `lnr_ctrl` | cFS App | cFE/SCH/EVS |
| `lnr_io` | cFS App | cFE/ipc |
| `gcs_if` | cFS App | cFE/TLS library |
| `loonar_bridge` | ROS 2 component | rclcpp/standard msgs/ipc |
| `loonar_camera` | native binary | libcamera/GStreamer |
| `virtual_mcu` | test binary | wire |

## 4. 첫 구현 backlog

### E0 — Contract

1. IPC message type와 cFS MID catalog 작성
2. `ipc_header_t` encode/decode golden vector
3. boot ID/sequence/epoch/request helper
4. queue class별 fixed-capacity container
5. catalog uniqueness CI

### E1 — mcu-io

1. epoll main/timer/signal
2. serial open/config/read/write/reconnect
3. `link_t`와 Control instance
4. `control.sock` server, peer credential, HELLO
5. latest motion과 MCU status routing
6. health/error counters
7. PTY virtual MCU integration test

### E2 — cFS MANUAL

1. `LNR_CTRL` input/output structs
2. mode/authority/arbiter/safety table tests
3. 20~50 Hz App tick과 SB mapping
4. `LNR_IO` control socket mapping
5. `GCS_IF` session/role/lease
6. manual CLI와 critical status
7. full manual SIL

### E3 — ROS AUTO

1. `loonar_msgs` 3개 type
2. `loonar_bridge` sensor and state IPC
3. wheel odometry와 timestamp conversion
4. `robot_localization`/URDF launch
5. Nav velocity candidate mapping
6. ROS kill/AUTO invalidation test

이후 backlog는 `implementation_plan.md`의 Slice 4~7 순서를 따른다.

## 5. 핵심 struct

### IPC header

```c
typedef struct {
    uint8_t version;
    uint8_t message_type;
    uint16_t payload_length_le;
    uint32_t sequence_le;
} lnr_ipc_header_t;
```

struct memory image를 직접 송신하지 않고 field별 encode/decode한다.

### Link state

```c
typedef struct {
    int serial_fd;
    lnr_parser_t parser;
    lnr_fixed_txq_t txq;
    uint32_t rx_sequence;
    uint32_t tx_sequence;
    uint64_t last_rx_ns;
    lnr_link_state_t state;
    lnr_link_counters_t counters;
} lnr_link_t;
```

Control과 Payload는 서로 다른 `lnr_link_t`를 가진다.

### LNR_CTRL tick

```c
lnr_ctrl_output_t lnr_ctrl_tick(
    const lnr_ctrl_input_t *input,
    const lnr_ctrl_state_t *previous,
    const lnr_ctrl_config_t *config,
    uint64_t now_ns);
```

함수 내부에서 SB, socket, clock을 호출하지 않는다.

## 6. Config 파일

| Config | Owner | Reload |
| --- | --- | --- |
| serial path/baud | `mcu-io` | service restart |
| motion limit/TTL | `LNR_CTRL` | validated cFS table 또는 restart |
| GCS role/certificate | `GCS_IF` | session 재생성 |
| ROS frame/calibration | ROS launch/config | lifecycle restart |
| Camera profile | Camera | fixed profile 전환 |
| Payload record quota | `mcu-io` writer | safe runtime update |

모든 값은 범위 검사를 통과해야 하며 invalid config에서는 safe default 또는 startup failure를 명시한다.

## 7. Review checklist

- owner가 둘 이상인 fd/device/topic/TF가 없는가
- motion direct writer가 없는가
- queue depth 또는 byte 상한이 명시됐는가
- timeout이 monotonic clock을 사용하는가
- reconnect가 cache를 비우는가
- periodic message가 불필요한 metadata를 반복하지 않는가
- external input이 shell/path/unit을 선택하지 않는가
- failure가 Control 링크까지 전파되는 shared lock/thread가 없는가

## 8. Pull request 단위

한 PR은 하나의 관찰 가능한 경로 또는 하나의 공통 contract만 다룬다.

- 새 interface: catalog + codec + golden vector
- 새 판단: pure function + table test
- 새 transport: bounded queue + reconnect/fault test
- 새 hardware: mock/SIL 먼저, HIL evidence 추가
- optimization: profiling 수치와 전후 비교 필수

## 9. CI 순서

```text
format/static analysis
  -> catalog check
  -> host unit + sanitizer
  -> contract golden vector
  -> multi-process SIL
  -> target cross-build
```

HIL은 별도 runner에서 같은 commit/config hash로 실행한다.

## 10. Definition of Done

- 요구 경로가 실제 process 경계를 통과해 동작
- happy/fault/restart/overflow test 통과
- memory, queue, drop, latency counter 확인 가능
- stale command와 duplicate action 0건
- target build 또는 명시적 hardware Gate 통과
- 관련 ICD, catalog, 검증 Gate 갱신
