# LOONAR Teensy 4.1 MCU v2

현재 임베디드 진입점은 `src/main.cpp` → `src/v2/runtime.cpp`이다.
기존 C control core와 wire v1은 호스트 회귀시험용으로 보존한다.
PWM/DIR·Teensy 엔코더 입력·BNO I²C HAL은 폐기했다.

## 핀과 장치

| 기능 | Teensy 핀 / 인터페이스 |
|---|---|
| RoboClaw RX / TX | 0 / 1, Serial1 packet serial |
| BNO085 RESET / INT | 8 / 9 |
| BNO085 CS / MOSI / MISO / SCK | 10 / 11 / 12 / 13 |
| Pi 초기 연결 | USB CDC, USB Serial |
| Pi 후속 UART | Serial3 RX15 / TX14, 2 Mbaud, 8N1; **배선 확정 필요** |

0/1은 Pi 연결에 쓰지 않는다. 8번을 쓰는 Serial2와 13번 LED blink도 사용하지 않는다.
엔코더는 RoboClaw의 count/speed 명령으로 읽는다. BNO 보드는 SPI 모드 strap과
3.3 V 신호 조건을 맞춰야 한다. 현재 UART 구현은 full duplex이며 RS-485 half duplex의
DE/RE 전환은 포함하지 않는다.

모터 채널은 **M1=오른쪽, M2=왼쪽**으로 고정한다. Pi/MCU 프로토콜과
피드백 배열의 순서는 왼쪽·오른쪽이며, RoboClaw 드라이버에서 명령과
count/speed/current/PWM 응답을 함께 변환한다.
사용자가 Motion Studio 튜닝 및 Write Settings를 완료했다고 확인했다.
이후 실기 시험은 사용자가 직접 실행한다.

## 빌드

개발 PC의 저장소 루트에서 실행한다. 아래 예시는 장치에 연결하지 않는 컴파일 명령이다.
현재 FreeRTOS 포트는 전용 newlib 툴체인이 필요하므로 Pi의 Ubuntu 기본 컴파일러로 빌드하지 않는다.

```bash
# UID 미지정: HELLO discovery만 가능한 이미지. 센서/모터 핀 구동 금지.
pio run -d platforms/loonar/firmware/control -e teensy41_usb

# 실제로 확인한 16자리 UID를 넣는다. 임의 예시 UID를 설치하지 않는다.
LOONAR_BOARD_UID="$CONTROL_UID" pio run -d platforms/loonar/firmware/control -e teensy41_usb
LOONAR_BOARD_UID="$CONTROL_UID" pio run -d platforms/loonar/firmware/control -e teensy41
LOONAR_BOARD_UID="$PAYLOAD_UID" pio run -d platforms/loonar/firmware/control -e payload41_usb
```

각 환경의 `.pio/build/<env>/firmware.hex`가 생성된다. 대상 UID와 역할만 빌드 설정에 넣는다.
PC 빌드 후 SSH로 Pi에 HEX를 전달하는 [Control 업로드·모터 벤치 절차](../../porting/motor_usb_bench.md)를 제공한다.
정상 USB의 software reboot와 TyTools의 대상 지정 업로드를 사용한다.

`payload41_usb`는 역할 식별과 health를 제공하는 공통 기반이다.
개별 payload 센서 앱은 포함하지 않으므로 기존 payload 펌웨어를 대체하는 완성본이 아니다.

## 구현 범위

- FreeRTOS 태스크 두 개: IO(통신·RoboClaw·health), IMU(BNO085 SPI).
- BNO 요청률: gyro/accel 200 Hz, quaternion 100 Hz, linear acceleration/gravity 50 Hz,
  magnetic field 20 Hz. 실제 취득률은 실기 확인 항목이다.
- RoboClaw: signed qpps 목표, count/speed/current/PWM/전압/온도/error 피드백.
  엔코더 입력을 Teensy가 직접 처리하지 않는다.
- 차체 속도→바퀴 qpps 계산은 Pi에서 한다. MCU 자체 속도·가속도 제한과 IMU 오류 주행 금지를 제거했다.
- Teensy CPU 온도 90°C 이상이면 모터 목표를 0으로 한다.
  health·센서 통신은 유지한다. 냉각 후에는 새 주행 명령이 필요하다.
- 기본 정지 조건은 장치/세션 불일치, 명령 만료(20–200 ms, backend 150 ms),
  driver ACK 만료(100 ms)와 driver 오류다. health 수신을 주행 허가로 사용하지 않는다.
- IO 태스크에 2초 watchdog을 둔다. IMU 이상은 watchdog feed나 모터 제어를 막지 않는다.
- MCU 표본 2,048건·우선 응답 16건, Pi 수신 표본 2,048건을 RAM에 둔다.
  RAM 수신 후 ACK하며 sequence·재전송·중복 제거를 사용한다. 초과는 drop/gap으로 보고한다.
  프로세스 종료·전원 차단·용량 초과까지 무손실을 보장하지는 않는다.
- EEPROM 마지막 8바이트는 boot counter용이다. UID 미등록/불일치 시 변경하지 않는다.

## Pi · ROS · cFS

[설정과 검증 절차](../../porting/mcu_v2_implementation.md),
[wire v2 명세](../../porting/mcu_wire_v2.md)를 따른다.
`tools/mcu_v2`의 backend가 연결을 소유하고 ROS bridge와 cFS에 전달한다.
`/wheel/odom`은 twist 측정이며 pose 추정은 robot_localization이 담당한다.
`/imu/orientation_raw`는 장착 TF와 축 확인 후 사용한다.

## 장치 없는 시험

```bash
cmake -S . -B build/mcu-v2-check -DBUILD_TESTING=ON
cmake --build build/mcu-v2-check -j2
ctest --test-dir build/mcu-v2-check --output-on-failure
PYTHONPATH=platforms/loonar/tools python3 -m unittest mcu_v2.test_v2 -v
python3 tools/gcs_test/run.py --build-only --skip-tests --jobs 2
```

마지막 명령은 cFS를 빌드만 한다. 실제 SPI/UART/USB, firmware upload,
watchdog 복구, motor stop 시간, ROS 실측 covariance는 하드웨어 인수시험 항목이다.
