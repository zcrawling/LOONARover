# 검증 기록

## 2026-10-06: 제동거리·낮은 턱·10 cm 명령 수정

- safety의 중심 기준 고정 35 cm 정지를 차체 크기와 실제 속도에 따른 제동
  영역으로 변경했다. 정지 여유, sensor_timeout, 반응시간, 가정 감속도를 포함하고
  회전 시 gyro/encoder 각속도와 차체 모서리 반경을 사용한다.
- 기본 35 mm 이하 지형은 독립 안전 감시에서 일괄 정지시키지 않는다.
  planner의 경사·요철·턱·낙차·unknown·신뢰도 검사는 유지한다.
- planner의 별도 최소 20 cm 구간 조건을 없앴다. 실제 명령거리가 10 cm 이상이고
  제동 여유가 남는 짧은 접근 구간도 허용한다. 안전거리로부터 명령거리를 줄이는
  계수와 최대 이동거리는 유지한다.
- Pi의 max_drive_distance=0.1에서 float32 action target=0.10000000149가
  한계 초과로 거부되는 오류를 수정했다. 한계를 wire float32 정밀도로 비교하고,
  0.1001 m는 계속 거부한다. 회전 한계도 같은 정밀도를 사용한다.
- 합성 단위시험 15개 통과(Python 10, C++ 5; colcon 합계 17은 wrapper 2개 포함).
  3 cm 턱 지형 생성 및 통과 가능 판정, 높은 턱 앞 10 cm 접근, 속도별 제동 영역,
  정지 gyro 노이즈, 미관측/낙차 거부를 확인했다.
- ROS 통합 기존 14개 통과 후 최종 변경 관련 3개를 재검증했다(기존 safety 2,
  신규 짧은 접근/낮은 턱/unknown planner 1). 별도 신규 10 cm action 경계 시험도
  통과했다. 10 cm 명령 완료 후 zero command, 10.01 cm 거부를 확인했다.
- Pi 접속 복구 후 core/safety/planner/bringup 및 motion 패키지 빌드·반영 완료.
  Pi local 설정의 사용하지 않는 두 거리 파라미터를 제거하고 원본은
  `log/20261006-braking/terrain-before.yaml`에 보관했다.
- 제동 감속도 0.20 m/s²와 추가 반응시간 0.10 s는 가정값이다. 이번 변경은
  차체 아래/주변 ToF 사각지대를 관측된 지면으로 바꾸지 않는다.
- 빌드/회귀 XML은 `log/*braking*`, `log/motion-limit-regression.xml`,
  Pi 실기 자료는 `log/20261006-braking/`에 모은다.

### 재연결 후 실제 10 cm 전진 시험 준비 결과

- 사용자가 Pi 전원 인가 및 실제 전진을 허용한 뒤 0.10 m / 0.03 m/s / timeout
  8 s의 단발 action 시험을 준비했다. 자율 반복 시작은 껐으며 시험 종료/예외 시
  ROS zero, motion stop, gateway STOP 및 프로세스 종료를 수행했다.
- 두 차례 실물 관측 모두 RoboClaw 상태 `0x02000000`이 지속됐다. 첫 실행에서는
  wheel 발행 차단의 결과인 `sensor/base missing or stale`만 나타났다.
  BaseState에 실제 드라이버 코드·boot hold·feedback age를 기록하고 safety가
  motor fault 원인을 먼저 표시하도록 수정한 뒤 재시험했다.
- 최종 관측: `MCU communication or motor fault: RoboClaw status 0x02000000`
  611회, boot hold가 함께 나타난 기동 표본 24회. 전진 action 발행 전 차단됐으며
  최대 선속도 명령 0, 마지막 cmd_vel=(0,0), 종료 AUTO=false를 확인했다.
- 이 코드는 제조사 Read Status 표의 Position Error Limit Warning이다.
  [RoboClaw 매뉴얼](https://downloads.basicmicro.com/docs/roboclaw_user_manual.pdf),
  [오차 한계 설명](https://resources.basicmicro.com/velocity-and-position-error-limit/).
  경고를 무시하거나 제어기 한계를 변경하지 않았다. Pi USB에는 control Teensy만
  보이며 RoboClaw 설정을 직접 읽을 별도 USB 연결은 확인되지 않았다.
- 모터 상태 코드 전달/정지 유지 및 safety 회귀시험 3개 통과 후 수정본을 Pi에
  빌드·반영했다. 실제 모터 전진 및 자율주행 성공은 아직 검증되지 않았다.
  경고 원인 점검과 앞서 확인한 unknown 사각지대 처리는 별도로 남는다.

## 2026-10-06 20:27 AUTO 미주행 진단

- 기존 gateway 로그에서 AUTO 수신 및 선속도/각속도 0을 확인했다. 조사 시작 당시
  사용자 실행은 이미 종료돼 있어, 당시 navigator가 멈춘 정확한 조건은 단정하지 않는다.
- 동일 Pi/실물 센서에서 모터 출력과 GCS 자동 시작을 끈 진단 실행으로 재현했다.
  cFS는 띄우지 않았으며 map 생성과 plan 서비스만 호출했다. 시험 후 진단 실행을 종료했다.
- 초기 관측 depth 전달 지연 중앙값 약 110 ms, p95 약 171 ms. 최신 gravity만
  비교하던 코드가 sync_tolerance 60 ms를 초과해 정상 프레임을 버렸다.
  safety/perception에 최대 64개 gravity 이력을 추가해 촬영 시각에 가장 가까운
  fresh 표본을 사용한다. sensor_timeout과 sync_tolerance를 늘리지 않았다.
- depth에 150 ms 전달 지연을 주는 합성 회귀시험을 추가했다. 정상/지연 입력의
  지도 생성·계획·충돌·센서 단절 및 navigator AUTO 관련 시험 8개 통과.
  x86 Jazzy 빌드와 Pi 변경 5개 패키지 빌드 완료.
- 수정 후 실물 관측: 기동 중 missing/stale 이후 `collision volume occupied`
  815회. 기동 직후 base fault 30회 뒤 정상 1,027회, 정지 확인 1,007회.
  depth/gravity 시간 불일치 메시지는 없었다. 전방 충돌 검출은 여전히 유효하다.
- 이전 같은 위치의 관측에서 충돌점 3,446개: 수평 정렬된 base_link 기준
  x=0.183~0.349 m, y=+0.071~+0.144 m, z=-0.028~+0.210 m.
  해당 점이 실제 어떤 물체인지 확인하지 않았으며 차체 자체로 임의 제외하지 않았다.
- 수정 후 실제 지도 생성 성공(map_id 1, valid_ratio 0.8157). 전체 heading 9개와
  forward-only 1개 모두 `rotation: unknown`, safe_distance 0으로 거부됐다.
  현재 위치의 footprint까지 관측을 요구하는 검사와 수평 전방 ToF의 사각지대가
  함께 남아 있다. 이 결과는 장애물 제거만으로 해결된다는 뜻이 아니다.
- navigator 대기 원인과 planner 후보 거부 이유를 로그/응답에 추가했다.
  실제 주행은 수행하지 않았으며 AUTO 주행 성공 상태로 검증된 것은 아니다.
- 진단 로그/관측 JSON/점군/재현 probe는 `log/20261006-auto/`, 합성 회귀 결과는
  `log/sync-regression.xml`에 모았다.

## 2026-10-06: PC/Pi 각 한 명령 실행

- `run_gcs_auto.sh`: PC 소스 복사, Pi 빌드, 기존 GCS 실행을 묶음.
- `run_auto.sh` / `start_auto_ros.sh`: 기존 motor_bench의 ROS launcher만 교체해
  gateway/cFS/backend/영상과 terrain stack을 함께 관리. 기존 bridge 중복 기동 없음.
- `gcs_auto_start`는 기본 false이며 통합 실행에서만 켠다. 신규 비-AUTO → AUTO
  선택으로 준비된 navigation을 시작, 모드 해제/통신·안전 오류 후에는 재선택 필요.
- 합성 ROS 통합시험 12개 통과(시작부터 AUTO일 때 대기, STOP→AUTO 시작,
  안전 해제만으로 재시작 금지, 재선택 후 재시작, GCS STOP 정지 포함).
  CAD TF launch smoke, backend registry/높이 변환 설정 시험 1개,
  기존/custom ROS launcher 표본 전달·프로세스 그룹 종료 시험 3개 통과.
- 셸 문법과 whitespace 검사 통과. 이 변경 시점 Pi `10.254.254.3`이
  `No route to host`여서 새 통합 실행의 Pi 배포·모터 실기는 수행하지 못했다.
  PC 실행 명령이 연결 복구 후 복사·빌드를 수행한다. 아래 ToF 실기 검증과 구분한다.

## 2026-10-06: STEP TF 적용 및 Pi ToF fault 수정

- 원본 STEP SHA256: `f37f89109957e3958b048365ac146ca31686b54c6dc067ca424b6cc132ddbc6b`.
  `loonar_description/config/cad_mounts.json`과 일치, CAD 프레임 시험 5개 통과.
- Pi aarch64 / Jazzy / SDK v2.5.9 / USB I200D에서 이전 helper의
  `libopencv_core.so.3.4` 로딩 실패(code 127)를 재현. `ldd`에서 OpenCV,
  FFmpeg, live555 간접 라이브러리 누락 확인. DT_RUNPATH → DT_RPATH 수정 후 모두 해소.
- SDK 원본: 640×480 depth/amplitude 142쌍, 약 15.17 Hz, 최초 프레임까지 2.69초.
  SDK destroy가 Released 이후 멈추는 현상 확인; bounded teardown 후 helper exit 0.
  USB 재접속 없이 후속 ROS 시험 성공.
- 기본 DDS 관측: CameraInfo 149개 대비 depth 28 / amplitude 34개.
  64 MiB SHM profile 후 25초(기동 포함)에 depth 248 / amplitude 249 /
  CameraInfo 249개, 동일 timestamp 248세트. depth 32FC1, 유효 비율 약 79.6%.
- 실물 ROS 시험에서 `base_link -> imu_link` yaw +90°, ToF optical 위치
  `[0.03575,0.00005,-0.0075]` m 확인. 모든 launch 프로세스 정상 종료.
- 최종 배포본 재시험도 통과: depth/amplitude/CameraInfo 동일 시각 224세트,
  유효 depth 약 80.3%, launch exit 0. 기존 `env.local.sh`도 새 `env.sh`를 읽도록 갱신했다.
- 과거 로그에는 ToF pipe EOF 외에 base_io exit 1도 있었으나 당시 traceback은
  저장되지 않았다. 현재 기존 `mcu_v2.ros_bridge`와 동시에 base_io를 시작하면
  같은 `ros-samples.sock`의 flock 충돌을 재현한다. 소켓을 빼앗지 않고 종료하며
  명시적 교체 안내를 추가했다. 이 충돌이 과거 종료의 유일 원인이었다고 단정하지 않는다.
- x86 Jazzy 전체 11개 패키지 빌드 및 통합시험 10개 통과. CAD TF를 확인하는
  launch smoke 통과. 첫 통합시험의 navigator 1건 timeout은 단독 재실행과
  전체 재실행에서 통과했으며 간헐적 DDS 타이밍 가능성은 남는다.
- SDK 실패의 상세 diagnostics, 음수 axle-relative collision 높이와 역전 범위
  거부를 회귀시험에 추가했다.
- 하드웨어 시험은 `run_base_io=false`, `enable_motion=false`, ROS domain 97.
  실제 자율주행/모터 출력/장애물 통과 시험은 수행하지 않았다. 기존 MCU/영상 프로세스와
  펌웨어는 이 작업에서 변경하지 않았다.
- Pi 시험 로그 및 JSON: `log/20261006/`. SDK 및 ROS 시험 재현:
  `tests/probe_sdk.py`, `tests/probe_tof_ros.py`.

광학 원점·거리 convention·IMU 위치는 실측 미완료다. CAD 축 적용과 광학 보정,
차체 사각지대 문제는 구분한다.

## 2026-10-04: 최초 합성 입력 검증

범위는 이 디렉터리에 추가한 ROS terrain-navigation MVP다. 기존 MCU/cFS/GCS
소스와 실제 장치·systemd 서비스는 변경하거나 실행하지 않았다.

## 실행 환경

- Ubuntu 24.04, ROS 2 Jazzy, Python 3.12.3, x86_64 Docker
- C++17 / Eigen, grid_map_core / grid_map_ros
- SDK helper: 별도 설치된 CubeEye x86_64 v2.5.11 release 헤더/라이브러리
- 하드웨어 대신 격리된 ROS domain, 합성 depth·IMU·encoder, 임시 UNIX socket 사용

## 통과한 검증

| 항목 | 결과 |
|---|---|
| 10개 ROS 패키지 colcon Release build | PASS |
| C++ geometry 시험 4개 | PASS |
| Python algorithm 시험 7개 | PASS |
| 실제 DDS/action/service 통합 시험 8개 | PASS |
| launch/YAML/xacro로 8개 노드 기동 및 정상 종료 | PASS |
| CubeEye SDK helper CMake build 및 링크 | PASS — 센서는 열지 않음 |
| shell 문법 | PASS |

colcon의 `13 tests` 합계는 11개 개별 단위시험과 CTest wrapper 2개를 포함한다.

통합 시험은 다음을 확인한다.

1. mm→m adapter, 이동 중 snapshot 거부, C++ 지형 생성, planner 및 map_id 검증
2. gyro 회전, encoder 직진 종료, action 취소/중복 거부, emergency/stale stop
3. 중력을 포함한 정지 판정, 바닥과 collision volume 구분, 센서 단절
4. heading 관측→회전→두 번째 관측→forward plan→직진 순서
5. no-safe-path의 bounded recovery와 SAFE_STOP, 전진 금지
6. 기존 MCU sample/gateway binary protocol, wheel count, command watchdog
7. snapshot timeout/cancel/정지 해제 및 잘못된 runtime parameter 거부
8. 실행기 SIGTERM 시 ROS context 종료 전에 zero command 발행

재현 명령은 `./test.sh`다. 로그와 XML은 `log/`, `build/`에 생성된다.
SDK 선택 빌드는 README의 `CUBEEYE_SDK` 경로를 별도로 지정한다.gㅠㅠㅠㅠㅠㅠㅠㅠ

## 실물에서 남은 검증

- Pi 5 + SDK v2.5.9 + I200DK의 실제 frame acquisition/15fps/latency
- depth scale 및 radial/axial convention, intrinsic/distortion, mount TF
- BNO085 gyro/gravity 축·부호·timestamp와 encoder geometry
- 실제 footprint/FOV 사각지대, step/slope/depression 정확도와 오검출률
- 회전 공간, 제동거리, 속도/물리 한계, slip 조건에서 stop-and-go 반복

기본 모션은 꺼져 있다. 실측 설정 없이 실차 주행 성공을 주장하지 않는다.
특히 현재 footprint나 회전 범위가 ToF 사각지대이면 unknown hard gate가
이동을 거부한다. 이를 해제하는 낙관적 지면 채우기는 구현하지 않았다.
