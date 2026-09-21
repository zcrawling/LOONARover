# LOONAR 추가 제한·보호 로직 검수

검수일: 2026-09-20 · 기준 소스: `d8833c8` · 대상: `/home/sb/LOONAR`

> **검수 이후 사용자 결정 및 수정:** 아래 본문은 수정 전 검수 기록이다.
> A1 RoboClaw 조회/ACK·오류 기반 주행 정지는 제거했다. A4 health 1초 미수신은
> 로그 및 기존 cFS/GCS 상태 보고만 하고 연결을 끊거나 STOP을 보내지 않도록 변경했다.
> A3 Pi 주행 명령 lease는 200 ms로 변경해, 마지막 새 명령 후 200 ms 이상이면 목표 속도가 0이 된다.
> A2 카메라 프로세스 종료 시 backend 종료와 나머지 항목은 사용자 지시로 유지했다.
> 적용에는 Pi backend 갱신과 MCU 펌웨어 업로드가 필요하며, 이번 수정에서 원격 배포/업로드는 하지 않았다.

## 판정

**요청했던 단순화가 저장소 전체에서 끝난 상태는 아니다.** 현재 주행 경로에도 요구사항에서 수치 근거를 찾을 수 없는 정지 조건과 입력 제한이 있다. 특히 RoboClaw 조회 실패를 주행 정지에 연결한 부분, 카메라 프로세스 종료를 전체 주행 지원 프로세스 종료에 연결한 부분은 우선 정리 대상이다.

반면 전자서명·공개키/개인키·펌웨어 SHA 검증·SQLite 영구 저장 후 ACK·IMU 상태 기반 주행 금지·추가 가속 램프는 **현재 LOONAR 실기 주행 경로에서는 발견하지 못했다.** SHA-256 보고서와 과거 실험용 제한은 별도로 남아 있다.

이번에는 실행 코드를 수정하지 않았다. SSH 접속, 펌웨어 업로드, 실제 주행·센서 시험도 하지 않았다. 이 문서만 추가했다.

## 범위와 판단 기준

소유 소스의 제한·거부·정지·재접속 조건을 검색하고, 시작 스크립트와 빌드 설정을 따라 현재 경로에 적용되는지 확인했다. 범위는 `platforms/loonar`의 펌웨어·Pi 도구·배포·systemd, `common/vehicle_gateway`, `cfs/apps`, `GCS`, ROS 브리지·localization·ToF/영상 도구, 기존 LIMO/실험 도구와 PCB 패키징 도구다. `platforms/rpi`에는 영상 설정 예제와 설명만 있다.

- **요청 기능:** Control/Payload MCU 구분, 90°C 이상 동작 제한, 송수신 버퍼와 health 보고, 명시적 STOP/Ctrl+C 정지.
- **추가 정책:** 센서나 조회 상태를 이유로 주행을 금지하거나, 요청에 없던 속도·시간·준비 조건을 강제하는 것. 타당한 목적이 있어도 요구사항과 같은 것으로 취급하지 않는다.
- **기본 처리:** 패킷 길이/CRC/숫자 유효성, 단일 직렬 포트 소유, 연결·파일 존재 확인. 모두 제거할 대상은 아니다.
- **관측·추정 조건:** 화면에 OFFLINE을 표시하거나 EKF 입력을 거르는 것은 모터 정지와 구분한다.

Pi의 `/opt/loonar/current`, 현재 실행 프로세스, Teensy에 실제 올라간 바이너리는 대조하지 않았다. 외부 SDK·Arduino/FreeRTOS·RoboClaw 내부 펌웨어·OS·패키지 매니저 내부까지 전수 검증한 결과도 아니다. 아래의 “현재 적용”은 **현재 저장소의 실기 시작/빌드 경로에 포함됨**을 뜻한다. 제공된 대화에서 근거를 찾지 못한 정책은 그렇게 표기했으며, 과거 모든 별도 요구까지 없었다고 단정하지 않는다.

## 현재 경로

```text
GCS start_loonar_gcs.sh
  → start_gcs.sh → webui.server --real-host → backend.real_app
  → TCP GroundLink → cFS ground_link → vehicle_adapter
  → vehicle_gatewayd → mcu_v2.backend → MCU v2 → RoboClaw

Pi start-ground-support.sh
  → mcu_v2.motor_bench
  → gateway + cFS + MCU backend + 선택적 video 프로세스

MCU PlatformIO
  → main.cpp + v2/*.cpp
  → MotionGate + RoboClaw
```

근거: [GCS 실기 실행](/home/sb/LOONAR/GCS/scripts/start_gcs.sh:69), [백엔드 선택](/home/sb/LOONAR/GCS/webui/server.py:107), [Pi 프로세스 구성](/home/sb/LOONAR/platforms/loonar/tools/mcu_v2/motor_bench.py:73), [MCU 빌드 필터](/home/sb/LOONAR/platforms/loonar/firmware/control/platformio.ini:17).

## 1. 현재 적용되는 추가 정지·제한 조건

### A1. RoboClaw 조회 실패도 모터 정지 조건으로 사용 — 우선 정리

현재 `driver_ok`는 다음을 **모두** 요구한다.

- 속도 명령 ACK를 받은 적이 있음.
- ACK 경과 시간이 100ms 미만.
- 오류 상태 조회 데이터가 500ms 미만으로 최신임.
- 오류 상태 값 전체가 정확히 `0`임.

하나라도 실패하면 `DriverStale`로 분류하고 양쪽 목표 속도를 0으로 만든다. 오류 비트별 구분은 없다. 특히 RoboClaw 엔진은 **일반 조회 응답이 10ms 안에 오지 않거나 CRC가 틀린 경우에도 `ack_seen=false`로 만든다.** 따라서 속도 명령 ACK 자체에 문제가 없어도 전압·온도·엔코더 등의 조회 실패가 다음 gate 판정까지 유지되면 정지로 이어질 수 있다. 이후 새 주행 명령과 정상 조건이 갖춰지면 다시 움직일 수 있어, 통신 상태에 따라 끊기는 현상도 가능하다.

이는 요청한 “입출력 값을 Pi로 전달”보다 강한 정책이다. **조회 정보의 신뢰도와 주행 명령 전달 상태를 한 조건으로 묶은 점**이 문제다. 오류 비트 중 어떤 것이 하드웨어 정지 사유인지는 별도 드라이버 명세/설정 확인이 필요하며, 모든 비트가 단순 경고라고 단정하지 않는다.

근거: [driver_ok](/home/sb/LOONAR/platforms/loonar/firmware/control/src/v2/runtime.cpp:429), [500ms 유효성](/home/sb/LOONAR/platforms/loonar/firmware/control/include/loonar/control/roboclaw.hpp:16), [10ms 조회 만료](/home/sb/LOONAR/platforms/loonar/firmware/control/include/loonar/control/roboclaw.hpp:34), [CRC 실패](/home/sb/LOONAR/platforms/loonar/firmware/control/include/loonar/control/roboclaw.hpp:102), [공통 실패 처리](/home/sb/LOONAR/platforms/loonar/firmware/control/include/loonar/control/roboclaw.hpp:186), [목표 속도 0 처리](/home/sb/LOONAR/platforms/loonar/firmware/control/include/loonar/control/motion_gate.hpp:43).

### A2. 카메라 종료가 주행 지원 전체 종료로 전파 — 우선 정리

`motor_bench.py`는 gateway, cFS, MCU backend, 선택적으로 video를 같은 `children` 목록에 넣는다. **어느 프로세스든 종료되면 전체 finally 정리로 들어가 나머지도 종료한다.** video를 함께 켰다면 카메라 분리·영상 인코더 종료가 MCU backend 종료 및 STOP 전송 시도로 이어진다.

카메라 상태에 따라 주행을 금지하라는 요구는 없었다. 독립적인 카메라 스트림 요구와도 맞지 않는 결합이다. 다만 별도의 systemd 서비스 구성에는 카메라 상태를 MCU 주행에 묶는 동일한 의존성이 없다. PC에서 영상 창을 닫는 것과 Pi의 송신 프로세스 종료도 구분해야 한다.

근거: [video를 같은 자식 목록에 추가](/home/sb/LOONAR/platforms/loonar/tools/mcu_v2/motor_bench.py:82), [하나라도 종료하면 예외](/home/sb/LOONAR/platforms/loonar/tools/mcu_v2/motor_bench.py:101), [전체 자식 종료](/home/sb/LOONAR/platforms/loonar/tools/mcu_v2/motor_bench.py:129).

### A3. 150ms 주행 명령 만료와 20~200ms 허용 범위 — 추가 정책

Pi는 모든 MOTION에 유효시간 `150ms`를 넣는다. MCU는 20~200ms 밖의 유효시간을 거부하고, 마지막 유효 명령 이후 시간이 만료되면 목표 속도를 0으로 만든다. 한 번의 속도 명령으로 계속 주행하는 인터페이스가 아니라 지속 갱신을 전제로 한다.

통신 단절 후 마지막 명령이 남는 것을 방지하는 목적은 분명하다. 그러나 **150/200ms라는 수치 자체는 사용자 요구에서 나오지 않았다.** 무조건 삭제할 장식적 검사와 같지는 않지만, 현재 별도 설명 없이 강제된 정책이다. GCS는 LOONAR 설정에서 50ms마다 갱신한다. 설정 로더는 50~1000ms를 허용하므로, 설정상 허용된 200~1000ms 주기를 선택해도 MCU의 150ms 만료와 충돌할 수 있다.

근거: [150ms 송신](/home/sb/LOONAR/platforms/loonar/tools/mcu_v2/backend.py:224), [허용 범위와 만료](/home/sb/LOONAR/platforms/loonar/firmware/control/include/loonar/control/motion_gate.hpp:30), [GCS 주기 검증](/home/sb/LOONAR/GCS/backend/config.py:21), [LOONAR 설정](/home/sb/LOONAR/GCS/config/loonar.toml:5).

### A4. health 1초 미수신 시 연결 종료·정지 — 보고 이상의 정책

Pi backend는 health를 100ms마다 요청한다. 응답이 1초간 없으면 예외를 발생시키고, finally의 `Link.close()`가 STOP을 전송한 뒤 직렬 포트를 닫는다. 이후 재접속한다. MOTION/모터 피드백만 정상이어도 health 응답 부재로 이 경로에 들어갈 수 있다.

사용자 요구는 health를 cFS→지상국에 보고하는 것이었다. **health 미수신을 직접 주행 중단으로 연결한 부분은 추가 정책**이며, A3의 명령 만료와도 별도다. 반면 500ms를 기준으로 health를 OFFLINE 표시하는 것은 관측용이며 직접 정지 명령을 만들지 않는다.

근거: [1초 health 예외](/home/sb/LOONAR/platforms/loonar/tools/mcu_v2/backend.py:226), [종료 시 STOP](/home/sb/LOONAR/platforms/loonar/tools/mcu_v2/link.py:126), [Pi OFFLINE 표시](/home/sb/LOONAR/platforms/loonar/tools/mcu_v2/backend.py:118), [cFS OFFLINE 표시](/home/sb/LOONAR/cfs/apps/mcu_bridge/fsw/src/loonar_mcu_bridge_app.c:79).

### A5. Gateway 수신 한 번에 64개를 처리하면 연결을 닫고 정지 — 추가 정책

Pi의 `Gateway.latest()`는 최대 64개 수신을 수행한다. 64개를 모두 읽고 루프 끝에 도달하면 실제 명령의 시각이나 남은 큐 개수와 무관하게 연결을 닫고 `(0,0)`을 반환한다. 이 값은 STOP으로 변환된다. “64개 이상 실제 주행 명령이 밀렸는지”를 구분하지도 않는다. 긴 대기를 줄이려는 구현이지만, **고정 처리 예산 초과와 주행 정지를 직접 연결한 정책**이다.

근거: [64회 수신 및 종료](/home/sb/LOONAR/platforms/loonar/tools/mcu_v2/backend.py:68), [0 명령을 STOP으로 변환](/home/sb/LOONAR/platforms/loonar/tools/mcu_v2/backend.py:211).

### A6. GCS 선속도 0.01~1.00m/s, 0.01 단위 강제 — 추가 입력 정책

웹 UI는 범위를 clamp하고 소수 두 자리로 반올림한다. 웹 서버와 실기 백엔드도 동일한 범위 밖 값을 거부한다. 0.005m/s 등 미세한 속도는 UI를 통해 지정할 수 없다. 후진은 양수 크기를 입력받아 음수로 변환한다. 정지는 별도 명령이므로 최솟값 0.01이 STOP을 막는 것은 아니다.

이 범위는 차량 기구값·드라이버 설정에서 계산한 한계가 아니다. 또한 백엔드 검사는 선택적 `linear_speed_mps` 인자에 적용되므로 시스템 전체의 일관된 속도 제한도 아니다. **불필요하게 여러 계층에 같은 UI 정책을 복제한 상태**다. 현재 MCU/Pi 속도 변환에는 이 상한이나 추가 가속 제한이 없다.

근거: [UI clamp](/home/sb/LOONAR/GCS/webui/static/app.js:53), [HTTP 거부](/home/sb/LOONAR/GCS/webui/server.py:81), [실기 백엔드 거부](/home/sb/LOONAR/GCS/backend/real_app.py:99), [Pi 변환](/home/sb/LOONAR/platforms/loonar/tools/mcu_v2/config.py:70).

### A7. cFS의 PAYLOAD/REACTION 진입 전 강제 STOP — 추가 모드 정책

`VA_Activity()`는 항상 `VA_Stop()`부터 호출하고 성공해야 PAYLOAD/REACTION 모드 선택과 실행 메시지 전달을 진행한다. payload 통신 요구만으로 반드시 주행 정지가 필요하다고 결론낼 수 없다. 현재 GCS 실기 백엔드는 이 두 명령을 아예 보내지 않으므로, **현재 웹 조작으로 진입할 수 없는 cFS 명령 경로에 있는 조건**이다.

근거: [선행 STOP](/home/sb/LOONAR/cfs/apps/vehicle_adapter/fsw/src/loonar_vehicle_adapter_app.c:200).

### A8. 2초 MCU watchdog, 주행 중 드라이버 통신 재설정 거부 — 존재하나 성격 구분

MCU IO task는 watchdog timeout을 2초로 설정하고 매 루프 feed한다. IMU task와 독립적이므로 IMU 불량 자체가 watchdog 리셋 조건은 아니다. 또 `gate.motion_seen` 상태에서는 RoboClaw baud/address 설정 변경을 거부한다. 사용자 요구에 명시된 기능은 아니지만, 각각 프로그램 정지 복구와 통신 중 재설정 충돌 방지다. 서명 시스템처럼 별도의 운영 절차를 요구하는 구조는 아니다.

근거: [watchdog](/home/sb/LOONAR/platforms/loonar/firmware/control/src/v2/runtime.cpp:405), [Configure 거부](/home/sb/LOONAR/platforms/loonar/firmware/control/src/v2/runtime.cpp:226).

## 2. 데이터 수신·ROS·ToF에 있는 추가 조건

다음은 **현재 수동 주행을 직접 막지는 않지만**, “센서 정보를 전부 받는다”는 기대와 다르게 데이터를 거르거나 전달을 지연시키는 조건이다.

| 항목 | 동작 | 판정 / 근거 |
|---|---|---|
| 시간 동기화 RTT 20ms | 왕복 시간이 0~20ms인 응답만 시간 offset 채택. 최초 동기화가 계속 실패하면 ROS 샘플 전달과 motor→gateway 상태 전달이 시작되지 않음 | 고정 수치의 근거 미확인. [link.py](/home/sb/LOONAR/platforms/loonar/tools/mcu_v2/link.py:92), [backend.py](/home/sb/LOONAR/platforms/loonar/tools/mcu_v2/backend.py:179) |
| 센서값 시각 -20~200ms | 미래 20ms 초과 또는 과거 200ms 초과 샘플을 ROS 브리지에서 폐기. Gateway 상태 전달에도 같은 조건 | 실시간 추정용 필터. 버퍼 재전송 성공과 ROS 전달 성공은 다름. [ros_bridge.py](/home/sb/LOONAR/platforms/loonar/tools/mcu_v2/ros_bridge.py:98) |
| wheel feedback age 100ms | 유효 bit가 없거나 age≥100ms이면 `/wheel/odom` 미발행 | 고정 신선도 조건. 모터 정지 조건과 별개. [ros_bridge.py](/home/sb/LOONAR/platforms/loonar/tools/mcu_v2/ros_bridge.py:173) |
| quaternion norm 0.9~1.1 | 범위 밖 orientation 샘플 폐기, 안쪽은 정규화 | 측정값 유효성 검사. gyro/모터 차단 아님. [ros_bridge.py](/home/sb/LOONAR/platforms/loonar/tools/mcu_v2/ros_bridge.py:148) |
| ToF 공간 필터 | `z>0.1m`, 원점 거리 `<5m`, 유한한 XYZ만 전달 | 거리를 하드코딩해 정보가 줄어듦. 주행 금지 기능 아님. [bridge.py](/home/sb/LOONAR/tools/cubeeye_ros/bridge.py:72) |
| ToF 기본 5Hz·stride 4 | 최신 프레임 한 개를 유지하고 각 축 4 간격으로 점을 뽑음. bag은 이 처리된 토픽을 기록 | 원본 모든 프레임/포인트 저장이 아님. 필터·성능 설정으로 분류. [run-tof.sh](/home/sb/LOONAR/platforms/loonar/deploy/run-tof.sh:28), [bridge.py](/home/sb/LOONAR/tools/cubeeye_ros/bridge.py:59) |
| ToF 장착 위치 필수 입력 | base TF 발행을 켜면 6개 위치/자세 설정이 있어야 시작. `TOF_PUBLISH_BASE_TF=false`이면 생략 가능 | 선택적 TF의 필수 입력 확인. 주행 인터록 아님. [run-tof.sh](/home/sb/LOONAR/platforms/loonar/deploy/run-tof.sh:10) |
| EKF sensor_timeout 0.1s | localization 추정기의 입력/예측 설정 | LOONAR launch는 EKF만 시작하며 모터 명령 발행 없음. IMU 기반 주행 금지가 아님. [EKF 설정](/home/sb/LOONAR/platforms/loonar/ros2/loonar_localization/config/loonar_minimal_ekf.yaml:13), [launch](/home/sb/LOONAR/platforms/loonar/ros2/loonar_localization/launch/loonar_minimal_ekf.launch.py:17) |

**ACK는 디스크 저장 완료가 아니다.** Pi의 RAM 버퍼 수용 후 ACK한다. MCU와 Pi의 버퍼는 각각 유한하며, MCU 버퍼가 가득 차면 새 샘플을 버리고 drop 수를 올린다. Pi의 프로세스 종료, MCU 재부팅, ROS 시각 필터 등에 대한 종단 간 무손실 보장은 없다. 버퍼가 꽉 찼다는 이유만으로 모터를 정지시키는 코드는 현재 경로에서 발견하지 못했다.

근거: [RAM ACK 경계](/home/sb/LOONAR/platforms/loonar/tools/mcu_v2/backend.py:174), [Pi 수신 버퍼](/home/sb/LOONAR/platforms/loonar/tools/mcu_v2/buffer.py:6), [MCU drop 처리](/home/sb/LOONAR/platforms/loonar/firmware/control/src/v2/runtime.cpp:97). 현재 ToF 기록 스크립트는 SQLite ACK 체계가 아니라 별도의 MCAP rosbag 기록이다. [record-tof.sh](/home/sb/LOONAR/platforms/loonar/tools/record-tof.sh:16)

## 3. 명시적으로 제거를 요청했던 항목의 잔존 여부

| 요청했던 제거 항목 | 현재 실기 경로 | 저장소 잔존 / 설명 |
|---|---|---|
| 전자서명·공개키·개인키 관리 | 발견하지 못함 | 자체 펌웨어 서명/검증 경로 없음. SSH·APT 자체의 표준 인증은 별개 |
| SHA-256 검증·해시 build ID·복잡한 firmware manifest | 펌웨어 빌드·업로드·주행 gate에는 발견하지 못함 | **배포 준비 보고서에 SHA-256/manifest 잔존**, PCB 도구와 오프라인 분석에도 존재 |
| 라이선스 자동 다운로드·별도 보관 절차 | 소유 배포/빌드 스크립트에서 발견하지 못함 | 의존성 패키지/SDK 자체의 라이선스 파일 동봉은 별개. 외부 빌드 도구 내부는 미감사 |
| SQLite 영구 저장 후 ACK | 없음: RAM 수용 후 ACK | 예전 bag 분석·보고서 도구의 SQLite 사용은 남음. MCU ACK와 무관 |
| IMU 이상 시 무조건 주행 금지 | 현재 MCU/Pi/GCS 경로에서 없음 | **과거 C/primitive 실험 실행 도구에는 IMU/추정 준비 조건 존재** |
| 요청 외 온도 기준 | 현재 v2는 MCU 내부 온도 ≥90°C | **구형 C control_core에는 95°C 잔존**. 현재 Teensy 빌드에서는 제외 |
| 추가 가속도 제한 | 현재 Pi→MCU→RoboClaw 경로에서 없음 | 과거 `c_ramp.py` 실험에 가속·감속 프로파일 존재. RoboClaw Studio 내부 설정은 이번에 확인하지 않음 |

현재 90°C 판정의 입력은 `tempmonGetTemp()`로 읽는 **Teensy 내부 온도**다. Pi CPU나 BNO085 온도가 아니다. RoboClaw 온도는 telemetry로 전송하지만 별도의 소프트웨어 온도 임계값 비교는 없다. 다만 A1의 드라이버 상태 전체 `error==0` 조건은 별도로 존재한다. 90°C에서 MCU 전원을 끄는 것이 아니라 모터 목표를 0으로 만들며 통신/health는 계속 수행한다.

### B1. 배포 SHA-256/manifest가 실제로 남아 있음

`record-preparation.py`는 바이너리와 HEX를 읽어 SHA-256을 계산하고 `~/loonar-staging/preparation-manifest.json`에 기록한다. 코드가 남아 있으므로 “해시 관련 구현을 전부 없앴다”는 답은 틀리다. 다만 이 결과를 업로드/주행 승인 조건으로 읽는 경로는 발견하지 못했다. 필수 런타임 절차가 아닌 수동 준비 보고서다.

근거: [출력 경로](/home/sb/LOONAR/platforms/loonar/deploy/record-preparation.py:18), [해시 계산](/home/sb/LOONAR/platforms/loonar/deploy/record-preparation.py:43).

PCB의 `rbphat-rebuild`와 `rbphat-xa-b4`에도 SHA 목록 생성과 PCB hash 불일치 시 제작 파일 패키징 중단이 있다. 로버 SW와 무관하지만 저장소 전체 기준으로는 잔존 항목이다. [B4 패키징](/home/sb/LOONAR/platforms/loonar/hardware/pcb/rbphat-xa-b4/package_artwork.py:7), [기존 보드 패키징](/home/sb/LOONAR/platforms/loonar/hardware/pcb/rbphat-rebuild/package_artwork.py:7). `tools/odom_v1/analyze.py`의 bag 해시는 오프라인 데이터 식별 용도다. [분석 코드](/home/sb/LOONAR/tools/odom_v1/analyze.py:105)

### B2. 구형 MCU 코드에 95°C 및 health 500ms 정지 조건 잔존

`control_core.h/.c`에는 `95000m°C`와 health 경과 `>500ms` 차단이 남아 있다. 루트 CMake에서는 이 소스를 host 라이브러리/테스트로 계속 빌드하지만, Teensy PlatformIO는 `main.cpp`와 `v2/*.cpp`만 빌드한다. **현재 Teensy에 95°C 제한이 적용된다는 뜻은 아니다.** 중복 구현과 요구사항 불일치를 없애기 위한 정리 대상이다.

근거: [구형 상수](/home/sb/LOONAR/platforms/loonar/firmware/control/include/loonar/control/control_core.h:13), [구형 정지 처리](/home/sb/LOONAR/platforms/loonar/firmware/control/src/control_core.c:39), [host CMake](/home/sb/LOONAR/platforms/loonar/firmware/control/CMakeLists.txt:1).

### B3. 과거 실험 코드에는 센서/녹화 준비 조건과 램프 잔존

- `c_ramp.py`: bias 준비·acceleration_valid·200ms 이내 진단값을 요구한 뒤 가속/감속 프로파일을 발행한다. **이 실험 도구를 직접 실행하면** IMU 준비 실패가 실험 주행을 막는다. [코드](/home/sb/LOONAR/common/ros2/loonar_localization/loonar_localization/c_ramp.py:35)
- LIMO `run_c_acc_trial.py`: bias/ToF/녹화 준비 상태를 확인한다. [코드](/home/sb/LOONAR/platforms/limo/tools/run_c_acc_trial.py:37)
- LIMO `run_primitive_trial.py`: 센서·EKF·녹화 준비, 250ms 센서 피드백 조건, recorder 종료 조건이 있다. 예외 시 최종 zero 명령을 발행한다. [코드](/home/sb/LOONAR/platforms/limo/tools/run_primitive_trial.py:44)
- `PrimitiveSequence`: 시작/구간 사이 정지 확인이 있어야 다음 이동 의도를 생성한다. 실기 GCS backend의 수동 제어와는 별도다. [코드](/home/sb/LOONAR/common/ros2/loonar_localization/loonar_localization/core.py:243)
- AprilTag 거리/primitive/C 실험에는 카메라·추적 실패 시 실험 중단과 원격 정지 절차가 있다. 거리 측정 실험의 성립 조건이며 현재 LOONAR 지원 스크립트에서 호출하지 않는다. [거리 시험](/home/sb/LOONAR/tools/apriltag_gt/loonar_apriltag/run_distance_test.py:236), [primitive 시험](/home/sb/LOONAR/tools/apriltag_gt/run_primitive_test.py:74)

따라서 “저장소 어느 곳에도 IMU 준비 조건이나 가속 램프가 없다”는 표현도 정확하지 않다. 다만 이 실험 목적의 코드들을 모두 억지 안전 기능이라고 판정할 근거는 없다.

## 4. 나머지 보호·구조 조건의 분류

| 항목 | 확인 결과 / 판단 |
|---|---|
| Control/Payload UID·role 구분 | 명시적 요구사항. registry 중복, 잘못된 role, 빌드 UID 불일치를 거부하는 것은 유지 대상. [config.py](/home/sb/LOONAR/platforms/loonar/tools/mcu_v2/config.py:1), [runtime.cpp](/home/sb/LOONAR/platforms/loonar/firmware/control/src/v2/runtime.cpp:571) |
| 최초 보드 등록 | 두 MCU 구분을 위해 실제 tag를 지정하고, 필요 시 UID 탐색용 이미지 후 UID가 묶인 이미지를 빌드한다. 서명 절차는 아님. 기존 firmware가 role을 응답하지 않는 최초 단계는 사용자의 올바른 물리 tag 지정에 의존함. [flash_control.py](/home/sb/LOONAR/platforms/loonar/tools/mcu_v2/flash_control.py:105) |
| session·boot·순서 번호·CRC | 옛 연결의 패킷, 잘못된 MCU, 중복/깨진 프레임을 구분하는 통신 처리. 임의의 서명/인증 인프라가 아님. session은 임시 숫자이며 공개키/개인키가 아님. [link.py](/home/sb/LOONAR/platforms/loonar/tools/mcu_v2/link.py:39), [MCU 수신](/home/sb/LOONAR/platforms/loonar/firmware/control/src/v2/runtime.cpp:175) |
| 순서 번호 소진 처리 | Pi request sequence가 uint32 끝에 도달하면 예외로 종료, MCU sample sequence가 끝나면 새 샘플을 버림. 자동 wrap 대신 중복 방지를 택한 장시간 운용상의 제한. MCU sample counter는 session만 바꿔서는 초기화되지 않음. [link.py](/home/sb/LOONAR/platforms/loonar/tools/mcu_v2/link.py:51), [runtime.cpp](/home/sb/LOONAR/platforms/loonar/firmware/control/src/v2/runtime.cpp:102) |
| GCS Host/Origin/CSRF 토큰 | 남아 있음. localhost Host와 Origin, 메모리 임시 토큰을 검사해 HTTP 명령을 거부할 수 있음. 키 파일·서명·사용자 로그인 절차는 없음. 타 웹페이지가 로컬 명령 API를 호출하는 것에 대한 작고 일반적인 보호로 분류. [server.py](/home/sb/LOONAR/GCS/webui/server.py:25) |
| GCS 연결/전송 중 버튼 제한 | 연결이 없거나 전송 중이면 버튼 비활성화. MCU temperature/IMU/health 값으로 웹 주행 버튼을 막지는 않음. keyup/blur의 zero와 명시적 STOP은 조작 종료 처리. [app.js](/home/sb/LOONAR/GCS/webui/static/app.js:7) |
| GCS PAYLOAD/REACTION 거부 | 실기 backend가 opcode 미정 사유로 항상 거부. **안전 기능이 아니라 미구현/연동 미완료**. 삭제만 해서 해결할 문제가 아님. [real_app.py](/home/sb/LOONAR/GCS/backend/real_app.py:93) |
| GCS 키 설정 고정 | 설정 파일을 읽지만 PAGE_UP/HOME/PAGE_DOWN/END/SPACE 외 값은 거부. 설정 형태와 달리 재매핑 불가. 임의 안전 장치보다는 불필요한 설정 중복. [config.py](/home/sb/LOONAR/GCS/backend/config.py:24) |
| 구형 mock GCS health gate | mock용 connection에는 PONG 6초 DEGRADED/20초 단절, 초기 status 조건, pending 200개 제한이 있음. 현재 `--real-host` 경로에는 적용되지 않음. [connection.py](/home/sb/LOONAR/GCS/backend/connection.py:105), [mock 설정](/home/sb/LOONAR/GCS/config/gcs.toml:10) |
| Gateway 자체 | 유한한 수치 검사와 MANUAL/AUTO 모드별 전달. 별도 속도·가속·IMU·온도 제한 발견하지 못함. AUTO는 AUTO 모드에서만 전달하는 경로 선택. [core.cpp](/home/sb/LOONAR/common/vehicle_gateway/src/core.cpp:34) |
| MCU/Pi 속도 계산 | 기구값으로 m/s, rad/s→wheel count/s 변환. 32bit 표현 범위 외 값 거부는 수치 오류 방지. RoboClaw command 37에 직접 속도 전송하며 추가 램프 없음. [config.py](/home/sb/LOONAR/platforms/loonar/tools/mcu_v2/config.py:70), [roboclaw.hpp](/home/sb/LOONAR/platforms/loonar/firmware/control/include/loonar/control/roboclaw.hpp:50) |
| systemd hardening | `NoNewPrivileges`, `ProtectSystem`, `ProtectHome`, 파일 존재 조건 등이 남아 있음. 동작 허가 인증은 아니지만 service에서 home 경로 설정을 쓰면 접근 문제를 만들 수 있음. 정상 `/etc`·`/opt`·`/run` 배치에서 주행 상태 판단과는 무관. [MCU service](/home/sb/LOONAR/platforms/loonar/systemd/loonar-mcu@.service:1) |
| 중복 실행 거부 | 직렬 포트 exclusive, flock, 동일 서비스/벤치 병행 금지 등. 동일 포트/소켓의 동시 소유 방지로 필요성이 있음. [motor_bench.py](/home/sb/LOONAR/platforms/loonar/tools/mcu_v2/motor_bench.py:46) |
| 카메라 빌드 소스 고정 | 정확한 revision이 아니거나 tracked 소스 수정이 있으면 빌드 거부. **편의상 고정한 추가 빌드 정책**. 실행 중 서명 검증과는 다름. [build-camera-stack.sh](/home/sb/LOONAR/platforms/loonar/deploy/build-camera-stack.sh:15) |
| Pi 펌웨어 빌드 금지 | aarch64에서 build를 거부하고 PC에서 빌드하도록 강제. 과거 FreeRTOS/newlib toolchain 문제의 우회책이며 보안 로직 아님. [board_config.py](/home/sb/LOONAR/platforms/loonar/firmware/control/board_config.py:9) |
| 설치 release/서비스 조건 | release 폴더 덮어쓰기 금지, 모든 관련 service 비활성 요구, 여러 준비 산출물 필수. 통합 준비 installer의 제약이며 “MCU만 교체”에도 써야 하는 필수 절차는 아님. [install-runtime.sh](/home/sb/LOONAR/platforms/loonar/deploy/install-runtime.sh:17) |
| SDK/영상/ToF 검사 | 실행 파일·장치·GStreamer element·입력 형식 존재 확인. 서명·라이선스 승인 절차는 발견하지 못함. 영상 queue는 지연 감소를 위해 프레임을 버리며 모터와 직접 연동하지 않음. [video-stream](/home/sb/LOONAR/common/video/loonar-video-stream:99) |
| SPEED_LIMITED 등 상수 | interface catalog와 생성 헤더에 이름은 있으나 현재 경로에서 실제 제한에 사용되는 호출은 발견하지 못함. 이름만으로 활성 제한이라고 판정하지 않음. [catalog](/home/sb/LOONAR/common/interfaces/catalog/reason_codes.yaml:24) |

## 5. 정리 우선순위

1. **조회/카메라와 주행의 불필요한 결합:** A1 RoboClaw 일반 조회 실패→주행 정지, A2 영상 프로세스 종료→주행 지원 전체 종료.
2. **요구사항에 없던 정책 정리:** A3 명령 만료 수치, A4 health 미수신 정지, A5 64개 수신 시 정지, A6 GCS 속도 범위, A7 payload 선행 정지. 통신 단절 처리 자체와 그 임계값/중복 구현은 나눠 결정해야 한다.
3. **명시적 제거 요청의 잔존물:** 준비 SHA/manifest, 구형 95°C/health gate 중복 코드. PCB/오프라인 분석까지 삭제 범위에 포함할지는 로버 실행 기능과 구분해야 한다.
4. **측정 데이터 제한 명시/조정:** ROS 시간 필터, wheel age, ToF 거리·주기·stride. 현재 bag을 원본 무손실 데이터라고 설명하면 안 된다.

UID/role 구분, 90°C 제한, CRC·길이·숫자 검증, 단일 통신 소유, 명시적 STOP을 일괄 삭제하는 것은 요청한 단순화와 맞지 않는다. 위 목록은 현재 동작을 드러내기 위한 검수이며, 새로운 정책이나 제한을 추가하자는 제안은 아니다.

## 6. 검증 증거

하드웨어를 연결하지 않는 기존 host/unit 테스트만 실행했다.

- `test_v2.cpp`를 현재 헤더로 임시 디렉터리에서 직접 컴파일/실행: 통과. wire, 90°C, motion lease, DriverStale, RoboClaw 조회 실패 동작 확인.
- `PYTHONPATH=platforms/loonar/tools python3 -B -m unittest mcu_v2.test_v2`: **14개 통과**. FakeSerial 및 임시 Unix socket 사용. RAM ACK/버퍼, UID 구분, 속도 변환 확인. C++ wire 호환성 하위 테스트는 기존 host 바이너리를 사용하므로 현재 소스 직접 빌드 결과와 구분한다.
- `PYTHONPATH=GCS python3 -B -m unittest discover -s GCS/tests -p test_real_backend.py`: **5개 통과**. 메모리 Writer 사용. 속도 범위 거부, PAYLOAD/REACTION 미전송, 실기 프레임 구성 확인.

테스트 통과는 해당 제한이 코드대로 존재한다는 근거다. 그 정책을 사용자가 요청했다거나, 실제 로버의 정지 시간·물리 동작까지 검증했다는 뜻은 아니다.
