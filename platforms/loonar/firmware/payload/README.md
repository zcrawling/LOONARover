# Payload Teensy 4.1

`src/main.cpp`의 Arduino 센서 앱이다. Control FreeRTOS/LNR2 펌웨어와 별개로
USB CDC 115200에서 ASCII 명령과 CSV를 주고받는다. 기본 `teensy41` 빌드는
`LOONAR_페이로드_핀맵_초안.xlsx`의 9월 센서 배선에 맞춘다.

| 센서 | 9월 핀맵 초안 배선 / 설정 |
| --- | --- |
| LIS3MDL | Wire SDA18 / SCL19, 50kHz, 0x1C 또는 0x1E 탐색 |
| MLX90614 | LIS3MDL과 같은 Wire SDA18 / SCL19, 50kHz, 0x5A |
| MAX31865 | SPI CS10 / MOSI11 / MISO12 / SCK13, 1MHz MODE1 |
| LIS3MDL INT, MAX31865 RDY | 초안에서 핀 미정. 펌웨어는 폴링으로 읽음 |
| RS-422 | 초안 제안은 Serial2 TX8 / RX7. 현재 펌웨어 통신은 USB CDC이며 RS-422 미사용 |

9월 문서는 **제안 핀맵**이며 실물 PCB의 전원·배선·센서 동작을 입증하지 않는다.
10월 [MCU_SENSOR PCB](../../hardware/pcb/261004_pcb/MCU_SENSOR/mcu_sensor.kicad_pcb)는
MLX90614가 Wire1 SDA17/SCL16, RS-422가 Serial1 RX0/TX1으로 다르다.
그 보드에는 `teensy41_mcu_sensor` 빌드를 사용한다. 두 빌드 모두 USB CDC만 사용한다.
5초 전원 대기, 기존 버스 안정화 대기와 센서별 최대 5회 재시도는 유지한다.

### 전원·통신 확인

- **9월 초안 보드 시험 전원:** USB 전원만으로 먼저 시험한다. 이 핀맵 문서에는
  PCB의 실제 5V 입력 회로가 확정돼 있지 않다. USB와 외부 5V를 동시에 사용할
  때에는 Teensy VIN–VUSB 연결과 보드 전원 경로를 먼저 확인한다.
  [PJRC 전원 설명](https://www.pjrc.com/store/teensy41.html).
- **RTD 기준저항:** 사용자 최종 확인값에 따라
  `RTD_REFERENCE_OHM = 4630.0f`로 설정한다. PCB U4의 `4.3k` 표기보다
  이 확인값을 우선한다.
  PT1000 3선식 설정도 실제 프로브와 모듈 점퍼 설정이 일치해야 한다.
  [Adafruit 기준저항 설명](https://learn.adafruit.com/adafruit-max31865-rtd-pt100-amplifier/python-circuitpython).
- **현재 Pi 통신:** USB CDC를 사용한다. 9월 초안의 RS-422는 송수신기 회로와
  실물 배선 확인 뒤 별도 구현이 필요하다.
- **MLX90614:** 9월 초안에는 전원 전압·실물 핀 방향이 미정이다. 실물 센서/모듈과
  PCB의 VDD/GND 및 SDA/SCL 배선, 3.3V 로직 전압을 확인한 뒤 전원을 넣는다.
  10월 PCB의 J3 커넥터는 별도 설계이며 1=GND, 2=3.0V, 3=SCL, 4=SDA다.
- **10월 MCU_SENSOR PCB:** 외부 전원 J1과 Pi USB 동시 사용에는 VIN–VUSB 분리가
  필요하다. PCB D1은 J1 쪽 다이오드이며 Teensy 내부 연결을 분리하지 않는다.
  저장소에 회로도 하위 시트 `modules.kicad_sch`, `infrared.kicad_sch`,
  `rs422.kicad_sch`, `testpoints.kicad_sch`가 없어 전체 ERC/PCB 일치 검증은
  완료되지 않았다.

Control의 BNO055 핀과 번호가 같아도 **서로 다른 Teensy**다.

## 빌드

저장소 루트에서:

```bash
C:\Users\subin\.platformio\penv\Scripts\platformio.exe run -d platforms/loonar/firmware/payload -e teensy41
```

9월 초안 보드용 산출물은 `.pio/build/teensy41/firmware.hex`다.
10월 PCB용은 `-e teensy41_mcu_sensor`로 빌드하며 산출물 경로도
`.pio/build/teensy41_mcu_sensor/firmware.hex`로 달라진다. 업로드 대상은 Payload 보드 tag로
지정한다. Control 보드의 tag를 재사용하지 않는다.

## START/STOP

- `START\n`: 센서를 재초기화하고 새 지점 측정. `CTRL,START,<station_id>` 응답.
- `STOP\n`: 시작 후 최소 5초 측정을 마친 뒤 PCA 행과 `CTRL,STOP,<station_id>` 출력.
- 센서 전원은 유지한다. STOP은 측정 종료이며 전원 차단 명령이 아니다.
- `model_params.h`는 DEMO_ONLY 모델이다. 실험으로 학습·검증된 판정 모델로 해석하지 않는다.

[Pi 서비스와 GCS 연동](../../porting/payload_pca_runbook.md),
[PC 직접 수집](../../tools/payload_pca_desktop.md).

## Pi 연동

[USB 프로토콜 v1](../../porting/payload_protocol.md): STATUS health, 요청 번호, ACK/DONE,
마지막 결과 조회를 지원한다. 초기화 대기·재시도는 단계별 실행하며 USB 폴링을 유지한다.
[배포와 실행](../../porting/payload_pca_runbook.md).
