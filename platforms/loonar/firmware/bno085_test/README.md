# Teensy 4.1 ↔ BNO085 단독 SPI 시험

현재 버전: **FIX-v5**. 아래 DIAG/FIX-v4 절은 이전 시험 기록이다.

ROS/Pi/FreeRTOS/모터 제어 없이 Arduino setup/loop와 USB 텍스트 로그로 센서를 확인한다.
이 테스트를 업로드하면 기존 주행 펌웨어가 대체된다. 모터 전원은 끄고 Teensy USB를
Pi에서 분리해 이 PC에 직접 연결한다. 업로드 시 이 PC에는 대상 Teensy 한 대만 연결한다.

## 배선

| BNO085 보드 표기 | Teensy 4.1 | 역할 |
|---|---:|---|
| CS | 10 | CS |
| DI | 11 | MOSI |
| SDA | 12 | MISO (보드의 SPI 핀 정의 확인) |
| SCL | 13 | SCK |
| RST | 8 | RESET |
| INT | 9 | interrupt |
| GND | GND | 공통 접지 |

전원은 사용하는 센서 보드의 정격에 맞추고 Teensy 신호는 3.3V 기준으로 연결한다.
PS0/PS1은 해당 보드 설명서의 SPI 모드로 설정한다. 13번은 SPI 클럭이므로 LED blink에 쓰지 않는다.

## 적용한 대기·재시도

1. `setup()` 최상단에서 RST LOW 100ms → INT INPUT_PULLUP·CS HIGH → RST HIGH 후 200ms 대기. 추가 5초 대기는 사용자가 제거한 상태를 유지한다. 각 `begin_SPI()` 내부 리셋도 LOW 100ms/HIGH 후 200ms로 동일하게 적용한다.
2. CS HIGH, SPI 핀 지정 및 `SPI.begin()` 후 `delay(250)`.
3. `begin_SPI()` 및 보고 설정을 최대 5회 시도. 실패 후 다음 시도 전 `delay(150)`.
   다섯 번 모두 실패하면 시도 사이 대기 합계는 600ms이며 begin/보고 설정 실행 시간은 별도.
4. 성공하면 즉시 재시도 종료. 모두 실패하면 로그를 남기고 대기. `r` 입력으로 새 5회 묶음 실행.
5. 재시도 전에 `sh2_close()`로 고정 라이브러리의 단일 SHTP 슬롯 반환.
6. gyro/accel 50Hz, rotation vector 20Hz 요청. 센서 reset 감지 시 동일 초기화 재실행.

## 빌드 / 업로드 — 이 PC에서

```bash
cd /home/sb/LOONAR
~/.local/bin/pio run -d platforms/loonar/firmware/bno085_test
~/.local/bin/pio run -d platforms/loonar/firmware/bno085_test -t upload
```

업로더가 보드를 기다리면 Teensy의 Program 버튼을 짧게 한 번 누른다.
자동 업로드는 USB로 연결된 대상에 수행되므로 다른 Teensy는 분리한다.

## 시리얼 로그

```bash
ls -l /dev/serial/by-id/
~/.local/bin/pio device monitor --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_19971280-if00 --baud 115200
```

실제 장치 경로가 다르면 `ls` 출력의 경로로 바꾼다. 모니터 종료는 Ctrl+C.
초기 로그를 놓쳤으면 `r`을 입력한다(필요하면 Enter). `r` 재시도에는 최초 setup의 5초/250ms 대기는 반복하지 않는다.

- `begin_SPI=OK` 및 product/version: 센서 식별 성공.
- `reports: gyro=1 accel=1 rotation=1`: 보고 설정 성공.
- `STATUS`의 gyro/accel/quat 누적 수가 계속 증가: 실제 센서 데이터 수신 성공.
- `GYRO`, `ACCEL`, `QUAT`: 출력량을 제한한 실측값. 기울이거나 회전시켜 변화를 확인한다.
- `INIT FAILED`: 초기화 실패. 각 begin 소요 시간, INT/RST/CS 상태를 함께 확인.
- `INIT OK`만으로 수신 성공으로 판정하지 않는다. `NO EVENTS`는 초기화 후 데이터가 안 오는 상태.
- INT/RST/CS는 읽은 논리값일 뿐 전압/배선 정상 여부를 보장하지 않는다.

## 산출물과 기존 펌웨어 복원

테스트 HEX: `.pio/build/teensy41/firmware.hex` (이 프로젝트 기준).

기존 IMU 보완 주행 펌웨어는 다음 파일로 보존되어 있다:
`/home/sb/LOONAR/output/imu-only-build-20260926/control-imu-only.hex`.
테스트를 마치고 복원할 때, 대상 Teensy 한 대만 연결한 상태에서:

```bash
~/.platformio/packages/tool-teensy/teensy_loader_cli -mmcu=imxrt1062 -w -s -v \
  /home/sb/LOONAR/output/imu-only-build-20260926/control-imu-only.hex
```

기다리는 동안 필요하면 Program 버튼을 짧게 누른다. 테스트 펌웨어는 LNR2를 제공하지 않으므로
주행용 도구의 HELLO/health와 호환되지 않는다.

## DIAG-v1: SPI 초기화 실패 단계 확인

`diagnostic_build.py`는 고정 라이브러리의 소스 복사본을 빌드 폴더에 생성하여 계측한다.
원본 라이브러리 및 주행 펌웨어는 수정하지 않는다. 소스 형태가 달라지면 빌드를 중단한다.
처음 8개 SPI 수신 헤더, 마지막 송신 prefix, read/write 호출 수, INT timeout,
센서 reset 호출 수와 sh2_open/product-ID 결과를 RAM에 기록하고 begin_SPI 반환 후 출력한다.
이는 파형 측정이 아니며 헤더가 정상처럼 보여도 패킷 내용까지 검증한 것은 아니다.

- `sh2_open=0 product_id=-6`: SH2 open은 반환했지만 제품 ID 조회 timeout.
  SH2 open 성공 코드만으로 센서 reset/광고 패킷 수신 성공을 보장하지 않는다.
- `product_id=-999`: 제품 ID 조회까지 도달하지 않음.
- `RX HEADER ... FF FF FF FF`: 읽힌 값이 모두 HIGH. 미구동 MISO/CS/접촉 문제 등 확인 대상이며 원인을 단정하지 않는다.
- `00 00 00 00`: 유효 패킷 헤더가 아님. MISO LOW 고정뿐 아니라 센서 준비 상태도 확인.
- `int_timeouts`: 라이브러리가 INT LOW를 기다리다 만료된 횟수. 통신 성공 여부와 구분.

다시 업로드한 후 첫 줄에 **DIAG-v1**이 있는지 확인하고, 첫 번째 BEGIN부터
INIT FAILED까지 로그를 수집한다. 기존 `cat`/시리얼 모니터는 Ctrl+C로 종료한 뒤 업로드한다.
이 진단 버전은 PC 빌드 성공만 확인했으며 실기 결과는 사용자 로그로 확인한다.

## DIAG-v3: INT 대기 중 반복 리셋 배제 비교

DIAG-v2에서 매 시도 reads=0/writes=0, INT timeout=2, resets=3이 관측되어
비교 목적으로 다음 두 조건만 변경했다. 이것이 실제 장애 원인이라는 확정은 아니다.

- INT LOW 대기 상한 500ms → 2000ms.
- 대기 만료 시 내부 hardwareReset 호출 제거. 다음 begin에서만 리셋.

최초 5000ms, SPI 준비 후 250ms, 최대 5회/실패 사이 150ms는 유지.
실패 시 한 시도가 약 4초 이상 걸릴 수 있다. 정상적인 계측값은 시도당 resets=1이며,
여전히 reads=0이면 두 번의 긴 INT 대기에도 통신 시작 조건을 확인하지 못한 것이다.
이번 변경만으로 배선/센서/MCU 입력 중 어느 쪽인지 판정하지 않는다.


## FIX-v4: SPI 처리 및 오류 전달 수정

변경은 단독 테스트 프로젝트에만 적용한다. 전원 대기 5000ms, SPI 준비 후 250ms,
최대 5회/실패 사이 150ms, SH2 세션 정리는 그대로다. PS0/WAKE는 구동하지 않는다.

- 리셋 해제 뒤 고정 10ms 대기를 제거하고 즉시 수신 처리. 센서 준비 완료는 실제 INT와 부팅 응답으로 확인.
- INT 변화 인터럽트는 횟수·최초 LOW 시각만 기록한다. ISR 안에서 SPI/Serial을 사용하지 않으며 지나간 edge를 근거로 INT HIGH일 때 읽기를 강행하지 않는다.
- 수신은 INT HIGH면 즉시 반환하여 SH2 상태 처리를 막지 않는다.
- 패킷 헤더와 본문을 하나의 CS LOW 구간에서 읽는다. CS로 INT가 해제된 뒤 같은 패킷에서 다시 INT를 기다리지 않는다.
- 부팅 reset 응답과 control 채널을 모두 받아야 SH2 open 성공. 없으면 2초 후 -6(timeout), product_id=-999(미실행).
- 송신 INT 대기는 100ms 후 -6 반환. HAL write가 계속 0을 반환해 upstream이 무한 재시도하는 경로를 차단.
- 타임스탬프는 micros() 사용. 센서 콜백 null 포인터 방어 유지.
- 초기 센서 보고 설정을 시작하기 전 USB 진단 출력으로 지연시키지 않는다.

최초 로그 `FIX-v4` 확인. 실패 시 `INT edges falling=... rising=...`와
`sh2_open/product_id`, `SPI reads/writes`를 함께 확인한다. falling=0이면 IRQ 계측 구간에도
LOW 전이가 관측되지 않은 것이다. 센서 내부 원인을 단정하는 값은 아니다.

검증: Teensy 4.1 빌드 성공. 모의 SPI 시험에서 INT가 CS 선택 직후 HIGH가 되어도
본문까지 단일 트랜잭션으로 수신, 길이 검증, 송신 timeout 검증 통과.
실제 SH2 C 코드로 무응답 timeout/5회 세션 정리 시험 통과. 두 시험 ASan/UBSan 사용.
현재 PC에서 USB Teensy가 확인되지 않아 업로드/센서 복구는 검증하지 못했다.

PS0가 HIGH에 고정되어 있으므로 이 코드는 센서를 WAKE 핀으로 깨울 수 없다.
이 변경은 확인된 소프트웨어 처리 문제를 보완한 것이며 실제 센서 복구를 보장하지 않는다.

## FIX-v5: 기존 배선에서 긴 리셋 시험

SPI0 및 CS10/DI11/SDA12/SCL13/RST8/INT9 배선을 유지한다.
setup 최상단과 각 begin 내부에서 RST LOW 100ms, 해제 후 200ms를 적용한다.
INT는 `digitalRead()`로 실제 LOW 레벨을 확인한다. CHANGE 인터럽트 카운트는
진단용이며 통신 시작 조건이 아니다. SPI 1MHz/mode3, startup 2초 제한,
패킷당 단일 CS, 최대 5회/150ms 재시도와 센서 값 출력을 유지한다.
RESET은 전원 방전이 아니며, 실제 센서 복구 여부는 실기 확인이 필요하다.
200ms 대기 중에도 begin의 IRQ 추적은 동작하지만 SPI 패킷 처리는 대기 이후 시작한다.

```bash
cd /home/sb/LOONAR
~/.local/bin/pio run -d platforms/loonar/firmware/bno085_test -e teensy41 -t upload
```

부팅 로그의 FIX-v5 및 SPI0 CS10 DI11 SDA12 SCL13 RST8 INT9를 확인한다.

## MKR ZERO: 사용자 지정 배선

`mkrzero` 환경은 **CS3 / DI4 / SDA11 / SCL12 / RST5 / INT2**를 사용한다.
기본 하드웨어 SPI와 다른 배선이므로 소프트웨어 SPI mode3/MSB-first를 사용한다.
각 반주기에 1µs 대기 + GPIO 호출 시간이 들어가므로 실제 클럭은 500kHz 미만이며
1MHz로 고정되지 않는다. SDA11은 SPI MISO, SCL12는 SPI SCK로 쓰며 I2C를 사용하지 않는다.
INT2는 코어의 외부 인터럽트 매핑이 없어 레벨 폴링으로 확인하고 에지 추적은 N/A로 출력한다.
PS0/PS1 SPI 모드 설정, VCC 3.3V→센서 VIN, 공통 GND는 유지한다.
리셋 LOW100ms/해제 후200ms, 버스 대기250ms, 5회/150ms 재시도 및 값 출력은 동일하다.
USB 연결 대기는 최대3초이며, 시작 로그를 놓쳤다면 `r`로 재시도할 수 있다.

```bash
cd /home/sb/LOONAR
# 빌드
~/.local/bin/pio run -d platforms/loonar/firmware/bno085_test -e mkrzero
# 업로드 (연결된 보드 포트 자동 탐색)
~/.local/bin/pio run -d platforms/loonar/firmware/bno085_test -e mkrzero -t upload
# 시리얼: 실제 장치 포트에 맞게 변경
~/.local/bin/pio device monitor -p /dev/ttyACM0 -b 115200
```

자동 업로드 진입 실패 시 MKR ZERO RESET 버튼을 빠르게 두 번 눌러 부트로더로 진입한 뒤
업로드를 다시 실행한다. 이식 빌드는 검증했으며 센서 실물 통신 성공은 별도 확인이 필요하다.

## Teensy 4.1 UART-SHTP

환경 `teensy41_uart`: PS0 LOW / PS1 HIGH, UART-SHTP 3,000,000bps 8N1.
115200bps UART-RVC와 다른 모드다. USB 콘솔은 기존 115200 설정으로 연다.

| Adafruit BNO085 | Teensy 4.1 |
|---|---|
| VIN | 3.3V |
| GND | GND |
| SDA (센서 TX) | 0 (Serial1 RX) |
| SCL (센서 RX) | 1 (Serial1 TX) |
| RST | 8 |
| INT (상태 확인용) | 9 |
| PS0 | LOW/GND (VIN 납땜 브리지 제거 후) |
| PS1 | HIGH/3.3V (VIN=3.3V 브리지 유지 가능) |
| CS, DI | 미연결 |

전원을 끄고 PS0의 VIN 납땜 브리지를 제거한다. VIN과 쇼트된 상태에서 GND로 연결하지 않는다.
센서 BT는 기존 기본 상태를 유지한다. 모드 핀은 리셋 시 읽힌다.
초기 추가 5초 대기는 기존 사용자 설정대로 0ms. RST LOW100ms/HIGH 후200ms,
버스 대기250ms, 최대5회/150ms 재시도, 자이로/가속도 값 출력 유지.
UART 수신 버퍼 8KB 추가, 리셋 전에 수신 활성화, 시작 패킷 보존.
UART 무응답 시 읽기는 즉시 반환하고 SH2 초기화는 2초 후 타임아웃한다.
호스트 송신 바이트 간 110µs 대기를 적용한다. UART rx_bytes/frames/bad_frames로 진단한다.

```bash
cd /home/sb/LOONAR
~/.local/bin/pio run -d platforms/loonar/firmware/bno085_test -e teensy41_uart
~/.local/bin/pio run -d platforms/loonar/firmware/bno085_test -e teensy41_uart -t upload
~/.local/bin/pio device monitor -p /dev/ttyACM0 -b 115200
```

출처: https://learn.adafruit.com/adafruit-9-dof-orientation-imu-fusion-breakout-bno085/pinouts
및 https://www.ceva-ip.com/wp-content/uploads/BNO080_085-Datasheet.pdf (§1.2.3).
