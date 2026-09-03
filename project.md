# Rover Software Architecture — Agent Handoff Specification

## 0. 목적

본 문서는 최종 로버와 LIMO 시험 플랫폼에서 최대한 동일한 소프트웨어를 사용하기 위한 상위 SW 아키텍처를 정의한다.

핵심 목표는 다음과 같다.

* cFS는 **Mission + Ground Segment**만 담당한다.
* ROS 2는 **Autonomy**만 담당한다.
* 실제 차량 제어 인터페이스는 `Vehicle Gateway/API` 뒤로 숨긴다.
* AUTO와 MANUAL이 서로 다른 MCU 통신 경로를 사용하지 않는다.
* Control MCU와 MPU 사이의 실제 통신 인터페이스는 항상 하나만 존재한다.
* LIMO와 최종 로버의 차이는 가능한 한 `Vehicle Backend`에서만 발생하게 한다.
* 최종 actuator safety는 ROS/cFS가 아니라 MCU가 책임진다.

## 0.1 현재 개발·검증 플랫폼

현재 공통 기능의 개발과 end-to-end 검증은 대여한 LIMO에서 수행한다.

| 항목 | 현재 LIMO 플랫폼 | 최종 LOONAR 플랫폼 |
| --- | --- | --- |
| Compute / OS | NUC11, Ubuntu 22.04 | Raspberry Pi 기반 최종 구성 |
| ROS 2 | Humble | 최종 sensor/platform 호환성 검증 후 확정 |
| Vehicle Backend | `LimoBackend` | `TeensyRs485Backend` |
| 우선 검증 범위 | Gateway, cFS/ROS interface, Nav2, MANUAL, TTL/epoch, camera control | RS-485, MCU command lease, PID/encoder, final sensor calibration 및 vehicle dynamics |

LIMO-specific driver, topic, calibration은 `platforms/limo/`에만 둔다. 최종
LOONAR의 PCB, MCU firmware, RS-485 wire, sensor 및 HIL 자료는
`platforms/loonar/`에 보존하며, 공통 상위 로직은 어느 플랫폼에도 직접 의존하지 않는다.

---

# 1. 전체 SW 구조의 핵심

## 1.1 책임 분리

### cFS — Mission / Ground Plane

cFS 담당:

* Ground Station TM/TC
* Mission sequence
* Mission START / STOP / ABORT
* Goal / waypoint 전달
* AUTO / MANUAL 운용 모드 명령
* Manual drive TC 수신
* Mission status / event / log
* Payload mission commanding
* Camera start/stop/record 등 상위 명령
* ROS autonomy 상태 및 vehicle 상태를 요약하여 지상국에 TM으로 전달

cFS가 담당하지 않는 것:

* SLAM
* Localization
* Path planning
* Obstacle avoidance
* `cmd_vel` 생성
* Wheel control
* Motor PID
* ROS node 내부 recovery
* 직접적인 RS485/UART 제어

---

### ROS 2 — Autonomy Plane

ROS 2 담당:

* Sensor driver 및 sensor processing
* Perception
* Localization / state estimation
* SLAM 필요 시 수행
* Nav2
* Reactive navigation fallback
* 목표점까지의 자율주행
* AUTO mode에서 `linear velocity v`, `angular velocity ω` 생성
* Autonomy 상태/진행도를 cFS에 보고

ROS는 실제 MCU serial/RS485를 직접 소유하지 않는다.

---

### Vehicle Gateway — Vehicle Interface / Final Command Arbiter

Linux userspace의 독립 서비스로 구현한다.

예:

`vehicle_gatewayd`

역할:

* Control MCU 통신의 단일 소유자
* AUTO/MANUAL/NONE authority arbitration
* ROS의 AUTO motion command 수신
* cFS의 MANUAL motion command 수신
* command TTL/dead-man
* sequence
* control epoch
* stale command 제거
* velocity hard/soft validation
* zero-command transition
* 차량 backend 추상화
* vehicle telemetry를 ROS와 cFS 양쪽에 제공

중요:

**ROS와 cFS가 각각 MCU/차량에 직접 접근해서는 안 된다.**

항상:

```text
ROS ───────┐
           │
           ▼
      Vehicle Gateway ─────→ ONE Vehicle Interface
           ▲
           │
cFS ───────┘
```

구조를 유지한다.

---

### MCU / FreeRTOS — Vehicle Safety / Real-Time Control

최종 Rover의 Teensy MCU 담당:

* Command validation
* Command lease timeout
* v, ω → wheel setpoint 변환
* Wheel velocity PID
* Encoder sampling
* PWM / motor output
* Motor/sensor hard limits
* Watchdog
* E-stop
* Communication timeout
* MCU fault handling
* Actuator SAFE state

최종 actuator enable 여부는 MCU가 결정한다.

---

# 1.2 최종 전체 구조

```text
                         Ground Station
                               │
                       TM / TC / Mission
                               │
                               ▼
                        ┌────────────┐
                        │    cFS     │
                        │            │
                        │ Mission    │
                        │ Ground I/F │
                        │ Payload    │
                        └─────┬──────┘
                              │
                ┌─────────────┴─────────────┐
                │                           │
       Mission / AUTO control        Manual v,ω TC
                │                           │
                ▼                           │
            ┌─────────┐                     │
            │  ROS 2  │                     │
            │         │                     │
            │ Nav2    │                     │
            │ Reactive│                     │
            │ Percept.│                     │
            │ Localiz.│                     │
            └────┬────┘                     │
                 │ AUTO v,ω                  │
                 └────────────┬──────────────┘
                              ▼
                    ┌──────────────────┐
                    │ Vehicle Gateway  │
                    │                  │
                    │ Final Arbiter    │
                    │ TTL / epoch      │
                    │ limits / routing │
                    └────────┬─────────┘
                             │
                    ONE Vehicle API
                             │
             ┌───────────────┴───────────────┐
             │                               │
             ▼                               ▼
       LIMO Backend                  Teensy RS485 Backend
             │                               │
          LIMO Base                      MAX3490E
                                             │
                                             ▼
                                       Teensy/FreeRTOS
                                             │
                                      Motor / Encoder
```

---

# 1.3 절대 지켜야 할 불변 조건

### RULE-1 — 차량 명령 경로는 하나

금지:

```text
ROS ─→ MCU

cFS ─→ MCU
```

허용:

```text
ROS ─┐
     ├→ Vehicle Gateway → MCU
cFS ─┘
```

---

### RULE-2 — AUTO와 MANUAL은 동일한 VehicleMotionCommand 사용

MCU에 다음과 같이 별도 인터페이스를 만들지 않는다.

```text
AUTO_MOTION_COMMAND
MANUAL_MOTION_COMMAND
```

하나의 공통 명령만 사용한다.

개념적 인터페이스:

```text
VehicleMotionCommand
{
    control_epoch
    sequence
    source

    linear_velocity_mps
    angular_velocity_radps

    valid_for_ms
}
```

`source`:

```text
AUTONOMY
MANUAL
TEST
```

---

### RULE-3 — authority는 Vehicle Gateway에서 최종 판정

예:

```text
authority = AUTO
→ ROS command만 허용

authority = MANUAL
→ cFS/GS manual command만 허용

authority = NONE
→ 모든 motion command 무시 + zero
```

ROS가 계속 명령을 생성해도 MANUAL/NONE에서는 폐기한다.

---

### RULE-4 — 모든 motion command는 유효기간을 갖는다

MANUAL/AUTO 모두 지속적인 command refresh가 필요하다.

통신이 끊기면:

```text
Gateway command TTL expiry
        ↓
ZERO command

        +

MCU command lease expiry
        ↓
Actuator SAFE
```

두 계층으로 정지한다.

---

### RULE-5 — mode 변경 시 control_epoch 증가

예:

```text
AUTO epoch = 15
        ↓
MANUAL 전환
        ↓
epoch = 16
```

늦게 도착한:

```text
AUTO
epoch = 15
```

packet은 즉시 폐기한다.

AUTO↔MANUAL 전환 중 stale command가 적용되는 것을 방지한다.

---

# 1.4 AUTO 동작

```text
Ground
  │
  │ MISSION_START / SET_GOAL
  ▼
cFS
  │
  ├→ Vehicle Gateway:
  │      authority = AUTO
  │
  └→ ROS:
         START / SET_GOAL
             │
             ▼
        Nav2 / Reactive
             │
           v, ω
             │
             ▼
       Vehicle Gateway
             │
             ▼
        Vehicle Backend
             │
             ▼
           Vehicle
```

cFS는 자율주행 알고리즘에 개입하지 않는다.

---

# 1.5 MANUAL 동작

Ground Station에서 MANUAL을 선택하면:

```text
Ground
  │
  │ MANUAL_MODE
  ▼
cFS
  │
  ├→ ROS:
  │     autonomy STOP/CANCEL
  │
  └→ Vehicle Gateway:
        authority transition
            ↓
        ZERO command
            ↓
        epoch++
            ↓
        authority = MANUAL
```

그 이후:

```text
Ground joystick
      │
      │ ManualDrive TC
      ▼
     cFS
      │
      │ v, ω + TTL
      ▼
Vehicle Gateway
      │
      ▼
Vehicle Backend
      │
      ▼
    Vehicle
```

중요:

**실제 manual velocity command는 ROS autonomy를 통과하지 않는다.**

ROS-cFS 인터페이스는 MANUAL 전환 시 ROS autonomy를 STOP/CANCEL하기 위해 사용한다.

---

# 1.6 STOP / Mission Stop

Mission sequence 또는 Ground TC에서 STOP이 발생하면:

```text
cFS
 │
 ├→ ROS autonomy CANCEL/STOP
 │
 └→ Vehicle Gateway
         │
     authority = NONE
         │
     epoch++
         │
     immediate ZERO
```

MCU에는 추가로 command lease timeout이 존재한다.

따라서 ROS가 잘못된 command를 계속 생성해도 Gateway가 이를 폐기한다.

---

# 1.7 Telemetry 구조

Vehicle 상태는 한 곳에서만 실제 hardware로부터 읽는다.

```text
Vehicle / MCU
      │
      ▼
Vehicle Gateway
   ┌──┴───────────────┐
   │                  │
   ▼                  ▼
 ROS state         cFS TM
   │                  │
Localization       Ground Station
Diagnostics
```

ROS와 cFS가 동일 RS485 device를 각각 읽어서는 안 된다.

---

# 1.8 Camera 구조

Camera는 Control Plane과 Data Plane을 분리한다.

### cFS Control Plane

```text
CAMERA_START
CAMERA_STOP
RECORD_START
RECORD_STOP
TAKE_SNAPSHOT
```

및:

```text
camera health
FPS
record status
stream status
```

등만 처리한다.

### Video Data Plane

고대역폭 영상은 cFS Software Bus/TM을 거치지 않는다.

```text
Camera
   ↓
ROS / libcamera
   ↓
encoding / GStreamer
   ↓
Ground Station
```

최종 Pi Camera Module 3와 LIMO camera 사이에는 sensor driver 차이만 존재하도록 한다.

---

# 2. ROS 2 최종 구조

## 2.1 기존 합의에서 유지되는 부분

다음 역할은 그대로 유지한다.

```text
Sensors
   ↓
Perception
   ↓
Localization / State Estimation
   ↓
Nav2 or Reactive Navigation
   ↓
desired vehicle motion
```

ROS가 결정하는 최종 출력은:

```text
linear velocity v
angular velocity ω
```

이다.

즉 ROS는:

> “로버가 어느 방향으로 얼마의 속도로 움직여야 하는가?”

를 결정한다.

ROS가 직접:

* PWM 생성
* Motor PID
* Encoder closed loop
* MCU watchdog

등을 수행하지 않는다.

---

# 2.2 기존 설계에서 수정된 부분

초기에는:

```text
Nav2
 ↓
diff_drive_controller
 ↓
wheel velocity
 ↓
ros2_control SystemInterface
 ↓
RS485
 ↓
Teensy
```

구조를 검토했다.

이 구조는 일반적인 ROS 로봇에는 적절하지만 다음 요구와 충돌한다.

* ROS 전체가 정지해도 manual driving 가능
* cFS ground manual control 필요
* MCU interface를 AUTO/MANUAL 두 개로 만들면 안 됨
* LIMO와 최종 rover를 동일 API로 추상화해야 함

따라서 최종 구조에서는 **RS485 ownership을 ros2_control 밖으로 이동한다.**

수정 후:

```text
ROS Autonomy
     │
    v,ω
     │
     ▼
Vehicle Gateway
     │
     ▼
Vehicle Backend
```

이다.

---

# 2.3 ros2_control의 위치

ros2_control은 필수적인 MCU 통신 계층으로 사용하지 않는다.

필요하면 ROS 내부 joint representation, controller test 등에 사용할 수 있지만:

**ros2_control plugin이 UART/RS485를 직접 열어서는 안 된다.**

실제 physical vehicle interface의 owner는 항상 Vehicle Gateway이다.

---

# 2.4 ROS 구성 요소

권장 ROS 패키지/노드 구조:

```text
rover_msgs
    공통 ROS message

rover_mission_interface
    cFS ↔ ROS mission command/status

rover_perception
    Camera / ToF 처리

rover_localization
    wheel odometry + IMU fusion

rover_navigation
    Nav2 integration

rover_reactive_navigation
    depth/LiDAR 기반 fallback navigation

rover_vehicle_client
    Vehicle Gateway와 IPC

rover_camera
    camera acquisition / encoding / stream

rover_diagnostics
    ROS subsystem health aggregation
```

---

# 2.5 cFS ↔ ROS 인터페이스

cFS가 ROS에 전달하는 것은 고수준 mission intent이다.

예:

```text
START_AUTONOMY
STOP_AUTONOMY

SET_GOAL
SET_WAYPOINTS

START_REACTIVE
STOP_REACTIVE
```

금지:

```text
wheel speed
PWM
motor command
```

ROS → cFS는 요약 상태만 보낸다.

예:

```text
AutonomyStatus
{
    mode
    goal_status
    progress

    localization_valid
    navigation_valid
    perception_valid

    fault_summary
}
```

Camera frame, PointCloud, TF, raw sensor data 등을 cFS Software Bus에 그대로 복제하지 않는다.

---

# 2.6 ROS Autonomy 내부 상태

예:

```text
INACTIVE
NAVIGATION
REACTIVE
FAULT
```

cFS Mission state와 ROS state를 동일한 global state machine으로 만들지 않는다.

예를 들어 다음 상태는 정상적으로 존재할 수 있다.

```text
cFS:
MISSION_RUNNING

ROS:
FAULT

Vehicle Gateway:
NONE

MCU:
DISARMED
```

cFS는 이를 Ground Station에 보고하고 mission policy에 따라 abort/retry 등을 결정한다.

---

# 3. LIMO와 최종 Rover의 공통 구조

Vehicle Gateway core는 그대로 사용한다.

```text
                    SAME CORE

                  VehicleGateway
                  ├─ authority
                  ├─ epoch
                  ├─ TTL
                  ├─ sequence
                  ├─ validation
                  └─ telemetry

                       │
               Backend Interface
                 ┌─────┴─────┐
                 │           │
                 ▼           ▼

          LimoBackend   TeensyRs485Backend

              │                 │
             LIMO             RS485
                                │
                              MCU
```

---

## 3.1 LIMO Backend

초기 개발에서는:

```text
VehicleGateway
       ↓
LimoBackend
       ↓
LIMO /cmd_vel 또는 LIMO driver
```

를 사용할 수 있다.

LIMO의 odometry/status는 Gateway를 통해 상위 SW에 전달한다.

---

## 3.2 Final Rover Backend

최종에서는:

```text
VehicleGateway
       ↓
TeensyRs485Backend
       ↓
MAX3490E
       ↓
Teensy
       ↓
FreeRTOS
       ↓
Motor
```

로 교체한다.

상위 모듈:

* cFS
* Mission logic
* Ground TC/TM
* Manual driving
* Nav2
* Reactive navigation
* Vehicle Gateway core

는 수정하지 않는 것을 목표로 한다.

---

# 4. LIMO에서 검증 후 그대로 가져갈 부분

LIMO에서 production 수준까지 검증 가능한 것:

```text
cFS Mission Manager
Ground TM/TC
Mission sequence

AUTO/MANUAL/NONE authority
Manual joystick/dead-man
command TTL
control epoch
stale command rejection

Vehicle Gateway core

ROS Nav2 orchestration
Reactive navigation logic
Localization architecture
Mission ↔ ROS interface

Camera command/control
Camera streaming architecture

logging
diagnostics
fault injection logic
```

최종 rover에서 다시 검증해야 할 것:

```text
RS485 physical communication
MAX3490E
Teensy protocol backend

FreeRTOS
MCU watchdog
MCU command lease

wheel kinematics
wheel PID
encoder
motor control
actual braking distance

Pi-specific driver/performance
final sensor calibration
vehicle dynamics
```

---

# 5. 최종 시스템의 핵심 문장

각 subsystem의 책임은 다음 한 문장으로 표현한다.

### cFS

**“미션으로 무엇을 해야 하는가, 그리고 지상국이 무엇을 명령했는가?”**

### ROS 2

**“그 미션을 자율적으로 어떻게 수행할 것인가?”**

### Vehicle Gateway

**“현재 누가 차량을 제어할 권한이 있으며, 어떤 motion command를 차량에 전달할 것인가?”**

### MCU

**“받은 motion command를 실제 actuator에 적용해도 안전한가, 그리고 어떻게 실시간으로 실행할 것인가?”**

---

# 6. Agent Implementation Rules

개발 에이전트는 다음 규칙을 위반해서는 안 된다.

1. ROS가 Control MCU의 UART/RS485 device를 직접 열지 않는다.
2. cFS도 Control MCU의 UART/RS485 device를 직접 열지 않는다.
3. Vehicle Gateway만 physical vehicle interface를 소유한다.
4. AUTO와 MANUAL은 같은 `VehicleMotionCommand` contract를 사용한다.
5. Manual command를 ROS autonomy stack을 통해 전달하지 않는다.
6. ROS-cFS interface는 mission/autonomy control과 status exchange용이다.
7. AUTO/MANUAL 전환 시 항상 zero transition과 `control_epoch` 증가를 수행한다.
8. 모든 continuous motion command에는 TTL/dead-man을 적용한다.
9. Gateway가 죽거나 command가 끊기면 차량은 정지해야 한다.
10. 최종 rover에서는 MCU 자체 command lease가 Gateway watchdog과 독립적으로 존재해야 한다.
11. Hardware-specific code는 backend 안으로 격리한다.
12. LIMO-specific code가 navigation/mission/core 로직으로 유출되면 안 된다.
13. Teensy/RS485-specific code가 ROS autonomy 로직으로 유출되면 안 된다.
14. Raw camera/video data는 일반 cFS TM 경로에 넣지 않는다.
15. Ground Manual, ROS Auto, Test command가 동시에 vehicle authority를 가질 수 없다.

---

# 7. 최소 End-to-End Acceptance Test

다음이 LIMO에서 우선 통과되어야 한다.

### AUTO

```text
GS Mission Start
→ cFS
→ ROS Goal
→ Nav2
→ v,ω
→ Gateway
→ LIMO 주행
```

### Mission STOP

```text
GS/cFS STOP
→ ROS cancel
→ Gateway authority NONE
→ 즉시 정지
```

### MANUAL

```text
GS MANUAL
→ cFS
→ ROS autonomy stop
→ Gateway MANUAL
→ joystick TC
→ cFS
→ Gateway
→ LIMO 주행
```

### Dead-man

```text
Manual TC 중단
→ Gateway TTL timeout
→ LIMO STOP
```

### Stale command

```text
AUTO → MANUAL 전환
→ epoch 증가
→ 과거 AUTO packet 수신
→ DROP
```

### Autonomy failure

```text
Nav2 kill
→ AUTO command 소실
→ Gateway timeout
→ STOP
→ MANUAL 전환 가능
```

최종 Teensy rover가 완성되면 동일한 시험을 `LimoBackend → TeensyRs485Backend`만 교체하여 다시 수행한다.
