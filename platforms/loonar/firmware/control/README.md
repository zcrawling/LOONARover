# LOONAR Teensy 4.1 MCU v2

현재 임베디드 진입점은 `src/main.cpp` → `src/v2/runtime.cpp`이다.
기존 C control core와 wire v1은 호스트 회귀시험용으로 보존한다.
PWM/DIR·Teensy 엔코더 입력·BNO I²C HAL은 폐기했다.

## 핀과 장치

| 기능 | Teensy 핀 / 인터페이스 |
|---|---|
| RoboClaw RX / TX | 7 / 8, Serial2 packet serial |
| BNO055 UART RX / TX | 25 / 24, Serial6 115200 8N1; PS1 HIGH, PS0 LOW |
| Pi 초기 연결 | USB CDC, USB Serial |
| Pi 후속 UART | Serial3 RX15 / TX14, 2 Mbaud, 8N1; **배선 확정 필요** |

모터는 Serial2 RX7/TX8을 사용한다. 기존 BNO RESET8 배선은 분리한다.
Control 역할에서는 BNO055 UART 작업을 실행한다. 기존 BNO085 SPI 작업은 사용하지 않는다.
엔코더는 RoboClaw의 count/speed 명령으로 읽는다. 현재 UART 구현은 full duplex이며 RS-485 half duplex의
DE/RE 전환은 포함하지 않는다.

모터 채널은 **M1=오른쪽, M2=왼쪽**으로 고정한다. Pi/MCU 프로토콜과
피드백 배열의 순서는 왼쪽·오른쪽이며, RoboClaw 드라이버에서 명령과
count/speed/current/PWM 응답을 함께 변환한다.
사용자가 Motion Studio 튜닝 및 Write Settings를 완료했다고 확인했다.
이후 실기 시험은 사용자가 직접 실행한다.

## 빌드·업로드

기본 환경 `teensy41_usb`는 USB CDC와 BNO055를 포함한다.
`teensy41`는 Pi 링크를 Serial3으로 선택한다. `teensy41_encoder_verify`는
IMU를 제외하는 진단 환경이다. `payload41_usb`는 역할 식별용 공통 기반이며
[실제 Payload 센서 펌웨어](../payload/README.md)와 다르다.

현재 `board_config.py`는 Linux ARM 빌드를 차단한다. Pi 빌드를 해결한 상태가
아니므로 아래는 개발 PC 빌드 → Pi 업로드 절차다.
UID 미지정 이미지는 HELLO 식별용이며 센서·모터를 구동하지 않는다.
대상 보드 UID와 Pi registry를 일치시켜 빌드한다.

Pi에 업로더가 없으면 `bash ~/LOONAR/platforms/loonar/deploy/prepare-control-upload.sh`로
설치한다. 기존 ground-support와 시리얼 모니터는 업로드 전에 종료한다.
`~/.local/bin/tycmd list --verbose`에서 Control 보드의 tag를 확인한다.
아래 UID/tag는 기존 Control 보드 예시이며 보드를 바꿨으면 다시 확인한다.

## 동작과 제한

- IO 태스크: USB/UART, RoboClaw 명령·피드백, health. IMU는 별도 태스크다.
- 차체 속도 → 바퀴 qpps 변환은 Pi backend에서 한다. 엔코더는 RoboClaw에서 읽는다.
- 장치·세션 불일치, 명령 만료(backend 200ms), MCU CPU 90°C 이상이면 목표 속도 0.
  냉각 후에도 새 명령이 필요하다. IO watchdog은 2초다.
- IMU 오류, RoboClaw ACK·조회 지연·오류는 보고하지만 주행 허가 조건으로 사용하지 않는다.
- 표본은 RAM 버퍼와 ACK/replay를 사용한다. 전원 차단·버퍼 초과의 무손실을 보장하지 않는다.
- IMU 수신은 구현되어 있으나 IMU 기반 직진 피드백 제어는 포함하지 않는다.

[wire v2](../../porting/mcu_wire_v2.md), [Pi 실행·기록](../../porting/ground_control_runbook.md).

## BNO055 통합 빌드

`teensy41_usb`가 BNO055를 포함한 기본 제어기 빌드다.
`teensy41_encoder_verify`는 IMU 작업을 제외하는 진단 빌드이므로 BNO055 시험에는 사용하지 않는다.

- TX24 → BNO055 RX, RX25 ← BNO055 TX, GND 공통. PS1 HIGH/PS0 LOW는 전원 인가 전에 설정한다.
- NDOF 0x0C, 기본 축 매핑, 가속도 m/s², 송신 각속도 rad/s, 쿼터니언 xyzw.
- 부팅 5000ms + 버스 250ms 대기. 초기화 최대 5회(실패 간격 150ms), 이후 2초 뒤 재시도.
- UART 트랜잭션 150ms 제한, 최대 3회/실패 간격 200ms. IMU 작업에서 RTOS 대기하므로 모터 작업은 계속 실행된다.
- 약 50Hz로 51바이트 레지스터 블록을 읽어 기존 Type32/36바이트 보고서 5개(1,2,5,4,6)를 송신한다.
- 상태가 fusion running(5), SYS_ERR=0일 때만 송신한다. 통신/센서 오류 시 2초 뒤 재초기화한다.
- 타임스탬프는 센서 노출 시각이 아닌 Teensy UART 수신 완료 시각이다. sequence는 호스트 폴링 번호이며 lost=0은 센서 내부 샘플 손실이 없다는 뜻이 아니다.
- calibration은 각 보고서에 대응하는 BNO 보정 레벨 0..3이다. 쿼터니언 accuracy 필드는 미측정으로 0이다.
- 기존 Pi ROS bridge가 `/imu` 계열 보고서를 수신한다. 센서 축은 장착/ENU 검증 전까지 위치추정에 바로 융합하지 않는다.
- 자력계 원시 보고서와 EEPROM 보정값 저장은 이번 통합에 포함하지 않는다.

```bash
# 노트북: 빌드 및 Pi 복사
cd /home/sb/LOONAR
LOONAR_BOARD_UID=000004e9e51e7948 ~/.local/bin/pio run -d platforms/loonar/firmware/control -e teensy41_usb
scp platforms/loonar/firmware/control/.pio/build/teensy41_usb/firmware.hex loonar@192.168.0.14:~/control-bno055.hex
scp platforms/loonar/tools/mcu_v2/{motor_bench,imu,ros_bridge}.py loonar@192.168.0.14:~/LOONAR/platforms/loonar/tools/mcu_v2/
# Pi: 기존 ground-support 종료 후 업로드
~/.local/bin/tycmd upload --board 19971280-Teensy ~/control-bno055.hex
bash ~/LOONAR/platforms/loonar/tools/start-ground-support.sh --ros-samples
```

Pi 콘솔의 `imu`에서 gyro_radps, accel_mps2, quaternion_xyzw 등을 확인한다.
health의 imu_progress 증가와 gyro_age_ms 최신값을 확인한다. `--record`를 추가하면 ROS 기록도 가능하다.
실제 하드웨어 수신 성공 여부는 업로드 후 확인해야 한다.
