# LOONAR Rover Software

LOONAR는 Raspberry Pi 5 MPU와 Teensy 4.1 Control/Payload MCU를 사용하는 로버 프로젝트다. 현재 저장소에는 Control MCU minimal wire v1, bounded parser, FreeRTOS task 연결, host/HIL용 시험 기반이 포함되어 있다.

## MPU 기준 구조

```text
systemd: mcu-io | cfs | ros2 | camera
cFS:    LNR_CTRL | LNR_IO | GCS_IF
ROS 2:  loonar_bridge + 표준 localization/Nav2/vendor nodes
```

- Raspberry Pi 5: Ubuntu 24.04 arm64 + ROS 2 Jazzy
- I200DK: Ubuntu 24.04/Jazzy 포팅 후 실장 검증
- serial owner: `mcu-io`
- Camera owner: `camera.service`
- motion authority: `LNR_CTRL -> LNR_IO -> mcu-io -> Control MCU`
- 고용량 Camera/PointCloud/Payload raw data는 cFS를 우회

전체 설계 기준은 [`docs/README.md`](docs/README.md)에서 시작한다.

## 현재 Control MCU wire

- `MPU_HEALTH`, `MOTION_CMD`, `MCU_STATUS`
- 10-byte header, CRC32C, 최대 46-byte packet
- 500 ms MPU health timeout과 95°C overtemperature 정지
- heap 없는 bounded parser와 depth-1 latest queue
- 현재 실제 motor controller는 안전하게 0 duty를 반환하는 TBD 상태

상세 규격은 [`docs/control_mpu_if.md`](docs/control_mpu_if.md), firmware 구조는 [`firmware/control/README.md`](firmware/control/README.md)를 따른다.

## Build와 test

```sh
cmake --preset host-debug
cmake --build --preset host-debug
ctest --preset host-debug
```

Sanitizer:

```sh
cmake --preset host-asan
cmake --build --preset host-asan
ctest --preset host-asan
```

Catalog:

```sh
python3 tools/gen_catalog.py
python3 tools/gen_catalog.py --check
```

Teensy:

```sh
cd firmware/control
pio run
```

## 주요 디렉터리

```text
interfaces/catalog/       공개 numeric ID의 source
interfaces/generated/     생성된 C/C++ 상수와 문서
libs/wire_c/               공통 C99 wire codec
firmware/control/          Control MCU firmware
tests/                     unit/contract/SIL test
docs/                      software architecture와 ICD
```
