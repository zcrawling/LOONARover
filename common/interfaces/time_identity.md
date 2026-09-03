# Time and Identity Interface

## 1. 원칙

시간과 식별자는 사용 목적이 있을 때만 메시지에 넣는다. timeout은 수신 프로세스의 monotonic clock으로 판정하고, 센서 측정시각은 ROS 경계에서만 ROS Time으로 변환한다.

## 2. 최소 식별자

| 값 | 범위 | 생성자 | 용도 |
| --- | --- | --- | --- |
| `boot_id` | process boot | 각 process | reconnect 시 상대 재시작 식별 |
| `sequence` | stream + boot | producer | gap, duplicate, out-of-order |
| `control_epoch` | command authority | Vehicle Gateway | 이전 권한의 motion 차단 |
| `request_id` | discrete request | 최초 요청자 | dedup과 결과 연결 |
| `activity_id` | Payload/recovery activity | cFS Mission Manager | 장시간 동작 상태 연결 |
| `sample_sequence` | sensor stream | acquisition owner | sample gap 확인 |
| `frame_sequence` | Camera boot | `camera.service` | Vision/video frame 연결 |

`boot_id`는 128-bit random 값으로 생성해 연결 `HELLO`와 저주기 status에서만 보낸다. packet마다 반복하지 않는다.

## 3. 시간 종류

| 시간 | 표현 | 사용 |
| --- | --- | --- |
| local monotonic | `uint64 ns` | TTL, heartbeat, lease, reconnect backoff |
| acquisition time | `uint64 ns` | IMU, encoder, depth, Camera, Payload sample |
| ROS Time | `builtin_interfaces/Time` | ROS topic header와 bag |
| wall time | RFC 3339 | operator log와 파일 metadata만 |

local monotonic 값은 다른 process와 직접 비교하지 않는다. 수신자는 packet 도착시각과 `valid_for_ms`로 freshness를 판정한다.

## 4. 이동 명령

Candidate와 승인 명령은 다음 조합으로 식별한다.

```text
source + control_epoch + sequence
```

- authority 획득, MANUAL session 교체, Gateway 재시작 시 `control_epoch`을 새로 만든다.
- `valid_for_ms`는 0보다 크고 config 상한 이하여야 한다.
- 수신 시 이미 만료됐거나 epoch가 다르면 적용하지 않는다.
- reconnect와 mode 전이 시 latest command cache를 지운다.

MCU wire v1에는 epoch와 TTL을 싣지 않는다. `TeensyRs485Backend`가 유효한 Gateway
명령만 전달하고, MCU는 command lease로 독립 정지해야 한다. v1의 `MPU_HEALTH`
timeout만으로는 최종 수용 조건을 충족하지 않는다.

## 5. Discrete request

mode 변경, Payload activity, platform action, file export에는 `request_id`를 사용한다.

- 같은 `request_id`와 같은 요청: 저장된 결과 반환
- 같은 `request_id`와 다른 요청: reject
- 처리결과 보존기간이 끝난 ID: 새 session에서만 재사용 가능
- 위험 action의 confirmation은 session에 묶고 reconnect 시 폐기

## 6. Sensor와 Camera

sensor sample은 `sample_sequence`, `acquisition_time_ns`, `validity`를 가진다. Camera는 `frame_sequence`, `capture_time_ns`를 사용한다. 변환 또는 추론 결과는 원본 sequence를 유지해 age와 gap을 계산할 수 있게 한다.

I200DK driver가 device timestamp를 제공하지 않으면 read 완료 직후 MPU monotonic time을 기록하고 `timestamp_source=HOST_RECEIVE`로 표시한다. 장비가 hardware timestamp를 제공할 때만 별도 동기화 정확도를 검증한다.

## 7. Restart 규칙

| 사건 | 필수 동작 |
| --- | --- |
| peer `boot_id` 변경 | RX/TX cache와 dedup window 초기화 |
| Gateway 재시작 | `NONE`, 새 epoch, motion 없음 |
| Teensy RS-485 backend 재시작 | serial/link handshake 전 motion 없음 |
| GCS 재연결 | 새 session과 lease 요구 |
| ROS 재시작 | AUTO readiness false, 새 candidate 대기 |
| Camera 재시작 | frame sequence는 새 boot 범위에서 1부터 시작 |

## 8. 기록 확장 조건

실제 dataset replay를 구현할 때만 dataset identity와 dual-clock mapping을 추가한다. 초기 운용 메시지에는 분석 전용 식별자를 넣지 않는다.

## 9. 검증

- sequence wrap, gap, duplicate, out-of-order
- boot 변경 후 cache 비움
- epoch 변경 후 이전 motion 적용 0건
- TTL/lease 경계와 monotonic clock jump 내성
- sensor acquisition time의 ROS 변환 오차
- GCS/cFS/Gateway 개별 재시작 후 재실행 0건
