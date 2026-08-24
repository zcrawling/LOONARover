# Control MCU firmware

이 디렉터리는 Teensy 4.1용 최소 Control MCU firmware다. Wire 규격의 단일 기준은
[`docs/control_mpu_if.md`](../../docs/control_mpu_if.md)다.

## 현재 데이터 흐름

```text
Serial1 RX buffer
  -> RX task: byte stream parse/decode
  -> latest-value queue
  -> Controller task: safety gate -> controller_tbd -> motor HAL
  -> status snapshot queue
  -> TX task: status encode -> Serial1 TX buffer
```

| 파일 | 책임 |
| --- | --- |
| `control_rx.c` | bounded stream parser와 `MPU_HEALTH`/`MOTION_CMD` decode |
| `control_core.c` | latest command와 health/temperature 차단 조건 평가 |
| `controller_tbd.c` | 실제 제어기 자리만 정의; 현재 motor duty는 항상 0 |
| `control_tx.c` | `MCU_STATUS` packet 생성 |
| `freertos_app.c` | RX, Controller, TX task와 depth-1 static queue 연결 |
| `teensy_hal.cpp` | UART, 온도, pin 초기화와 motor 출력의 Teensy adapter |
| `main.cpp` | board 초기화와 FreeRTOS scheduler 시작 |

Core, parser, packet encoder와 TBD controller는 FreeRTOS/Teensy header에 의존하지 않는 C99
코드라 PC에서도 같은 코드를 시험한다. task와 queue는 모두 정적 할당한다.

## Pin map

모든 board pin과 전기적 기본값은
[`include/loonar/control/board_pins.h`](include/loonar/control/board_pins.h) 한 파일에만 둔다.

| 기능 | Teensy 4.1 pin |
| --- | ---: |
| Status LED | 13 |
| MPU UART RX / TX (`Serial1`) | 0 / 1 |
| Left encoder A / B | 2 / 3 |
| Right encoder A / B | 4 / 5 |
| Left motor PWM / DIR / EN | 6 / 7 / 8 |
| Right motor PWM / DIR / EN | 9 / 10 / 11 |
| BNO085 SDA / SCL (`Wire`) | 18 / 19 |
| BNO085 INT / RST | 20 / 21 |

이 값은 Teensy 4.1 기능과 서로 충돌하지 않는 firmware 기본값이다. 실제 Control PCB pinout이
확정되면 이 헤더만 수정한다. compile-time 검사로 중복 pin 할당을 막는다.

## 의도적으로 비워 둔 부분

- `controller_tbd`는 입력을 받지만 항상 left/right duty 0을 반환한다. 따라서 현재 build는
  정상 packet을 받아도 motor enable을 켜지 않는다.
- Encoder와 BNO085는 pin/I2C만 초기화한다. sample 수집, encoder ISR과 제어 계산은 아직 없다.
- UART는 Teensy `HardwareSerial`의 interrupt-driven 고정 buffer(RX 256 B, TX 64 B)를 사용한다.
  별도 DMA 구현은 하지 않았다. 나중에 필요하면 `LnrControlHal` 내부만 교체한다.
- Motor polarity, enable polarity와 실제 driver 전기 조건은 PCB/driver 확인 뒤 pin header에서
  확정한다.

## Teensy 4.1 build

PlatformIO dependency는 재현 가능하도록 commit SHA로 고정했다.

```sh
cd firmware/control
pio run
```

결과물은 `.pio/build/teensy41/firmware.hex`에 생성된다. 보드 연결 후 upload는 다음과 같다.

```sh
pio run --target upload
```

## Host 검증

```sh
cmake --preset host-debug
cmake --build --preset host-debug
ctest --preset host-debug
```

Host test는 golden packet, fragmentation/resync/CRC, 30,000 packet soak, 200,000 random byte,
health 경계 500 ms, 95°C 경계, TBD controller의 항상-0 출력과 `RX -> Controller -> TX` 흐름을
검사한다.
