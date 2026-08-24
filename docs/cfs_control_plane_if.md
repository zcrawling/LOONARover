# cFS Control Plane Interface

## 1. 책임

cFS는 임무 모드, 명령권한, 이동 승인, 안전 제한, recovery, Payload activity, GCS 제어면을 담당한다. 고주기 센서와 대용량 데이터는 다루지 않는다.

## 2. App 구성

| App | 책임 | 금지사항 |
| --- | --- | --- |
| `LNR_CTRL` | 모드, authority, candidate 선택, safety, recovery, Payload activity | 장치파일·socket 직접 접근 금지 |
| `LNR_IO` | local IPC와 Software Bus 변환, 승인 명령 송신, 고정된 platform action 실행 | 정책 판단·임의 shell 실행 금지 |
| `GCS_IF` | 인증 세션, operator role, MANUAL lease, command/tlm framing | MCU·Camera 장치 직접 접근 금지 |

기본 cFS App은 `SCH`, `EVS`를 사용한다. `HS`는 App 감시가 필요할 때 활성화하고, `TBL`은 현장 조정값이 생길 때 추가한다. 별도 house-keeping App은 만들지 않고 각 App이 저주기 상태 snapshot을 제공한다.

## 3. LNR_CTRL 내부 모듈

```text
lnr_ctrl/
  mode.c               RoverMode 전이
  authority.c          MANUAL lease와 control_epoch
  arbiter.c            candidate 선택
  safety.c             freshness, readiness, limit, deny
  recovery.c           복구 단계 실행
  payload_activity.c   Payload activity 상태
  app.c                 SB 입출력과 20~50 Hz tick
```

각 모듈은 입력 snapshot과 config를 받아 결과를 반환하는 순수 함수로 작성한다. transport, 시간 읽기, event 발행은 `app.c` 경계에 둔다.

## 4. 권위 상태

### 4.1 RoverMode

`INIT`, `STANDBY`, `MANUAL`, `AUTO`, `RECOVERY`, `SAFE`

- 부팅과 cFS 재시작은 항상 `INIT`에서 시작한다.
- `INIT -> STANDBY`는 MCU link와 안전 상태가 확인된 뒤에만 가능하다.
- `MANUAL`은 유효한 GCS lease가 필요하다.
- `AUTO`는 ROS, localization, navigation 준비상태가 모두 유효해야 한다.
- `RECOVERY`의 이동도 일반 승인 경로를 그대로 사용한다.
- critical fault, cFS 입력 단절, 명시적 정지 요청은 `SAFE`로 전이한다.

### 4.2 PayloadState

`IDLE`, `RUNNING`, `COMPLETE`, `FAULT`

Payload 상태는 RoverMode와 병렬이다. Payload와 Camera fault는 주행 안전조건을 침해하지 않는 한 이동을 중지시키지 않는다.

### 4.3 Readiness evidence

`LNR_CTRL`은 다음 evidence의 `valid`, `age_ms`, `reason`만 보유한다.

- `mcu_ready`
- `ros_ready`
- `localization_ready`
- `navigation_ready`
- `gcs_authority_valid`
- `payload_ready`
- `camera_ready`

세부 진단은 해당 owner가 보유하고 `SYSTEM_STATUS`에는 요약만 싣는다.

## 5. 이동 승인 tick

20~50 Hz SCH tick마다 같은 순서를 실행한다.

```text
input cache 갱신
  -> mode/authority 전이
  -> select_candidate(mode, freshness)
  -> apply_safety(candidate, readiness, limits)
  -> APPROVED_MOTION 최신값 갱신
  -> 상태가 변한 경우에만 EVENT/SYSTEM_STATUS 발행
```

중간 판단은 App 내부 값이다. Software Bus에는 candidate 입력과 최종 승인값만 게시한다. 같은 상태·source·reason의 반복 event는 rate limit한다.

## 6. Software Bus 공개 메시지

| 메시지 | Producer | Consumer | Queue | 유효성 |
| --- | --- | --- | --- | --- |
| `AUTO_CANDIDATE` | `LNR_IO` | `LNR_CTRL` | latest 1 | `valid_for_ms` |
| `MANUAL_CANDIDATE` | `GCS_IF` | `LNR_CTRL` | latest 1 | lease + `valid_for_ms` |
| `MODE_REQUEST` | `GCS_IF`/mission | `LNR_CTRL` | bounded FIFO | `request_id` dedup |
| `APPROVED_MOTION` | `LNR_CTRL` | `LNR_IO` | latest 1 | `control_epoch`, `valid_for_ms` |
| `MCU_STATUS` | `LNR_IO` | `LNR_CTRL` | latest 1 | receive age |
| `PAYLOAD_REQUEST` | `GCS_IF`/mission | `LNR_CTRL` | bounded FIFO | `request_id` dedup |
| `PAYLOAD_STATUS` | `LNR_IO`/`LNR_CTRL` | `GCS_IF` | latest + transition | activity identity |
| `SYSTEM_STATUS` | `LNR_CTRL` | `GCS_IF`/`LNR_IO` | latest 1 | snapshot sequence |
| `PLATFORM_ACTION` | `LNR_CTRL` | `LNR_IO` | bounded FIFO | `request_id` |
| `EVENT` | 모든 App | `GCS_IF`/EVS | bounded FIFO | rate limited |

공개 메시지의 공통 필드는 `schema_version`, `sequence`뿐이다. 필요한 식별자와 시간은 메시지별로 정의한다.

## 7. Candidate와 승인 명령

Candidate 필드:

```text
source, sequence, control_epoch, valid_for_ms,
linear_mps, yaw_rate_radps
```

승인 명령 필드:

```text
sequence, control_epoch, valid_for_ms,
linear_mps, yaw_rate_radps, decision, reason
```

`decision`은 `ALLOW`, `LIMIT`, `DENY`다. `DENY`는 속도 0을 생성한다. 새 candidate가 없거나 epoch가 바뀌면 이전 값을 재사용하지 않는다.

## 8. Recovery

Recovery는 `LNR_CTRL` 내부 table-driven 상태기계다.

```text
STOP -> WAIT_STABLE -> RELOCALIZE -> LIMITED_MOVE -> VERIFY
     -> COMPLETE 또는 FAILED
```

각 단계는 timeout, entry action, 성공조건, 실패조건을 가진다. `LIMITED_MOVE`는 별도 우회 경로를 만들지 않고 candidate를 생성해 동일한 safety와 승인 경로를 통과한다.

## 9. Platform action

`LNR_IO`는 아래 enum만 실행할 수 있다.

- `RESTART_ROS`
- `RESTART_CAMERA`
- `RESTART_MCU_IO`
- `REBOOT_MPU`

입력에 shell, 파일경로, systemd unit 이름을 넣지 않는다. 실행 권한은 고정 helper 또는 D-Bus policy로 제한하고 결과를 `request_id`와 함께 반환한다.

## 10. 장애 동작

| 장애 | 동작 |
| --- | --- |
| ROS/localization loss | AUTO candidate 무효화, MANUAL 유지 |
| GCS loss | lease 만료 후 0속도 승인 |
| `LNR_CTRL`/cFS loss | 명령 갱신 중단, MCU watchdog 정지 |
| `LNR_IO` loss | MCU 명령 갱신 중단, reconnect 후 빈 cache에서 시작 |
| `mcu-io` loss | MCU watchdog 정지, link 복구 전 motion 금지 |
| Payload/Camera loss | 해당 기능만 fault, drive는 계속 가능 |

## 11. 단위시험 경계

- mode 전이 table test
- authority lease/epoch/deadman test
- candidate freshness와 source 선택 test
- safety allow/limit/deny table test
- recovery 단계와 timeout test
- Payload activity dedup/restart test
- cFS 재시작 후 과거 명령이 발행되지 않는 test
