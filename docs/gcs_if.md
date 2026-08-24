# Ground Control Station Interface

## 1. 구성

GCS control, telemetry, discrete command, bulk metadata는 `GCS_IF`의 인증된 연결 하나에서 multiplex한다. Video는 `camera.service`, file data는 Bulk/File worker의 별도 data path를 사용한다.

```text
GCS
  -> authenticated connection -> GCS_IF -> LNR_CTRL/LNR_IO
  -> short-lived video token -> camera.service
  -> authorized file_id/range -> Bulk/File worker
```

## 2. Session

초기 transport는 TLS 1.3 reliable connection과 length-prefixed frame을 사용한다. session은 다음 값만 보유한다.

- `session_id`
- authenticated operator identity와 role
- connection boot nonce
- MANUAL `lease_id`와 expiry
- receive/transmit sequence
- last applied manual sequence

재연결은 새 session이다. 이전 lease, 미완료 velocity, confirmation token을 복원하지 않는다.

## 3. Frame

```text
protocol_version
channel: CONTROL | CRITICAL_TLM | MISSION_TLM
message_type
payload_length
sequence
payload
```

연결별 TX queue는 bounded다. 우선순위는 `CONTROL > CRITICAL_TLM > MISSION_TLM`이며 낮은 우선순위의 오래된 snapshot부터 버린다. Control frame이 queue 상한을 넘으면 session을 종료하고 lease를 만료시킨다.

## 4. MANUAL lease

MANUAL 진입 전에 권한 있는 operator가 lease를 획득한다. lease는 단일 session에만 연결되고 짧은 주기로 갱신한다. GCS 연결, lease 또는 command가 만료되면 `LNR_CTRL`은 0속도를 승인한다.

MANUAL velocity packet:

```text
lease_id
sequence
valid_for_ms
linear_mps
yaw_rate_radps
```

각 velocity packet에 결과 메시지를 보내지 않는다. `SYSTEM_STATUS`가 `last_received_manual_sequence`, `last_applied_manual_sequence`, decision/reason을 제공한다.

## 5. Discrete request

```text
request_id
type
bounded parameters
confirmation_token   # 위험 동작에만 존재
```

결과 상태는 네 개다.

- `ACCEPTED`
- `REJECTED`
- `COMPLETED`
- `FAILED`

Payload activity, recovery, file export처럼 오래 걸리는 작업은 별도 progress snapshot을 제공한다. 같은 `request_id` 재수신은 이전 결과를 반환하고 다시 실행하지 않는다.

## 6. 권한

| Role | 허용 |
| --- | --- |
| observer | telemetry, video 보기 |
| operator | mode, MANUAL lease, Payload activity |
| maintainer | 사전 정의 service restart, log/file 요청 |
| admin | MPU reboot와 credential 관리 |

role 검사는 `GCS_IF`에서 하고 platform 실행부는 고정 action enum을 다시 검사한다. 외부 입력으로 shell, path, unit 이름을 받지 않는다.

## 7. Telemetry

### Critical TLM

- RoverMode, command source, lease/epoch
- MCU link, inhibit/fault, applied motion
- cFS/mcu-io/ROS readiness
- battery/temperature와 safety reason
- last manual received/applied sequence

### Mission TLM

- localization/navigation quality
- PayloadState, progress, sample/file summary
- Camera/video health
- queue drop, reconnect, storage counter

주기 상태는 latest snapshot으로 대체할 수 있다. fault와 상태전이는 event FIFO로 보존한다.

## 8. Video와 Bulk

`GCS_IF`는 인증된 요청에 대해 짧은 수명의 video token과 허용 profile을 발급한다. encoded video는 Camera data path에서 직접 전송하며 control/tlm queue를 사용하지 않는다.

Bulk 요청은 `file_id`, offset, length로 제한한다. worker는 path를 외부에 노출하지 않고 hash와 resume range를 검증한다. bandwidth limit으로 Critical TLM을 침해하지 않는다.

## 9. 안전 동작

| 조건 | 결과 |
| --- | --- |
| authentication 실패 | session 생성 안 함 |
| sequence 역행/중복 velocity | packet 폐기 |
| lease/command timeout | 0속도 승인 |
| mode 또는 epoch 불일치 | motion 거부와 reason 갱신 |
| GCS 재연결 | 새 lease 전 motion 금지 |
| video/bulk congestion | 해당 data path만 degrade |

## 10. 검증

- 인증/role/lease 만료 table test
- velocity flood에서 bounded memory와 최신값 적용
- session reconnect 후 과거 명령 적용 0건
- discrete request dedup
- telemetry 우선순위와 drop 정책
- video/bulk 포화 중 Control latency와 Critical TLM 유지
- ROS down 상태에서 MANUAL end-to-end 동작
