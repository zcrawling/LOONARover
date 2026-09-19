# LOONAR Final Rover Hardware Baseline

This document is the final-LOONAR hardware baseline. LIMO is a separate
validation platform and must not overwrite these physical assumptions. The
Raspberry Pi operating-system/ROS choice is a deployment decision, not part of
this hardware baseline.

## 1. 확정 구성

| 영역 | 장치 | 역할 | Software 기준 |
| --- | --- | --- | --- |
| Main MPU | Raspberry Pi 5 8 GB | cFS, ROS 2, Gateway backend and Camera control | final deployment selection |
| Control MCU | Teensy 4.1 | motor, IMU, encoder, local safety | FreeRTOS |
| Payload MCU | Teensy 4.1 | Payload sensor와 local task | FreeRTOS |
| Camera | Raspberry Pi Camera Module 3 Wide | Vision과 GCS video | libcamera/GStreamer |
| Depth sensor | CubeEye I200DK | depth/point cloud, 조건부 위치보정 | target ROS adapter |
| Control IMU | BNO085 | IMU measurement | Control MCU owner |
| Motor driver | RoboClaw 2x7A | dual motor control and feedback | Control MCU, packet serial design proposed 2026-09-19 |
| Payload temperature | MLX90614 | non-contact temperature | Payload MCU owner |
| Payload RTD | MAX31865 | RTD interface | Payload MCU owner |
| Payload magnetometer | LIS3MDL | magnetic field | Payload MCU owner |

LIMO validation uses NUC11, Ubuntu 22.04 and ROS 2 Humble. The final Raspberry
Pi deployment environment is selected separately after sensor and platform
compatibility validation; the I200DK supplier baseline remains an input to that
decision.

## 2. I200DK 수령 후 확인 Gate

1. USB VID/PID, bandwidth, 전원과 reset/reconnect 확인
2. 공급 SDK/driver source와 license, arm64 binary ABI 확인
3. Ubuntu 24.04에서 SDK core build 또는 load
4. headless frame 수신과 device timestamp 확인
5. target ROS에서 표준 `sensor_msgs/PointCloud2`/depth image 발행
6. frame, unit, invalid point, range/FoV 확인
7. 30분 soak, cable reconnect, CPU/memory/temperature 측정

SDK core가 22.04 전용 binary뿐이면 ROS wrapper만의 포팅으로 해결되지 않는다. 이 경우 공급사 arm64/Noble binary 요청 또는 공개 protocol 기반 대체 구현을 별도 결정한다.

## 3. 물리 통신

2026-09-19 추가 요구: 초기 USB CDC와 최종 transceiver UART를 모두 지원하며,
두 역할은 별도 연결과 UID로 구분한다. 사용자 실행 USB 업로드 절차는
[Control USB 벤치](../porting/motor_usb_bench.md)를 따른다.
[MCU v2 구조](../porting/mcu_architecture_v2.md)가 신규 요구사항의 기준이다.
아래 링크와 v1 크기는 기존 UART 구현의 기준자료이며 v2 확정값이 아니다.

| Link | MPU owner | MCU | 기준 |
| --- | --- | --- | --- |
| Control | `TeensyRs485Backend` inside Vehicle Gateway | Control Teensy | 전용 UART + MAX3490E, 4-wire full-duplex RS-485, 2 Mbit/s |
| Payload | final payload service (TBD) | Payload Teensy | 전용 UART + MAX3490E, 4-wire full-duplex RS-485 |

두 MCU를 하나의 bus와 parser에 묶지 않는다. Control wire의 최대 packet은 46 byte이며 상세 규격은 `control_mpu_if.md`를 따른다.

## 4. Configuration으로 관리할 값

- wheel radius/separation, encoder ticks와 polarity
- motor channel, enable polarity, driver limit
- rover footprint, rear rod swept area, minimum turn radius
- Control/Payload device path와 baud
- IMU axis/mounting/rate/covariance
- Camera resolution/format/FPS/bitrate
- I200DK frame/range/FoV/point format/rate
- battery/temperature/reaction-wheel limit와 timeout

이 값은 source constant로 흩어놓지 않고 versioned config로 관리한다.

## 5. Control Teensy 배선 (2026-09-19 사용자 확정)

핀 번호는 Teensy 4.1 기준이다. SPI 10~13은 기본 SPI 신호 배치로 해석한다.

| 기능 | Teensy pin / 경로 |
| --- | --- |
| RoboClaw UART RX (`Serial1`) | 0: RoboClaw TX → Teensy RX |
| RoboClaw UART TX (`Serial1`) | 1: Teensy TX → RoboClaw RX |
| BNO085 RESET | 8 |
| BNO085 INTERRUPT | 9 |
| BNO085 SPI CS | 10 |
| BNO085 SPI MOSI | 11 |
| BNO085 SPI MISO | 12 |
| BNO085 SPI SCK | 13 |
| Pi ↔ Control 초기 통신 | USB CDC (`Serial`) |
| Pi ↔ Control 최종 트랜시버 UART | 구현: Serial3 RX15/TX14. HAT 배선 확정 필요; Serial1 0/1 공유 금지 |
| 엔코더 취득 | RoboClaw가 제공하는 count/speed 읽기. Teensy 직접 A/B 입력·ISR 없음 |

사용자 확정: **RoboClaw M1=오른쪽 모터, M2=왼쪽 모터**. Motion Studio 파라미터
튜닝 및 Write Settings 완료. 이후 카메라부터 사용자가 직접 테스트한다.
주행 변환 확정값: 바퀴 지름 196mm, 좌우 중심 간격 210mm,
바퀴/출력축 1회전당 encoder 485681 count, 전진 시 좌우 각각 count 증가(+1).

13번은 SPI SCK로 사용하므로 내장 LED를 별도 status blink로 제어하지 않는다.
기본 Serial2 TX 8번도 BNO085 RESET과 충돌하므로 그대로 Pi UART에 할당하지 않는다.
SPI 기준: [PJRC SPI 라이브러리 소스](https://github.com/PaulStoffregen/SPI/blob/master/SPI.cpp).

현재 펌웨어는 위 SPI·Serial1 배선을 반영했다. 이전 PWM/DIR·I²C HAL은 폐기했고,
임베디드 진입점은 `src/v2/runtime.cpp`이다. 실제 보드 업로드와 배선 검증은 아직 수행하지 않았다.

## 6. HIL에서 확정할 항목

- MCU control loop deadline/jitter
- RS-485 error rate, termination/bias, cable length
- BNO085 output rate와 timestamp jitter
- RoboClaw encoder telemetry의 단위·부호·갱신율·count overflow
- motor current/temperature/fault interface
- Camera encoder 처리량, CPU, 발열, 전력
- I200DK sunlight/multipath/rough terrain 성능
- Raspberry Pi 5 worst-case end-to-end latency
- brownout, reboot, cable disconnect 후 safe restart
