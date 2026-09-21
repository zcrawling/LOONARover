# MCU v2 설정과 검증

현재 코드는 로컬 빌드·소프트웨어 시험 단계다. 실제 업로드, 센서·모터 구동, Pi 서비스 시작은 하지 않았다.
이후 요청한 원격 USB 업로드와 모터 벤치 명령은 [사용자 실행 절차](motor_usb_bench.md)에 있다.
USB가 멈춘 장치까지 자동 복구하는 기능은 포함하지 않는다.

최신 사용자 확인: RoboClaw는 **M1=오른쪽, M2=왼쪽**이며 Motion Studio 튜닝 및
Write Settings를 완료했다. 이후 카메라부터 사용자가 직접 시험한다.
좌우 채널 수정과 해당 회귀시험은 코드에 반영했으며, 이 수정 이후 시험은 아직 실행하지 않았다.

## 파일과 설치 준비

- `firmware/control`: USB/UART, 두 태스크, BNO085, RoboClaw, RAM 버퍼, health.
- `tools/mcu_v2`: 역할별 backend, RAM 수신 버퍼, ROS bridge, 진단 도구.
- `cfs/apps/mcu_bridge`: 두 MCU의 health를 GroundLink `0x8007`로 전달.

Pi backend의 추가 apt 의존성은 `python3-serial`이다. ROS 패키지는 기존 배포 apt 목록을 따른다.
`deploy/install-runtime.sh`는 Python 코드, 실행 스크립트, unit, 설정 예제를 새 release에 설치한다.
서비스는 자동 enable/start하지 않는다. 로컬 수정만으로 기존 Pi release가 바뀌지는 않는다.

## 장치와 설정

1. Control/Payload 각각의 실제 UID와 `/dev/serial/by-id/` 경로를 확인한다.
2. `config/mcu-registry.example.json`을 `/etc/loonar/mcu-registry.json`에 복사하고 UID와 경로를 채운다.
   UART를 사용할 때는 transport와 해당 `/dev/` 경로를 지정한다.
3. RoboClaw baud/address를 실제 설정에 맞춘다. 코드 기본값은 115200/128이며, 사용자가 저장한 값과 일치해야 한다.
4. 차체 설정은 사용자 확정값을 반영했다: 반지름 0.098m, 중심 간격 0.210m,
   바퀴 1회전당 485681 count, 좌우 전진 부호 각각 +1. 기존 0 설정은 벤치 문서의 갱신 명령으로 교체한다.
5. `config/mcu-sensors.example.yaml`의 장착 frame과 covariance를 설정한다.
   0 covariance는 미측정 상태이며 시작을 차단하지 않는다. EKF 투입 전에는 실측값으로 바꾼다.

v2가 이미 설치된 장치의 HELLO 조회 명령은 다음과 같다. 실제 장치에 접근하므로 실기 단계에서 사용한다.

```bash
PYTHONPATH=platforms/loonar/tools python3 -m mcu_v2.inspect \
  --role control --discover-device /dev/serial/by-id/ACTUAL_CONTROL_DEVICE
```

기존 앱에 v2 HELLO가 없으면 이 조회는 응답하지 않는다. 최초 설치는 위 업로드 절차의 식별용 이미지를 사용한다.
UID를 지정한 컴파일은 [펌웨어 README](../firmware/control/README.md)를 따른다.
대상 UID가 다른 보드에서는 센서·모터 태스크가 주변장치를 구동하지 않는다.

## 서비스와 ROS

| 서비스 | 역할 |
|---|---|
| `loonar-mcu@control.service` | Control serial 단독 소유, Gateway 명령과 센서·health 전달 |
| `loonar-mcu@payload.service` | Payload serial 단독 소유, 공통 health 전달 |
| `loonar-mcu-sensors.service` | `/run/loonar/mcu/samples.sock` → ROS |
| `loonar-cfs.service` | `/run/loonar/mcu/health.sock` → cFS → 지상국 |

`/imu/data`는 gyro를 제공하고 orientation/accel은 covariance=-1로 표시한다.
가속도, 원시 quaternion, 자기장, 선형 가속도, 중력은 별도 topic으로 발행한다.
`/wheel/odom`은 드라이버 속도에서 얻은 twist이며 pose 추정은 robot_localization이 맡는다.
장착 TF·축·시각을 확인한 뒤 wheel vx + gyro z 구성으로 EKF에 연결한다.
상위 motion restrict는 유지하며 MCU에는 별도 속도/가속도 제한을 두지 않는다.

표본은 MCU/Pi RAM 버퍼와 ACK·재전송으로 전달한다. ROS는 200 ms보다 오래된 표본을 제어용으로 재발행하지 않는다.
Pi 프로세스 재시작·전원 차단 시 RAM 표본은 사라진다. 버퍼 초과는 카운터와 로그로 확인한다.

2026-09-20 사용자 지정 변경: RoboClaw ACK/조회 실패·오류에 따른 MCU 정지는 제거했다.
Pi의 health 1초 미수신은 보고만 하며, 기존 500 ms offline 표시 기준은 유지한다.
새 주행 명령이 200 ms 이상 없으면 MCU 목표 속도를 0으로 한다.
카메라 프로세스 종료 시 전체 벤치를 종료하는 동작과 나머지 정책은 유지한다.

## 로컬 소프트웨어 검증

저장소 루트에서 실행한다. 장치 접속이나 업로드 없이 실행할 수 있다.

```bash
cmake -S . -B build/mcu-v2-check -DBUILD_TESTING=ON
cmake --build build/mcu-v2-check -j2
ctest --test-dir build/mcu-v2-check --output-on-failure
PYTHONPATH=platforms/loonar/tools python3 -m unittest mcu_v2.test_v2 -v
```

단순화 이후 CTest 16개, Python unittest 14개, Control USB/UART 및 Payload USB 컴파일이 통과했다.
시험에는 CRC/분할 수신, 역할/UID 거부, RAM 버퍼 순서·중복·초과·재연결,
C++/Python 바퀴 명령 호환, 명령 만료, 89.99°C/90°C/90.1°C 정지 경계가 포함된다.
컴파일에 사용한 UID는 검증용이다. 실제 설치할 HEX는 실제 UID로 다시 빌드해야 한다.

## 이후 사용자가 수행할 실기 순서

| 순서 | 확인할 내용 |
|---|---|
| 카메라 | 기존 독립 영상 stream과 지상국 수신 |
| Teensy USB | 두 장치의 역할·UID·경로 구분, 반대 역할 연결 거부 |
| BNO085 | SPI 배선, 값·축·시각·실제 취득률, 분리 시 health 변화와 독립 모터 경로 |
| cFS/지상국 | 두 role의 UID·온도·online·age, 한 연결 종료 시 해당 role의 offline |
| 버퍼 | 짧은 연결 중단 후 중복 제거·연속 sequence, 용량 초과 시 drop/gap 표시 |
| 라이다/ToF | 독립 드라이버·frame·timestamp |
| 모터 피드백 | RoboClaw baud/address, count/speed 단위·부호, 전류·전압·온도·오류 |
| 모터·주행 | 명령과 실제 바퀴 동작, 200 ms 명령 만료, driver 조회 실패·health 미수신 시 보고와 명령 전달 지속, EKF 연결 |

90°C 조건은 소프트웨어 경계값 시험으로 확인했다. 보드를 과열시키는 시험을 요구하지 않는다.
실제 모터 정지 지연과 센서 통신 품질은 하드웨어에서 별도로 확인해야 한다.
진단 도구는 backend와 동시에 serial을 열지 않는다. backend 중지 후
`python3 -m mcu_v2.inspect --role control --seconds 5`로 health를 볼 수 있다.
이 조회는 새 session을 만들므로 이전 제어 session은 종료된다.
