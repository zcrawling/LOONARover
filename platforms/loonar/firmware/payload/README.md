# Payload Teensy 4.1

`src/main.cpp`의 Arduino 센서 앱이다. Control FreeRTOS/LNR2 펌웨어와 별개로
USB CDC 115200에서 ASCII 명령과 CSV를 주고받는다.

| 센서 | 배선 / 설정 |
| --- | --- |
| LIS3MDL | Wire2 SDA25 / SCL24, 50kHz, 0x1C 또는 0x1E |
| MLX90614 | Wire1 SDA17 / SCL16, 50kHz |
| MAX31865 | SPI CS10 / MOSI11 / MISO12 / SCK13, 1MHz MODE1 |

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
