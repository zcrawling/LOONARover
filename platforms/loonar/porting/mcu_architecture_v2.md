# LOONAR MCU 구조 — 단순화한 구현

2026-09-19 사용자 수정 요구를 반영한 현재 구현이다. 이후 요청한 USB 원격 업로드는
[사용자 실행 절차](motor_usb_bench.md)의 TyTools 방식으로 제공한다.

## 역할과 데이터 흐름

```text
BNO085 SPI ──┐                       ┌─ ROS 2 IMU / wheel odom
             ├─ Control Teensy ─ Pi backend ─ Vehicle Gateway
RoboClaw UART┘      USB 또는 UART     └─ cFS mcu_bridge ─ 지상국
Payload Teensy ─── 별도 Pi backend ──────┘
```

| 위치 | 담당 기능 |
|---|---|
| MCU IO 태스크 | USB/UART 패킷, 장치 식별, RoboClaw 명령·피드백, health, RAM 송수신 버퍼 |
| MCU IMU 태스크 | BNO085 SPI 취득과 센서 데이터 전송 버퍼 입력 |
| Pi backend | 역할별 연결, RAM 수신·ACK·중복 제거, 차체 속도→바퀴 qpps 변환, ROS/cFS 전달 |
| ROS bridge | 시간·단위 변환과 표준 메시지 발행; 위치 추정은 robot_localization |
| cFS mcu_bridge | Control/Payload 각각의 health를 지상국으로 전달 |

## 하드웨어

- RoboClaw: Serial1 RX0/TX1. 엔코더는 드라이버가 제공하는 값으로 읽는다.
- 모터 채널은 M1=오른쪽, M2=왼쪽으로 고정한다. 명령과 피드백 모두 드라이버에서 좌우 순서로 변환한다.
- BNO085: RESET8, INT9, CS10, MOSI11, MISO12, SCK13.
- Pi: 초기 USB CDC. UART 구현은 Serial3 RX15/TX14, 2 Mbaud, full duplex이며 HAT 배선은 확정해야 한다.
- Control/Payload는 각기 별도 연결과 버퍼를 사용한다.

## 장치 구분

Pi 설정은 역할, 실제 MCU UID, 장치 경로를 갖는다. 연결할 때 HELLO의 역할·UID를 대조한다.
펌웨어에도 대상 UID를 넣는다. 다른 보드에서 실행되면 센서·모터를 구동하지 않는다.
UID 미지정 빌드는 식별 응답만 가능하다. 역할/UID 확인은 원래 요구한 두 MCU 혼동 방지 기능이다.
업로드는 사용자가 지정한 Control USB tag만 대상으로 한다. 기존 LNR2 Payload 응답은 거부한다.
기존 앱에 역할 정보가 없는 첫 설치에서는 사용자가 실제 Control의 USB tag를 확인해야 한다.

## 센서와 모터

BNO085는 각속도, 가속도, quaternion, 선형 가속도, 중력, 자기장을 보낸다.
센서 시각·정확도·sequence·누락 수를 포함한다. IMU 오류나 미연결은 주행 금지 조건이 아니다.

MCU는 좌우 qpps 명령을 RoboClaw에 전달하고 count, speed, commanded qpps,
current, PWM, voltage, temperature, error를 돌려준다. 차체 치수와 encoder 변환은 Pi에만 둔다.
MCU에 별도 최대 속도나 가속도 제한은 없다.

**Teensy CPU 온도 90°C 이상이면 모터 목표를 0으로 한다.** health와 센서 통신은 계속한다.
온도가 내려가도 이전 주행 명령은 자동 재개하지 않으며 새 명령이 필요하다.
장치/세션 불일치, 명령 만료(backend 150 ms), RoboClaw 통신 만료(ACK 100 ms)·오류에 대한 기본 정지는 유지한다.
health는 상태 보고용이며 별도의 주행 허가 조건으로 사용하지 않는다.
IO 태스크 정지에 대비한 2초 watchdog을 유지하며 IMU 진행 여부와 연동하지 않는다.

## 버퍼

MCU 표본 버퍼 2,048건, 우선 응답 큐 16건, Pi 수신 버퍼 2,048건을 RAM에 둔다.
CRC-32C, sequence, ACK, 재전송, 중복 제거로 일시적인 통신 누락을 처리한다.
Pi는 RAM에 수신한 연속 sequence까지 ACK한다. 소비자가 느리면 Pi 버퍼에 보관하며,
버퍼가 차면 새 표본을 수락하거나 ACK하지 않고 재전송을 기다린다.
MCU 버퍼까지 넘친 경우 drop/gap counter로 누락을 드러낸다.
RAM이므로 프로세스 종료·전원 차단과 버퍼 용량을 넘는 장기 단절까지 보존하지 않는다.

서명·키 관리·이미지 해시/build ID·별도 manifest·라이선스 수집 절차·SQLite 저장은 없다.
일반 의존성 라이브러리의 원래 라이선스 파일은 그대로 둔다.

## 범위와 검증

`payload41_usb`는 역할 구분과 health를 제공하는 공통 기반이며, 개별 payload 센서 앱은 별도 작업이다.
로컬 빌드와 소프트웨어 시험을 수행한다. 실기 순서는 카메라 → Teensy USB/IMU → 라이다/ToF → 모터·주행이다.
[실행·시험 절차](mcu_v2_implementation.md), [통신 규격](mcu_wire_v2.md)을 따른다.
