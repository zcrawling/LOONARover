# Control MCU-MPU Minimal Wire Protocol v1

상태: **현 LOONAR HW v1 기준자료 — Gateway 이관 전 개정 필요**  
확정일: 2026-08-25

## 1. 범위와 원칙

이 문서는 기존 LOONAR Control MCU UART byte stream의 기준자료다. 최종 구조에서는
`vehicle_gatewayd`의 `TeensyRs485Backend`만 이 link를 열며 cFS, ROS 2, GCS는 장치에 직접 접근하지 않는다. 목표는
`RX -> Controller -> TX` 흐름을 짧고 결정론적으로 검증하는 것이다.

v1에는 다음 세 메시지만 존재한다.

1. MPU가 살아 있음을 알리는 `MPU_HEALTH`
2. MPU가 목표 속도를 전달하는 `MOTION_CMD`
3. MCU가 실제 적용 상태를 돌려주는 `MCU_STATUS`

v1에는 time sync, epoch, TTL, mode, trace, ACK, command result와 fault event가 없다.
`project.md`가 요구하는 독립 MCU command lease를 충족하려면 기존 payload를 바꾸지 않고
protocol version을 올려야 한다.

## 2. 물리 링크

| 항목 | v1 값 |
| --- | --- |
| 물리 계층 | MAX3490E 기반 4-wire full-duplex RS-485 |
| UART | 2,000,000 baud, 8-N-1 |
| Byte order | Little Endian |
| 동적 메모리 | 사용 금지 |

현재 Control Teensy adapter는 `Serial1`의 기본 pin RX 0/TX 1과 interrupt-driven 고정 buffer를
사용한다. 전체 pin map은 `firmware/control/include/loonar/control/board_pins.h`에서만 관리한다.
향후 DMA로 교체해도 이 wire byte 형식은 바뀌지 않는다.

## 3. Packet

### 3.1 형식

| Offset | Field | Type | Size | 고정 규칙 |
| ---: | --- | --- | ---: | --- |
| 0 | `SYNC` | `uint16` | 2 | `0xA55A`; wire는 `5A A5` |
| 2 | `VERSION` | `uint8` | 1 | `1` |
| 3 | `MSG_ID` | `uint8` | 1 | 4장 참조 |
| 4 | `PAYLOAD_LEN` | `uint16` | 2 | 최대 32 |
| 6 | `SEQ` | `uint32` | 4 | 송신 방향별 packet sequence |
| 10 | `PAYLOAD` | bytes | N | 메시지별 고정 크기 |
| 10+N | `CRC32C` | `uint32` | 4 | Header와 payload 전체 |

Header는 10 byte, 최대 packet은 46 byte다. C struct의 메모리 이미지를 wire에 복사하지 않고
field를 하나씩 직렬화한다.

`SEQ`는 각 송신기가 1부터 시작해 packet마다 증가시키고 overflow 후 1로 돌아간다. 0은
아직 송신/수신한 packet이 없음을 나타낸다. Sequence gap은 관측값일 뿐 motor 차단 조건이 아니다.

### 3.2 CRC32C

- Castagnoli reflected polynomial: `0x82F63B78`
- initial: `0xFFFFFFFF`
- final XOR: `0xFFFFFFFF`
- CRC field: Little Endian
- 표준 vector `123456789`: `0xE3069283`

고정 packet vector:

```text
MPU_HEALTH, seq=1, uptime_ms=0x12345678
5A A5 01 10 04 00 01 00 00 00 78 56 34 12 FD 8E 28 7B
```

### 3.3 Stream parser

- `5A A5`를 찾은 뒤 header, payload, CRC 순서로 검사한다.
- version, length 또는 CRC가 틀리면 한 byte 전진해 다음 sync를 찾는다.
- partial frame은 20 ms 후 폐기한다.
- parser storage는 92 byte(`2 * 최대 packet`)로 고정한다.
- heap 할당, 무제한 length 대기와 무제한 buffer 확장은 금지한다.

## 4. Message 목록

| ID | Message | 방향 | Payload | 기본 주기 |
| ---: | --- | --- | ---: | --- |
| `0x10` | `MPU_HEALTH` | MPU -> MCU | 4 B | 10 Hz |
| `0x20` | `MOTION_CMD` | MPU -> MCU | 8 B | latest-value, 권장 20-50 Hz |
| `0x80` | `MCU_STATUS` | MCU -> MPU | 28 B | 20 Hz |

그 외 ID는 v1에서 reserved이며 수신 시 무시하고 `rx_error_count`를 증가시킨다.

## 5. MPU_HEALTH

| Offset | Field | Type | Size | 의미 |
| ---: | --- | --- | ---: | --- |
| 0 | `uptime_ms` | `uint32` | 4 | MPU monotonic uptime; 진단용 |

MCU는 payload의 시간을 안전 판정에 사용하지 않는다. CRC와 payload 길이가 정상인 health를
받은 MCU local time만 기록한다. 마지막 정상 health 수신 후 500 ms를 초과하면 motor 출력은 0이다.

## 6. MOTION_CMD

| Offset | Field | Type | Size | 단위/방향 |
| ---: | --- | --- | ---: | --- |
| 0 | `linear_velocity_mps` | `float32` | 4 | 전진 양수, m/s |
| 4 | `yaw_rate_radps` | `float32` | 4 | 반시계 양수, rad/s |

가장 최근의 정상 명령 하나만 유지한다. NaN과 Inf는 malformed payload로 무시한다. v1에서는
TTL, range clamp, epoch, mode와 duplicate 판정을 하지 않는다. Health가 정상이고 온도가
95°C 미만인 동안 마지막 정상 명령을 계속 적용한다.

## 7. MCU_STATUS

| Offset | Field | Type | Size | 의미 |
| ---: | --- | --- | ---: | --- |
| 0 | `uptime_ms` | `uint32` | 4 | MCU monotonic uptime |
| 4 | `last_command_seq` | `uint32` | 4 | 마지막 정상 `MOTION_CMD` packet sequence; 없으면 0 |
| 8 | `board_temp_mdeg_c` | `int32` | 4 | MCU 온도, °C x 1000 |
| 12 | `state` | `uint8` | 1 | 0 STOPPED, 1 ACTIVE |
| 13 | `inhibit_flags` | `uint8` | 1 | 아래 두 bit만 허용 |
| 14 | `reserved` | `uint16` | 2 | 항상 0 |
| 16 | `applied_linear_velocity_mps` | `float32` | 4 | 안전 gate 후 controller에 전달한 지령; 측정값 아님 |
| 20 | `applied_yaw_rate_radps` | `float32` | 4 | 안전 gate 후 controller에 전달한 지령; 측정값 아님 |
| 24 | `rx_error_count` | `uint32` | 4 | frame/CRC/payload/timeout 누적 오류 |

`inhibit_flags`:

| Bit | 이름 | 조건 |
| ---: | --- | --- |
| 0 | `HEALTH_TIMEOUT` | health 미수신 또는 마지막 수신 후 500 ms 초과 |
| 1 | `OVERTEMP` | MCU 온도 95,000 m°C 이상 |

다른 inhibit/fault bit는 v1에 존재하지 않는다.

## 8. 제어 규칙

Motor 출력을 0으로 만드는 조건은 정확히 두 개다.

1. `MPU_HEALTH` timeout
2. MCU 온도 95°C 이상

둘 중 하나라도 참이면 `state=STOPPED`이고 적용 속도는 `(0, 0)`이다. 두 조건이 모두
해제되면 마지막 정상 motion command를 다시 적용한다. v1은 overtemperature latch나
hysteresis를 두지 않는다. CRC 오류나 malformed packet은 무시하고 계수하며, 별도의 안전
상태를 만들지 않는다.

## 9. FreeRTOS 데이터 흐름

```text
Serial1 interrupt RX buffer
  -> RX task: bounded parser + payload decode
  -> depth-1 health/motion latest queues
  -> Controller task: 100 Hz, 두 차단 조건 평가, TBD controller, motor HAL
  -> depth-1 status snapshot queue
  -> TX task: MCU_STATUS encode + Serial1 interrupt TX buffer
```

- RX task만 parser를 소유한다.
- Controller task만 command와 적용 상태를 소유한다.
- TX task만 UART TX를 시작한다.
- task와 queue는 모두 `xTaskCreateStatic`/`xQueueCreateStatic`으로 생성한다.
- UART ISR은 Teensy `HardwareSerial`이 소유한다. packet parse와 제어 계산은 task에서만 한다.

## 10. 구현 고정값과 board TBD

Wire 및 제어 구조에서 확정된 값:

- packet layout, endian, CRC와 세 message payload
- 최대 payload 32 B, parser 92 B, RX scratch 64 B
- health timeout 500 ms
- overtemperature threshold 95°C
- Controller 100 Hz, Status 20 Hz
- latest queue depth 1, 정적 할당

Board adapter에서만 남은 TBD:

- 실제 Control PCB에 맞춘 pin/polarity 확인
- HIL 측정 후 DMA 필요 여부와 필요 시 channel/ring/cache 처리
- encoder/BNO085 acquisition
- `(linear, yaw)`를 wheel duty로 변환하는 실제 controller

위 TBD를 결정할 때 wire packet이나 세 task 사이의 데이터 소유권은 변경하지 않는다.
