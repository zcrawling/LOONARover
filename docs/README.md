# LOONAR Rover Software Design

이 디렉터리는 LOONAR 로버 소프트웨어의 구현 기준이다. 문서 간 충돌이 있으면 이 문서의 불변조건, 개별 인터페이스 문서, 구현·검증 계획 순으로 해석한다.

통합 아키텍처 요약본은 `Rover_SW_System_Architecture.docx`다.

## 1. 기준 환경

| 항목 | 기준 |
| --- | --- |
| MPU | Raspberry Pi 5 8 GB, arm64 |
| OS | Ubuntu 24.04 LTS |
| ROS 2 | Jazzy |
| 비행 소프트웨어 | cFS 7 계열 |
| Control/Payload MCU | Teensy 4.1 + FreeRTOS |
| Camera | Raspberry Pi Camera Module 3 Wide |
| Depth sensor | CubeEye I200DK |

I200DK 공급사 배포물은 Ubuntu 22.04/ROS 2 Humble 환경을 기준으로 확인되었다. 본 프로젝트는 Raspberry Pi 5의 기준 환경을 낮추지 않고 Ubuntu 24.04/ROS 2 Jazzy에서 소스 빌드와 의존성 교체로 포팅한다. 실제 장비 수령 후 USB 인식, SDK ABI, 프레임 수신, PointCloud 발행, 장시간 재연결을 순서대로 검증한다.

## 2. 아키텍처 불변조건

1. Control MCU가 모터 출력과 로컬 안전정지의 최종 실행자다.
2. MPU의 실행영역은 `mcu-io`, `cfs`, `ros2`, `camera` 네 개의 systemd 서비스만 둔다.
3. `mcu-io`만 Control/Payload 직렬장치를 열고, `camera.service`만 Camera 장치를 연다.
4. ROS 2와 GCS는 MCU에 직접 명령하지 않는다. 모든 이동 명령은 `LNR_CTRL`의 승인 후 `LNR_IO`와 `mcu-io`를 통과한다.
5. Control 링크와 Payload 링크는 파일 디스크립터, parser, buffer, 상태를 분리한다.
6. Camera, PointCloud, raw Payload 같은 대용량 데이터는 cFS Software Bus를 통과하지 않는다.
7. 모든 queue는 bounded이며 reconnect 후 과거 명령을 다시 실행하지 않는다.
8. AUTO는 ROS/localization 준비상태가 무효이면 중지한다. MANUAL은 ROS 장애와 독립적으로 유지한다.
9. GCS lease 또는 명령 유효시간이 만료되면 승인 이동 명령은 0으로 수렴한다.
10. 최종 `odom -> base_link` TF는 `robot_localization` 한 곳에서만 발행한다.

## 3. 실행 구조

```text
GCS ── authenticated control/tlm ── GCS_IF ─┐
Nav2 ── loonar_bridge ── local IPC ── LNR_IO ├─ cFS SB ── LNR_CTRL
MCU status ── mcu-io ── local IPC ── LNR_IO ┘                  │
                                                               └─ APPROVED_MOTION
                                                                    │
                                           LNR_IO ── mcu-io ── Control MCU

Camera ── camera.service ── latest frame ── ROS Vision
                         └─ encoded video ── GCS
Payload MCU ── mcu-io ── LNR_IO/LNR_CTRL + bounded raw record ── GCS bulk
```

## 4. 문서 목록

| 문서 | 내용 |
| --- | --- |
| `Rover_SW_System_Architecture.docx` | 통합 아키텍처 기준서 |
| `hardwares.md` | 하드웨어, OS/ROS 2, 물리 링크 기준 |
| `interface_catalog.md` | 실행영역, owner, endpoint, 메시지 전체 목록 |
| `time_identity_if.md` | 시간, sequence, boot, epoch, request 식별 규칙 |
| `control_mpu_if.md` | Control MCU 직렬 wire v1 |
| `mcu_ros2_if.md` | `mcu-io`, local IPC, ROS 2 bridge |
| `cfs_control_plane_if.md` | cFS 3-App 제어면과 상태기계 |
| `camera_if.md` | Camera 캡처·Vision·Video 경로 |
| `payload_mcu_if.md` | Payload 명령·상태·sample·저장 경로 |
| `gcs_if.md` | 인증, MANUAL, telemetry, video, bulk |
| `implementation_plan.md` | vertical slice 구현 순서 |
| `sw_implementation_execution_plan.md` | 저장소 구조와 작업 단위 |
| `verification_gates.md` | 통과조건과 시험 증거 |

## 5. 변경 규칙

공개 경계만 catalog로 고정한다. 대상은 MCU wire ID, local IPC message type, 외부 cFS MID, GCS protocol version이다. 내부 함수 결과와 상태 전이는 소스 enum으로 관리한다. 인터페이스 변경에는 producer/consumer, 단위, 유효시간, queue 정책, 재시작 동작, contract test를 함께 수정한다.
