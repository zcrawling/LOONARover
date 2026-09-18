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

## 5. Control Teensy 기본 pin map

| 기능 | Pin |
| --- | ---: |
| Status LED | 13 |
| MPU UART RX/TX (`Serial1`) | 0/1 |
| Left encoder A/B | 2/3 |
| Right encoder A/B | 4/5 |
| Left motor PWM/DIR/EN | 6/7/8 |
| Right motor PWM/DIR/EN | 9/10/11 |
| BNO085 SDA/SCL (`Wire`) | 18/19 |
| BNO085 INT/RST | 20/21 |

실제 PCB 확인 전 motor enable은 비활성으로 유지한다. pin과 polarity는
`../firmware/control/include/loonar/control/board_pins.h` 한 곳에서 관리한다.

## 6. HIL에서 확정할 항목

- MCU control loop deadline/jitter
- RS-485 error rate, termination/bias, cable length
- BNO085 output rate와 timestamp jitter
- encoder maximum count rate와 overflow
- motor current/temperature/fault interface
- Camera encoder 처리량, CPU, 발열, 전력
- I200DK sunlight/multipath/rough terrain 성능
- Raspberry Pi 5 worst-case end-to-end latency
- brownout, reboot, cable disconnect 후 safe restart
