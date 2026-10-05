# Payload Teensy 4.1

`src/main.cpp`의 Arduino 센서 앱이다. Control FreeRTOS/LNR2 펌웨어와 별개로
USB CDC 115200에서 ASCII 명령과 CSV를 주고받는다.

| 센서 | 배선 / 설정 |
| --- | --- |
| LIS3MDL | Wire SDA18 / SCL19, 50kHz, PCB ADDR=GND이므로 0x1C (0x1E 탐색도 유지) |
| MLX90614 | Wire1 SDA17 / SCL16, 50kHz |
| MAX31865 | SPI CS10 / MOSI11 / MISO12 / SCK13, 1MHz MODE1 |
| LIS3MDL INT / DRDY | 5 / 6, PCB 연결됨. 현재 펌웨어는 I2C 폴링으로 읽음 |
| MAX31865 RDY | 9, PCB 연결됨. 현재 펌웨어는 SPI 폴링으로 읽음 |
| RS-422 | Serial1 RX0 / TX1 → U2 THVD1451. 현재 펌웨어 통신은 USB CDC이며 RS-422 미사용 |

기준은 [261004 MCU_SENSOR PCB](../../hardware/pcb/261004_pcb/MCU_SENSOR/mcu_sensor.kicad_pcb)의
U1·U4·U5·J3 패드 net이다. 이전 Wire2 SDA25/SCL24는 이 PCB에서 미연결이다.
5초 전원 대기, 기존 버스 안정화 대기와 센서별 최대 5회 재시도는 유지한다.

### 전원·통신 및 새 PCB 설정

- **현재 전원:** Pi USB로만 공급하며 외부 전원 J1은 연결하지 않는다.
  USB 전원으로 동작하려면 Teensy VIN–VUSB 연결이 유지돼 있어야 한다.
  추후 J1 외부 5V와 USB를 동시에 사용한다면 VIN–VUSB 연결을 분리해야 한다.
  PCB D1은 J1 쪽 다이오드이며 Teensy 내부 VIN–VUSB 연결을 분리하지 않는다.
  [PJRC 전원 설명](https://www.pjrc.com/store/teensy41.html).
- **RTD 기준저항:** 사용자 최종 확인값에 따라
  `RTD_REFERENCE_OHM = 4630.0f`로 설정한다. PCB U4의 `4.3k` 표기보다
  이 확인값을 우선한다.
  PT1000 3선식 설정도 실제 프로브와 모듈 점퍼 설정이 일치해야 한다.
  [Adafruit 기준저항 설명](https://learn.adafruit.com/adafruit-max31865-rtd-pt100-amplifier/python-circuitpython).
- **현재 Pi 통신:** USB CDC를 사용하며 J2 RS-422는 사용하지 않는다.
  추후 RS-422 사용에는 MCU Serial1 처리와 Pi HAT 포트 설정이 별도로 필요하다.
- **MLX90614 커넥터:** J3는 1=GND, 2=3.0V, 3=SCL, 4=SDA다.
  사용하는 센서/모듈이 3.0V 전원에 맞는 사양인지 확인한다.
- 제공 폴더에 회로도 하위 시트 `modules.kicad_sch`, `infrared.kicad_sch`,
  `rs422.kicad_sch`, `testpoints.kicad_sch`가 없다. PCB 패드 net으로 핀을 확인했으며
  전체 회로도 ERC/PCB 일치 검증은 완료되지 않았다.

Control의 BNO055 핀과 번호가 같아도 **서로 다른 Teensy**다.

## 빌드

저장소 루트에서:

```bash
~/.local/bin/pio run -d platforms/loonar/firmware/payload -e teensy41
```

산출물은 `.pio/build/teensy41/firmware.hex`다. 업로드 대상은 Payload 보드 tag로
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
