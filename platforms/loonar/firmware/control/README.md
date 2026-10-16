# LOONAR Teensy 4.1 MCU v2

현재 임베디드 진입점은 `src/main.cpp` → `src/v2/runtime.cpp`이다.
기존 C control core와 wire v1은 호스트 회귀시험용으로 보존한다.
PWM/DIR·Teensy 엔코더 입력·BNO I²C HAL은 폐기했다.

## 핀과 장치

| 기능 | Teensy 핀 / 인터페이스 |
|---|---|
| RoboClaw RX / TX | 7 / 8, Serial2 packet serial |
| BNO055 UART RX / TX | 15 / 14, Serial3 115200 8N1; PS1 HIGH, PS0 LOW |
| Pi 초기 연결 | USB CDC, USB Serial |
| Pi 후속 UART | Serial1 RX0 / TX1, PCB J2 RS-422, 2 Mbaud, 8N1 |

[261004 MCU_MOTOR PCB](../../hardware/pcb/261004_pcb/MCU_MOTOR/mcu_motor.kicad_pcb)의
J4 `ESC UART PWM / XA 4P`를 BNO055 UART용으로 사용한다.

| J4 핀 | PCB 연결 | BNO055 연결 |
| --- | --- | --- |
| 1 | GND | GND |
| 2 | Teensy TX14 → R8 100Ω → B-G431B RX | BNO055 RX |
| 3 | B-G431B TX → R7 100Ω → Teensy RX15 | BNO055 TX |
| 4 | Teensy pin 2 PWM (100Ω 직렬, 10kΩ 풀다운) | 연결하지 않음 |

**J4에는 전원 핀이 없다.** BNO055 전원은 사용 모듈 사양에 맞춰 별도로 공급한다.
모터는 기존 Serial2 RX7/TX8(J3)을 유지한다. 기존 BNO RESET8 배선은 분리한다.
Pi USB 통신은 유지하며, 비USB 빌드의 HAT UART만 Serial1 RX0/TX1로 맞춰
BNO055 Serial3과의 충돌을 피한다.
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
`teensy41`는 Pi 링크를 Serial1으로 선택한다. `teensy41_encoder_verify`는
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

- TX14 → BNO055 RX, RX15 ← BNO055 TX, GND 공통. PS1 HIGH/PS0 LOW는 전원 인가 전에 설정한다.
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

## Reaction wheel (Control MCU)

261004 Control PCB 기준 ESC는 **Teensy 2 → J4-4**, 서보는
**Teensy 6 → J6-2**다. J4-1/J6-1은 GND다. J4-2/3의 BNO055 UART는 유지한다.
J4/J6에는 모터 전원 핀이 없으며 공통 GND와 외부 전원을 사용한다.
PWM은 50 Hz 하드웨어 FlexPWM으로 생성해 FreeRTOS와 Servo ISR의 타이머 공유를 피한다.

| 구간 | 왼쪽 | 오른쪽 |
|---|---|---|
| 부팅 준비 (5초) | ESC 1488 / 서보 1500 | 동일 |
| 1단계 | ESC 1513, 5초 | ESC 1463, 10초 |
| 2단계 | ESC 1538, 10초 | ESC 1438, 10초 |
| 중립 대기 | ESC 1488, 10ms | 동일 |
| 서보 유지 | 800, 3초 | 2200, 3초 |
| 완료 / STOP | ESC 1488 / 서보 1500 | 동일 |

좌/우는 각각 별도의 1회 실행이다. 참고 스케치의 15초 ramp 대신 위 단계별 고정
펄스 유지 시간을 사용한다. 10ms는 ESC 중립 **명령 이후**의 시간이며, 20ms PWM
프레임의 실물 펄스 도착 시각이나 휠 정지를 측정한 시간이 아니다.
현재 RPM 피드백은 없다. 준비 중·실행 중 재시작/방향 전환은 거부한다.
비제로 주행 명령과 리액션휠은 동시에 실행하지 않는다.
STOP, 세션 교체, Pi health 요청 1초 단절, MCU 온도 90°C 이상 또는 비정상 온도는
리액션휠을 취소하고 두 PWM을 중립으로 돌린다. 통신 복구 후 자동 재시작하지 않는다.
MCU watchdog reset 후에도 중립 및 부팅 준비부터 다시 시작한다.

### 수치 조정과 수동 실행

PC에서 빌드한 `teensy41_usb` 이미지를 Control UID/tag에 맞춰 업로드해야 한다.
사용자가 제공한 참고 스케치는 **"Disconnect ESC power during upload."**를 요구한다.
업로드 전 ESC 전원을 분리한다. 자동 업로드/실기 회전 시험은 하지 않는다.

Pi의 ground-support를 종료한 상태에서 실행한다. 이 도구는 Control USB를 단독
소유하며 GCS 실행 중의 시리얼 연결을 공유하지 않는다.

```bash
cd ~/LOONAR
export PYTHONPATH="$PWD/platforms/loonar/tools${PYTHONPATH:+:$PYTHONPATH}"
python3 -m mcu_v2.reaction_wheel left
python3 -m mcu_v2.reaction_wheel right
python3 -m mcu_v2.reaction_wheel stop
```

`Ctrl+C` 및 도구 종료도 STOP을 보낸다. 다른 프로세스가 USB를 소유하면 연결이
거부된다. 도구 실행은 새 세션을 만들므로 기존 동작은 중립으로 취소된다.
지상국의 ‘리액션휠 시험 설정’에서 같은 수치를 입력하고 좌·우 1회 실행을 사용할 수 있다.
이때 기존 Control backend가 단독 USB 소유자로 설정/실행을 전달한다.
MCU 설정 수락 후에만 START를 전송하고, 설정 거부/timeout은 자동 재시도하지 않는다.
실행 중 중복 요청은 거부하며 STOP, GCS TCP 단절 또는 Gateway 연결 단절은 중립 취소를 전달한다.
실기 시험은 사용자가 직접 실행한다.

`platforms/loonar/tools/mcu_v2/reaction-wheel.example.json`을 복사해 원하는 항목을
수정하고 `--config /path/to/settings.json`으로 지정한다. 펄스는 µs, 시간은 ms다.
설정은 MCU RAM에만 반영되며 재부팅 시 기본값으로 돌아간다. 부팅 기본값은
`include/loonar/control/reaction_wheel.hpp`의 `ReactionConfig`에서 변경한다.

### LNR2 명령 계약

기존 boot/session/sequence/CRC 검증과 STOP(7)은 유지한다.

- `REACTION(13)`: 1 byte. `0=취소`, `1=왼쪽`, `2=오른쪽`. 정상 세션과 최근 health
  요청, 중립 주행 상태, 부팅 준비 완료가 필요하다. 요청은 재전송하지 않는다.
- `REACTION_CONFIGURE(14)`: little endian `<8H6I>`, 40 bytes. JSON 예제 필드 순서와
  같다. 실행 중에는 거부한다. ESC 범위 1148..1832, 서보 800..2200 µs를 검사한다.
- `REACTION_STATUS(15)`: health 요청 및 실행 수락 후 송신. `<BBBBHHII>`:
  state, direction, active, reserved(0), ESC µs, servo µs, phase elapsed ms, cycle counter.
  state `0..5=PREPARING,READY,FIRST,SECOND,NEUTRAL_WAIT,SERVO_HOLD`.
- `RESULT(10)`: 기존 8-byte 형식. `code=0` 수락, `1` 잘못된 명령/설정,
  `2` 준비 중/실행 중, `4` 실행 조건 불충족. 수락은 물리 회전 확인을 뜻하지 않는다.
