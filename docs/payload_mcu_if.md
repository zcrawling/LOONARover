# Payload MCU Interface

## 1. 범위

Payload MCU는 sensor acquisition과 local task를 담당한다. MPU에서는 `mcu-io`가 serial owner, `LNR_IO`가 cFS 변환, `LNR_CTRL`이 activity state와 명령권한을 담당한다. Payload 장애와 raw data burst는 Control 링크와 주행을 막지 않는다.

## 2. Link 분리

Payload는 Control MCU와 별도 UART, transceiver, parser, RX/TX buffer, health state를 사용한다. wire framing과 CRC 구현은 공통 `wire_c`를 재사용할 수 있지만 link instance는 공유하지 않는다.

## 3. 초기 wire message

| Message | 방향 | 내용 | Queue |
| --- | --- | --- | --- |
| `HEARTBEAT` | 양방향 | uptime, state, fault 요약 | latest 1 |
| `COMMAND` | MPU → MCU | activity 시작/중지와 config | bounded FIFO |
| `STATUS` | MCU → MPU | activity 진행률, 결과, fault | latest + transition |
| `SAMPLE` | MCU → MPU | sensor sample 또는 block | bounded byte queue |

wire header, endian, CRC, 최대 payload는 실제 Payload sample 크기를 측정한 뒤 catalog에 고정한다. 동적 할당과 무제한 length는 허용하지 않는다.

## 4. COMMAND

```text
request_id: uint64
activity_id: uint64
opcode: enum { START, STOP, SET_PROFILE }
profile: fixed enum
parameter_length: uint16
parameters: bounded bytes
```

MCU는 `request_id`를 dedup한다. 재연결 후 MPU는 과거 START를 자동 재전송하지 않고 STATUS를 먼저 읽은 뒤 operator/mission의 새 요청으로 상태를 맞춘다.

## 5. STATUS

```text
activity_id
state: IDLE | RUNNING | COMPLETE | FAULT
progress_permille
last_request_id
result_code
fault_bits
last_sample_sequence
```

`LNR_CTRL`이 최종 PayloadState를 소유한다. MCU STATUS와 cFS activity가 불일치하면 새 동작을 시작하지 않고 상태를 `FAULT` 또는 `IDLE`로 명시적으로 재동기화한다.

## 6. SAMPLE과 raw record

SAMPLE의 최소 필드:

```text
schema_version
sample_sequence
acquisition_time_ns
validity
payload_length
payload
```

`mcu-io`의 선택적 writer는 고정 header + payload record를 rotating file에 순차 저장한다. writer queue는 byte 상한을 가지며 disk가 느리면 sample을 drop하고 counter를 증가시킨다. Control event loop는 disk 완료를 기다리지 않는다.

## 7. 파일 전송

저장 파일은 opaque `file_id`로만 노출한다. 목록, hash, resume offset, quota, download는 Payload 전용 코드가 아니라 공통 Bulk/File worker가 처리한다. cFS에는 file metadata와 transfer 결과만 전달한다.

## 8. GCS 명령과 결과

GCS 요청은 `GCS_IF -> LNR_CTRL -> LNR_IO -> mcu-io -> Payload MCU` 경로를 사용한다.

- 즉시 검증 결과: `ACCEPTED` 또는 `REJECTED`
- activity 종료 결과: `COMPLETED` 또는 `FAILED`
- 장시간 작업: STATUS의 progress만 갱신

모든 velocity packet처럼 불필요한 개별 ACK를 만들지 않으며, discrete Payload 요청에만 `request_id`를 사용한다.

## 9. 장애 동작

| 장애 | 동작 |
| --- | --- |
| Payload heartbeat loss | activity `FAULT`, drive 유지 |
| malformed/CRC burst | packet reject, counter 증가, bounded reconnect |
| record queue full | raw sample drop, 상태·Control 링크 유지 |
| storage full | 기록 중지와 fault 통보, acquisition 정책은 config대로 유지 |
| MPU/cFS restart | STATUS 재조회 전 activity command 금지 |

## 10. 검증

- command dedup과 reconnect 재동기화
- sample sequence gap과 validity 기록
- disk stall에서 Control latency 변화 없음
- queue byte 상한과 drop counter
- START/STOP/COMPLETE/FAULT end-to-end GCS 표시
- Payload link fault가 Control link에 전파되지 않음
