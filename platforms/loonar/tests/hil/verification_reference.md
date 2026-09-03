# LOONAR Hardware Validation Reference

이 문서는 최종 LOONAR의 MCU, RS-485, sensor, camera, payload 및 HIL 시험 자산을
보존한다. 모든 Control link 시험은 `vehicle_gatewayd`와 `TeensyRs485Backend` 경로로
수행한다.

## 1. 원칙

Gate는 기능 존재가 아니라 안전한 실패와 bounded resource를 증명한다. 모든 결과에는 commit, config hash, target, test log, 주요 counter를 남긴다.

## 2. 시험 계층

| 계층 | 대상 | 환경 |
| --- | --- | --- |
| Unit | codec, parser, pure state logic | host |
| Contract | wire/IPC/SB/ROS schema | CI |
| Component | process/App/node | fake I/O |
| SIL | 실제 process와 PTY virtual MCU | Ubuntu 24.04 |
| HIL | Pi 5, Teensy, serial, sensors | 실제 HW |
| Soak/Fault | kill, pressure, reconnect | SIL/HIL |

## 3. G0 — Contract와 Ownership

| ID | 시험 | 통과조건 |
| --- | --- | --- |
| `IF-001` | numeric ID uniqueness | duplicate/reserved 충돌 0 |
| `IF-002` | wire/IPC golden vector | 모든 target byte 일치 |
| `IF-003` | producer/consumer audit | owner 없는 공개 message 0 |
| `IF-004` | hardware owner audit | serial/Camera direct opener 각 1 |
| `IF-005` | motion writer audit | 승인 경로 외 writer 0 |
| `IF-006` | TF audit | `odom -> base_link` writer 1 |
| `IF-007` | resource audit | unbounded queue/buffer 0 |
| `IF-008` | restart audit | cache-clear 규칙 누락 0 |

## 4. G1 — Control Wire와 Teensy RS-485 Backend

| ID | 시험 | 통과조건 |
| --- | --- | --- |
| `CTL-001` | fragmented/coalesced stream | 모든 정상 packet 복원 |
| `CTL-002` | CRC/version/length corruption | crash 없이 reject/resync |
| `CTL-003` | random byte fuzz | OOB/hang/allocation growth 0 |
| `CTL-004` | motion latest queue | 가장 최근 유효값만 송신 |
| `CTL-005` | Gateway/RS-485 backend kill | MCU command lease로 안전 정지 |
| `CTL-006` | serial reconnect | 새 승인 전 motion 0건 |
| `CTL-007` | 30분 SIL soak | memory 증가와 unexpected error 0 |
| `CTL-008` | Control/Payload 동시 부하 | Control latency 요구 유지 |

## 5. G2 — MANUAL/GCS

| ID | 시험 | 통과조건 |
| --- | --- | --- |
| `MAN-001` | full manual path | GCS sequence가 MCU status에 반영 |
| `MAN-002` | role/lease | 권한 또는 lease 없는 motion 0건 |
| `MAN-003` | command deadman | TTL 만료 후 0속도 |
| `MAN-004` | mode/epoch 변경 | 이전 epoch 적용 0건 |
| `MAN-005` | GCS disconnect/reconnect | 새 lease 전 motion 0건 |
| `MAN-006` | ROS process kill | MANUAL 유지, AUTO unavailable |
| `MAN-007` | cFS kill/restart | Gateway authority `NONE`, mission state 재동기화 |
| `MAN-008` | velocity flood | memory 상한과 latest 적용 |
| `MAN-009` | discrete dedup | 동일 request 재실행 0건 |

## 6. G3 — ROS AUTO와 Localization

| ID | 시험 | 통과조건 |
| --- | --- | --- |
| `ROS-001` | IMU/wheel timestamp | acquisition time/단위 정확 |
| `ROS-002` | wheel odometry | straight/turn golden 결과 일치 |
| `ROS-003` | TF authority | writer 1, loop 0 |
| `ROS-004` | full AUTO path | 승인 후에만 MCU 도달 |
| `ROS-005` | candidate timeout | 0속도와 reason 갱신 |
| `ROS-006` | localization loss | AUTO block, MANUAL 가능 |
| `ROS-007` | ROS restart | readiness 재확인 전 AUTO 0건 |

## 7. G4 — I200DK

| ID | 시험 | 통과조건 |
| --- | --- | --- |
| `LID-001` | target OS/ROS arm64 build/load | clean Pi 5에서 재현 |
| `LID-002` | depth/point schema | frame/unit/invalid point 일치 |
| `LID-003` | timestamp | source와 age 계산 가능 |
| `LID-004` | cable reconnect | crash 없이 bounded 복구 |
| `LID-005` | 30분 stream | memory 안정, drop counter 설명 가능 |
| `LID-006` | quality gating | invalid correction 적용 0건 |
| `LID-007` | rough/sunlight dataset | reject/성공 기준 측정 |
| `LID-008` | recovery relocalize | success/failure 모두 안전정지 경로 |

SDK core가 Noble/arm64에서 실행되지 않으면 `LID-001`은 실패로 기록하고 공급사 지원 또는 대체 구현 결정 전까지 integration을 진행하지 않는다.

## 8. G5 — Payload

| ID | 시험 | 통과조건 |
| --- | --- | --- |
| `PAY-001` | command dedup | 같은 request 실행 1회 |
| `PAY-002` | activity state | GCS와 MCU 상태 일치 |
| `PAY-003` | sample sequence | gap/drop/validity 기록 |
| `PAY-004` | link kill/reconnect | drive 유지, 명시적 재동기화 |
| `PAY-005` | disk stall/full | Control latency 유지 |
| `PAY-006` | queue overflow | byte 상한과 drop counter |
| `PAY-007` | file resume/hash | 지정 range와 hash 일치 |

## 9. G6 — Camera

| ID | 시험 | 통과조건 |
| --- | --- | --- |
| `CAM-001` | Vision consumer stop | capture nonblocking, depth 1 |
| `CAM-002` | network congestion | old video drop, Control 영향 0 |
| `CAM-003` | encoder restart | Vision branch 유지 |
| `CAM-004` | Camera disconnect | bounded backoff와 fault 통보 |
| `CAM-005` | video authentication | expired/invalid token 거부 |
| `CAM-006` | 30분 simultaneous load | CPU/memory/thermal 요구 충족 |
| `CAM-007` | latency | capture→Vision/video 요구 충족 |

zero-copy는 `CAM-006/007`의 copy 비용이 요구를 넘을 때만 별도 최적화 Gate를 연다.

## 10. G7 — System Fault와 HIL

| ID | 시험 | 통과조건 |
| --- | --- | --- |
| `SYS-001` | cFS/ROS/Gateway/Camera/Payload Transport kill matrix | 정의된 격리/정지 동작 일치 |
| `SYS-002` | CPU stress | motion deadline과 watchdog 유지 |
| `SYS-003` | network/storage pressure | Control/Critical TLM 유지 |
| `SYS-004` | thermal pressure | bounded degrade와 상태 통보 |
| `SYS-005` | real RS-485 error/soak | error율과 latency 요구 충족 |
| `SYS-006` | motor interlock | hard safety override 불가 |
| `SYS-007` | brownout/reboot | unsafe output와 stale replay 0건 |
| `SYS-008` | Camera+I200DK+Payload load | drive path starvation 0 |

구체적인 latency 수치는 MCU control period, cable, motor driver, Pi 5 부하를 측정한 뒤 requirement table에 고정한다. 평균뿐 아니라 max, p99.9, jitter, deadline miss를 기록한다.

## 11. 필수 증거

- JUnit/CTest 결과
- config와 dependency version
- queue high-water mark와 drop counter
- reconnect/restart counter
- latency/jitter summary
- 관련 wire/event/rosbag log
- 실패 시 재현 명령과 최초 원인

## 12. Release 조건

1. G0~G3 모두 통과
2. 장착 기능에 해당하는 G4~G6 통과
3. G7 HIL과 soak 통과
4. known failure를 skip으로 숨기지 않고 limitation으로 승인
5. firmware, catalog, ICD와 실제 binary version 일치
