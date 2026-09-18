# LOONAR Software Project

## 1. 현재 개발 기준

LOONAR의 최종 하드웨어가 완성될 때까지 LIMO를 공통 소프트웨어의 시험
플랫폼으로 사용한다.

| 구분 | 현재 시험 플랫폼 | 최종 플랫폼 |
| --- | --- | --- |
| 컴퓨터 | LIMO NUC, Ubuntu 22.04 | Raspberry Pi 5 8 GB |
| ROS 2 | Humble | 하드웨어 호환성 확인 후 확정 |
| 차량 backend | LIMO ROS 2 `/cmd_vel` | LOONAR MCU serial/RS-485 (포팅 시 구현) |
| 공통 코드 | Gateway, cFS adapter, GroundLink | 그대로 사용 |

LIMO 전용 코드는 `platforms/limo/`, 최종 로버의 하드웨어·MCU·센서 자료와
포팅 항목은 `platforms/loonar/`에 둔다. 최종 로버 자료는 레거시가 아니라
계속 참고해야 하는 이식 기준이다.

## 2. 데이터 경로

```text
카메라 ── H.264/MPEG-TS/UDP ───────────────────────────> 지상국 영상 수신기

지상국 제어 ── GroundLink/TCP ──> cFS ──> VehicleAdapter ──> vehicle_gatewayd
지상국 상태 <── GroundLink/TCP <── cFS <── VehicleAdapter <── vehicle_gatewayd

ROS 2 autonomy ── AUTO v,w ─────────────────────────────> vehicle_gatewayd
vehicle_gatewayd ── LIMO backend 또는 LOONAR backend ───> 차량

ROS 2 topic/TF/map ── 동일 LAN에서 RViz2로 직접 조회 ───> 지상국 개발 PC
```

영상, cFS 제어·상태, ROS 개발 관측은 서로 독립된 경로다. 영상 장애가 차량
명령 프로토콜을 막지 않으며 RViz2는 운용 제어 경로에 들어가지 않는다.

## 3. 운용 모드와 명령 선택

Gateway가 표시하는 모드는 다음 다섯 가지다.

| 모드 | 의미 |
| --- | --- |
| `STOP` | 명시적인 정지 상태 |
| `MANUAL` | 지상국 조이스틱의 `linear`, `angular` 명령 실행 |
| `AUTO` | ROS 2 autonomy의 `linear`, `angular` 명령 실행 |
| `PAYLOAD` | 차량을 정지시킨 뒤 payload 시퀀스 수행 |
| `REACTION` | 차량을 정지시킨 뒤 reaction wheel 기능 수행 |

선택 규칙은 단순하고 명시적이다.

1. 지상국/cFS `STOP`은 즉시 0 명령을 보내고 `STOP`으로 전환한다.
2. 지상국/cFS `MANUAL` 명령은 `MANUAL`로 전환하고 받은 속도를 그대로 보낸다.
3. ROS `AUTO` 속도는 현재 모드가 `AUTO`일 때만 전달한다.
4. `PAYLOAD`와 `REACTION`은 먼저 명시적 0 명령을 보낸 뒤 해당 모드로 전환한다.
5. `PAYLOAD`/`REACTION` 동안 ROS AUTO 속도는 차량으로 전달하지 않는다.

Gateway에는 authority, epoch, TTL, command lease, 속도 상한, backend health
gate를 넣지 않는다. 유한수가 아닌 손상된 속도 프레임만 거부한다. 필요한
장치 수준 보호는 최종 MCU 설계에서 별도로 결정한다.

## 4. 구성요소 책임

### `vehicle_gatewayd`

- cFS, ROS 2, backend용 Unix `SOCK_SEQPACKET` endpoint 제공
- 다섯 모드 선택과 현재 명령 상태 유지
- 공통 `linear`, `angular` 차량 명령 전달
- backend의 공통 `VehicleStatus`를 cFS로 중계
- 수신 명령을 즉시, 현재 모드를 1초마다 로그로 출력

LIMO에서는 별도 ROS backend node가 공통 명령을 `/cmd_vel`로 전달한다.
최종 LOONAR에서는 같은 backend socket 뒤에 serial/RS-485 구현을 추가한다.

### cFS 최소 구성

- `GroundLink`: TCP 한 연결에서 지상국 명령 수신 및 telemetry 전송
- `VehicleAdapter`: Software Bus 명령과 Gateway 로컬 프로토콜 변환
- 다섯 명령의 Software Bus MID 제공
- Gateway/Vehicle/MCU/Device/Event telemetry MID 제공

미션 시퀀서나 자율주행 알고리즘은 현재 최소 cFS 범위가 아니다. PAYLOAD의
실제 시퀀스와 REACTION의 actuator·복구·사후 로직은 최종 하드웨어 포팅 때
구현한다. 현재 REACTION은 경로만 존재하며 `NOT_IMPLEMENTED`를 반환한다.

### ROS 2

- 센서 driver, TF, odometry, perception, SLAM/localization, Nav2 담당
- `AUTO` 모드에서만 Gateway에 공통 `linear`, `angular` 명령 제공
- 향후 ROS mode bridge가 현재 운용 모드를 구독해 PAYLOAD/REACTION/STOP을
  제어 불능으로 오판하지 않도록 구성
- cFS와 무관하게 동일 LAN에서 topic, TF, map을 관찰 가능

### 영상 송신기

- LIMO는 Orbbec 통합 RGB UVC 장치를 V4L2로 직접 입력
- Raspberry Pi는 카메라를 `libcamerasrc`로 직접 입력
- 1/3/5 Mbit/s 프리셋으로 저지연 H.264 인코딩
- MPEG-TS로 감싸 UDP 5600에 직접 전송
- 독립적인 systemd 서비스로 실행
- ROS는 어느 platform에서도 영상 전송 경로에 포함하지 않음

## 5. 공통 상태

`VehicleStatus`는 platform 독립 구조이며 각 값의 유효 비트가 있다.

- 배터리 전압/잔량
- odometry 위치, yaw, 선속도, 각속도
- IMU roll, pitch, yaw

LIMO backend는 `/limo_status`, `/wheel/odom`, `/imu`를 이 구조로 변환한다.
제조사가 제공하지 않는 배터리 잔량 등은 추정하지 않고 invalid로 둔다.

최종 LOONAR에서는 다음 telemetry를 cFS를 통해 지상국에 추가 전달한다.

- MCU 연결 및 MCU 제공 온도/전압/전류/오류 값
- IMU, 모터, payload sensor 등 MCU 연결 장치 상태
- LiDAR, 카메라 등 Linux 연결 장치 상태
- Wi-Fi 연결 상태
- payload 결과 및 reaction event/result

공통 envelope와 MID는 현재 구현되어 있다. 최종 센서 값을 만드는 producer와
MCU wire mapping은 하드웨어 포팅 항목이다.

## 6. 구현·검증 순서

1. 공통 codec과 Gateway core 단위 테스트
2. Gateway daemon socket 통합 테스트
3. cFS GroundLink/VehicleAdapter를 공식 cFS 빌드로 검증
4. Ground mock → TCP → cFS SB → Gateway 전체 경로 검증
5. LIMO ROS 2 backend를 NUC에서 빌드하고 정지 상태에서 topic/status 검증
6. LIMO 실제 주행으로 MANUAL/AUTO/STOP 검증
7. ROS 2 주행 로직과 simulation 구성
8. LOONAR 완성 후 serial backend, MCU telemetry producer, PAYLOAD/REACTION 구현

## 7. 관련 문서

- `docs/ground_link_protocol.md`: 지상국 TCP wire format
- `docs/vehicle_gatewayd_if.md`: Gateway 로컬 socket interface
- `docs/ground_control_implementation_plan.md`: 구현 단위와 현재 상태
- `cfs/README.md`: cFS 앱 통합·빌드 방법
- `common/video/README.md`: 공통 영상 송신기와 systemd 설치 방법
- `platforms/limo/video/README.md`: LIMO 카메라 실장 정보와 검증 결과
- `platforms/rpi/video/README.md`: Pi 카메라 설정 방법
- `platforms/loonar/porting/ground_control_tbd.md`: 최종 로버 포팅 TBD
- `platforms/loonar/hardware/`: 최종 하드웨어 참고자료
- `platforms/loonar/interfaces/`: MCU 및 장치 interface 참고자료
