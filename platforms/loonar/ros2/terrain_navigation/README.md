# LOONAR stop-and-go terrain navigation MVP

## PC 한 명령 + Pi 한 명령

기존 Pi support/terrain 실행이 있으면 GCS STOP 후 해당 터미널에서 Ctrl+C로 먼저
종료한다. 같은 MCU/ToF를 두 실행기가 동시에 소유할 수 없다.

PC (복사·Pi 빌드 후 지상국 실행; SSH 비밀번호는 기존 loonar 계정):

```bash
bash /home/sb/LOONAR/platforms/loonar/ros2/terrain_navigation/run_gcs_auto.sh 10.254.254.3
```

Pi (통신·영상·CAD TF·ToF·자율주행을 함께 실행):

```bash
bash ~/LOONAR/platforms/loonar/ros2/terrain_navigation/run_auto.sh --video-ip 10.254.254.2
```

Pi 센서 기동 후 지상국에서 **STOP → AUTO**를 선택하면 시작한다. 별도 ROS service
호출이 필요 없다. STOP/MANUAL 전환, 센서/통신 오류 시 정지하며 오류 해소만으로
재시작하지 않는다. 다시 STOP → AUTO를 선택해야 한다. 초기부터 AUTO이거나 통신이
복구된 직후 AUTO인 상태도 자동 재생하지 않는다. AUTO 선택 후 준비를 최대
`phase_timeout` 동안 기다린다. 바닥 미관측 등 planner의 SAFE_STOP은 계속 유효하다.

Pi 명령은 가정값 기반 시험용 모션을 활성화한다. 센서 기동만으로 주행하지 않고
GCS 선택을 기다린다. 종료는 GCS STOP 후 Pi 터미널 Ctrl+C다.
영상 IP는 PC 주소, 첫 명령 IP는 Pi 주소다. `--record-all`은 별도 ToF 드라이버를
띄우므로 거부한다. 통합 실행은 기존 ROS bridge 대신 terrain launch를 시작하므로
수동 pkill/소켓 교체가 필요 없다. MCU radius/track/encoder registry는 backend와
base_io가 같은 파일을 사용하고, 생성 설정은 `log/auto-runtime.yaml`에 모은다.
ROS 로그는 `~/loonar-motor-bench/runtime/sensors.log`다.

### AUTO가 전달됐는데 움직이지 않을 때

GCS의 `AUTO Sent/Forwarded`는 명령 전달 상태이며 주행 준비 완료를 뜻하지 않는다.
Pi의 sensors.log에는 `AUTO blocked: ...`, `select GCS STOP then AUTO to arm/rearm`
등 대기 이유가 출력된다. `collision braking envelope`는 제동 영역의 높은 점 검출,
`rotation: unknown`은 회전 검사 영역의 미관측 바닥 때문에 정지한 것이다.
2026-10-06 실물 시험 당시에는 고정 35 cm collision box와 unknown 조건을 확인했다.
그 후 제동 영역 방식으로 수정했다. 정면 수평 ToF만 사용하는 현재
구성에서는 차체 아래/주변 사각지대가 남아, 장애물을 치우는 것만으로 경로가
허용된다고 보장할 수 없다. unknown 영역을 안전한 바닥으로 채우지는 않는다.

`MCU communication or motor fault: RoboClaw status 0x02000000`이면 거리 검사가
아니라 모터 드라이버의 위치 오차 한계 경고에 의해 차단된 것이다. 상태 비트를
무시하지 않으며, 드라이버 전원/상태 및 위치 제어 설정을 점검해야 한다. 이전에는
이 경우 유효 wheel 발행이 중단되면서 `sensor/base missing or stale`로만 보였지만,
이제 BaseState와 safety 메시지에서 실제 드라이버 상태 코드를 우선 표시한다.
코드 의미는 [제조사 매뉴얼의 Read Status](https://downloads.basicmicro.com/docs/roboclaw_user_manual.pdf)
및 [오차 한계 설명](https://resources.basicmicro.com/velocity-and-position-error-limit/)을 참조한다.

depth/IMU는 촬영 시각에 가장 가까운 IMU 이력을 사용한다. SDK 전달 지연으로
최신 IMU와 시간이 달라지는 정상 프레임을 거부하던 문제를 수정했으며, 실제
센서 timeout과 동기 허용 오차는 그대로 적용한다.

### 장애물까지 접근하는 거리와 낮은 턱 통과

높은 장애물이 있다는 이유만으로 35 cm 안에서 일괄 정지하지 않는다. 독립 안전
감시는 차체 앞끝부터 `max(stopping_margin, safety_margin) + v*T + v²/(2*a)`의
여유를 확보한다. `T = sensor_timeout + brake_reaction_time`, 기본 추가 반응시간은
0.10 s, 가정 감속도는 0.20 m/s²다. 바퀴 속도와 gyro/encoder 각속도를 사용하며
회전 중에는 차체 모서리 속도와 회전 반경도 포함한다. 정지 상태의 작은 gyro
노이즈는 회전으로 취급하지 않는다. 제동 성능은 아직 실측하지 않았다.

바닥 기준 `max_step_up` 이하의 점은 비상정지 사유로 삼지 않고 지형 계획기에
넘긴다. 기본 턱 높이 한계는 35 mm이고, 경사·요철·하강·낙차·관측 신뢰도를 함께
통과해야 이동한다. `collision_min_height`를 더 낮게 설정한 경우 그 보수적 기준은
유지한다. 낮은 점 하나를 검출했다고 통과 가능으로 확정하는 것은 아니다.

계획기는 높은 턱 앞의 관측된 안전 구간으로부터 실제 이동거리를 계산한다.
별도의 20 cm 최소 관측거리 조건은 제거했고, 제동 여유를 빼고도 최소 명령거리
10 cm가 나오면 짧은 전진 후보를 허용한다. 지나갈 수 있는 낮은 턱은 그 너머까지
평가한다. 오래된 설정의 `emergency_stop_distance`, `minimum_progress_distance`는
더 이상 사용하지 않는다.

모든 거리는 기준점을 구분해야 한다. 길이 30 cm 차체의 중심에서 18 cm인 물체는
앞끝과 3 cm, 중심에서 35 cm인 물체는 앞끝과 20 cm 떨어져 있다. 실제 명령은
차체 폭·안전 여유·지도 해상도까지 반영한 경로 검사 결과를 따른다.

기존 `run_pi.sh`는 계속 모터 비활성 관측용으로 사용할 수 있다.

구현·설정·실행 문서·시험을 이 디렉터리에 모은 ROS 2 Jazzy 워크스페이스다.
MCU, cFS, GCS, 기존 dead-reckoning 소스는 변경하지 않는다. 전역 지도,
SLAM, ICP, Nav2 제어기는 사용하지 않는다.

```text
STOP → measured STATIONARY → 3–4 depth frames → local map → heading
     → ROTATE → STOP → measured STATIONARY → NEW map → forward-only plan
     → short STRAIGHT → STOP → repeat
```

첫 관측의 이동거리는 버린다. 각 action은 고유 `map_id`와 ROS timestamp를
사용하며, planner는 오래된 지도·다른 map_id를 거부한다. 직진 거리는
`min(alpha * safe_distance, max_drive_distance, safe_distance - stopping_margin)`이고
최소거리보다 작으면 전진하지 않는다. 최소거리로 올려 clamp하지 않는다.

**기본 실행은 모션 비활성이다.** 제공된 치수·한계·URDF 장착값은 시험용 시작값이다.
실측 장착 TF, 카메라 depth convention, 차체 footprint, 제동거리 확인 후에만
`calibration_confirmed`, `enable_motion`을 켠다. 이 구현 과정에서 실제 로버를
움직이거나 실행 중인 systemd 서비스를 변경하지 않았다.

## 패키지

| 패키지 | 역할 |
|---|---|
| `loonar_msgs` | 지도/상태/판정 메시지, 두 action, planner 서비스, 향후 registration interface |
| `loonar_tof_adapter` | SDK 또는 ROS 입력, depth metre/invalid 정규화, 렌즈 보정, depth/amplitude 동기화 |
| `loonar_stationary_detector` | 좌우 wheel velocity, gyro norm/std, acceleration std, odom, primitive 상태 |
| `loonar_terrain_perception` | C++/Eigen 3–4 frame median/MAD, gravity 정렬, local grid, terrain layers |
| `loonar_terrain_planner` | 회전 swept footprint 및 직진 corridor hard gate, 후보 점수, RViz |
| `loonar_motion_primitives` | gyro 적분 회전, encoder 평균거리 종료, gyro heading hold, watchdog/취소/정지 |
| `loonar_terrain_navigator` | 비동기 action/service 상태 머신, 회전 후 재관측, bounded scan, SAFE_STOP/FAULT |
| `loonar_safety_monitor` | 별도 프로세스의 depth collision box, 자세/충격/통신/모터 오류 감시 |
| `loonar_bringup` | launch/YAML/URDF/RViz, 기존 gateway·MCU ROS 접속, rosbag/replay/metrics |
| `loonar_terrain_core` | 중복을 피하기 위한 공통 계산·ROS 유틸리티 및 단위시험 |

모든 노드는 독립 프로세스다. `run_adapter`, `run_stationary`, `run_perception`,
`run_planner`, `run_motion`, `run_navigator`, `run_safety`, `run_base_io` launch
argument로 개별 실행을 선택한다. 센서/안전 노드가 사라지면 모션은 계속하지 않는다.

## 빌드

Ubuntu 24.04 / ROS 2 Jazzy에서 이 폴더를 작업 디렉터리로 사용한다.

```bash
source /opt/ros/jazzy/setup.bash
rosdep install --from-paths . ../loonar_description --ignore-src -r -y
colcon build --base-paths . ../loonar_description --parallel-workers 2 --cmake-args -DCMAKE_BUILD_TYPE=Release
source install/setup.bash
./test.sh
```

주요 의존성: `rclcpp`, `rclcpp_action`, `rclpy`, `Eigen`, `grid_map_core`,
`grid_map_ros`, NumPy, OpenCV, tf2, robot_state_publisher, xacro.
point cloud nearest-neighbor/ICP/PCL 알고리즘은 구현하지 않는다.

호스트의 ROS와 Python ABI가 다르면 Ubuntu 24.04 Jazzy 컨테이너에서 실행한다.
이 폴더를 동일 작업 디렉터리로 mount하고 위 명령을 사용하면 된다.
검증 기록은 [VALIDATION.md](VALIDATION.md)에 있다. 테스트 결과는 `build/`, `log/`에만 생성된다. `test.sh`의 통합시험은 별도
ROS domain 97과 인접 domain에서 합성 센서/베이스만 사용한다. 다른 시험 domain은
`LOONAR_TEST_DOMAIN_ID`로 지정한다.

## Stage 1: I200DK acquisition

### 기존 ROS image driver

기본 `source: topics`의 입력은 다음이다. remap도 가능하다.

```text
/loonar/tof/input/depth        Image: 16UC1(mm 기본) 또는 32FC1(m)
/loonar/tof/input/amplitude    Image: 16UC1 / mono16 / 32FC1
/loonar/tof/input/camera_info  CameraInfo: 실제 intrinsic/distortion
```

depth/amplitude는 같은 크기·frame이고 `sync_tolerance` 안에 있어야 한다.
출력 depth/amplitude에는 동일 timestamp를 부여한다. depth는 항상 rectified
optical axial `32FC1` metre이고 invalid는 NaN이다. 입력 16bit scale은
`depth_scale`, radial range 센서는 `source_depth_is_radial`로 명시한다.
radial→axial 변환은 원본 왜곡 보정 ray를 사용한다. 이미 보정된 입력만
`source_rectified: true`로 설정한다. `/loonar/tof/raw_depth`와 보정 출력은
비교할 수 있으며, perception의 `spatial_median`은 기본 off다.

고정 출력:

```text
/loonar/tof/depth
/loonar/tof/amplitude
/loonar/tof/camera_info
```

기존 `tools/cubeeye_ros/bridge.py`는 XYZ 전용이므로 이 입력을 직접 제공하지
않는다. 새 adapter의 SDK 모드로 대체하거나 image driver를 연결해야 한다.
`/points`를 4번 만들거나 그 입력에 의존하지 않는다.

### SDK helper

SDK 자체는 저장소에 넣지 않는다. 기존 별도 설치 SDK를 지정한다.

```bash
colcon build --packages-select loonar_tof_adapter --cmake-args \
  -DCUBEEYE_SDK=/opt/loonar/vendor/cubeeye/2.5.9/release
```

`terrain.yaml`의 `source`를 `sdk`로, `helper`를 설치된
`install/loonar_tof_adapter/lib/loonar_tof_adapter/cubeeye_capture`의 **절대경로**로
설정한다. helper의 ELF RPATH가 SDK 및 vendor 간접 의존성 경로를 포함하므로
현재 배포 경로에서는 별도 `LD_LIBRARY_PATH` 설정이 필요하지 않다.

helper는 depth+amplitude와 카메라 intrinsic/distortion을 읽어 bounded queue로
전달한다. 센서 한 개만 허용한다. 같은 SDK timestamp의 두 frame만 짝짓고,
ROS timestamp에는 callback의 host clock을 사용한다. 오래된 pipe 데이터는
버린다. vendor SDK는 ROS perception과 직접 링크되지 않는다.
기존 ToF 서비스와 SDK helper가 동시에 같은 USB 장치를 열면 안 된다.
2026-10-06 Pi SDK v2.5.9 + I200D에서 640×480 depth/amplitude 약 15 Hz를 확인했다.
이전 RUNPATH 빌드는 vendor OpenCV/FFmpeg/live555 간접 라이브러리를 찾지 못해
code 127로 종료했다. 수정된 RPATH 적용에는 helper 재빌드가 필요하다.
SDK destroy가 멈추면 stop 완료를 확인한 뒤 2초 후 격리 helper를 종료한다.
adapter diagnostics에 helper 종료 코드와 마지막 SDK 메시지가 남는다.
거리 단위의 절대 정확도·radial/axial convention·FOV와 광학 중심은 추가 실측 대상이다.

### Pi 관측 실행 (CAD TF 포함)

Pi 빌드는 `--base-paths . ../loonar_description --build-base build/pi5
--install-base install/pi5`를 사용한다. 복사할 때 인접한 `../loonar_description`도
함께 복사한다. SDK와 registry/socket 경로가 설정된 `terrain.local.yaml`이 있을 때:

```bash
cd ~/LOONAR/platforms/loonar/ros2/terrain_navigation
bash run_pi.sh
```

기본은 ToF/CAD TF 관측이며 모션과 base_io는 비활성이다. 기존 MCU bridge·영상은
유지할 수 있지만 다른 ToF driver와 같은 USB 장치를 동시에 열면 안 된다.
subscriber 터미널에서도 `source ./env.sh`로 환경을 맞춘다.
`loonar_bringup/config/fastdds.xml`은 64 MiB shared-memory segment를 사용한다.
Pi 기본 크기에서는 1.2 MiB float 이미지가 누락되어 CameraInfo만 정상 수신될 수 있다.
launch도 이 프로파일을 기본 적용하며 명시한 외부 프로파일은 유지한다.

하드웨어 관측 시험은 모터 또는 MCU에 연결하지 않는다:

```bash
source ./env.sh
ROS_DOMAIN_ID=97 python3 tests/probe_tof_ros.py "$PWD/terrain.local.yaml" \
  --seconds 25 --output log/tof-cad-check.json
```

주행 연결은 기존 ROS sample 소비자를 종료한 다음 `run_base_io:=true`로 실행한다.
이미 소켓을 사용하는 bridge가 있으면 base_io는 소켓을 빼앗지 않고 명시적 오류로 종료한다.

## 기존 MCU와 ROS 연결

현재 MCU ROS bridge는 `/imu/data`(gyro), `/imu/accel`, `/imu/gravity`,
`/imu/orientation_raw`, `/wheel/odom`으로 분리 발행한다. 새 `base_io`는 같은
backend sample protocol을 읽으면서 다음을 추가한다.

```text
/wheel_states       JointState: left_wheel/right_wheel, radians, radians/sec
/odom/raw           Odometry: encoder-derived vx/wz (pose는 측정하지 않음)
/loonar/base/state  BaseState: fresh motor feedback, motor fault, AUTO selection
/cmd_vel           Twist subscriber → vehicle_gateway ros.sock AUTO command
```

기존 `/wheel/odom`과 분리 IMU 토픽도 계속 발행하여 기존 EKF를 유지한다.
실제 누적 encoder count를 사용하고 32bit wrap을 처리한다. MCU boot 변경 때는
모션을 정지시키고 잠시 fault를 발행한다. 오류 필드가 없거나 count/speed가
오래된 motor sample을 정상 상태로 간주하지 않는다.

`base_io`를 사용할 때는 **기존 `loonar-mcu-sensors`와 동시에 실행하지 않는다**.
둘은 같은 `/run/loonar/mcu/samples.sock`의 소비자다. lock은 중복 소유를 거부한다.
MCU serial을 소유하는 `mcu_v2.backend`, gateway, cFS는 그대로 사용한다.
`registry`의 실제 control UID와 geometry를 읽으며, 모터 명령 scale은 기존
backend에서 계속 계산한다. 다른 플랫폼/시뮬레이터에서는 `run_base_io:=false`로
위 ROS 계약만 제공하면 된다.

GCS/cFS에서 STOP → AUTO를 선택해야 ROS 명령이 전달된다. ROS 쪽에서 MANUAL이나
STOP 모드를 강제로 해제하지 않는다. gateway 재접속 시 이전 명령을 재전송하지
않고, ROS command가 끊기면 zero를 한 번 보낸다. 최종 프로세스 종료/통신 단절은
기존 MCU의 200ms MOTION lease도 담당한다.

## TF와 gravity

```text
odom                 기존 EKF만 동적 TF 소유
  base_link          x forward, y left, z up
    tof_link
      tof_optical_frame   x right, y down, z forward
    imu_link
    terrain_local    현재 STOP snapshot의 gravity-aligned frame
```

`publish_tf:=false`가 기본이다. 실제 URDF/TF가 이미 있으면 중복 발행하지 않는다.
`urdf/loonar.urdf.xacro`는 인접 `loonar_description`의 STEP 기반 URDF를 포함한다.
base_link는 지면이 아닌 바퀴 축 중앙이다. IMU yaw=+π/2,
ToF 장착 위치는 `[0.03575, 0.00005, -0.0075]` m, 장착 roll은 −π/2다.
10월 7일 raw 영상의 왼쪽이 아래를 향하는 방향을 TF에 반영했다.
terrain wrapper가 필요한 `tof_optical_frame`만 추가한다. AG12847 CAD 렌즈
기준점까지 전방 15.99 mm를 더해 합성 위치는 `[0.05174, 0.00005, -0.0075]` m다.
광학 주점 실측값은 아니며, 지면 기준 높이를 임의로 바꾸지는 않았다.
camera optical frame은 발행하지 않는다.
IMU 위치는 명목값이며 CAD 부품 원점과 실측 광학 중심은 구분한다.
기존 임시 `robot.local.urdf`에는 예전 값이 남을 수 있으므로 기본 wrapper를
사용하거나 새 wrapper로 해당 파일을 다시 생성한다.

2026-10-07 ToF 수정: SDK `FrameDropped`는 횟수를 기록하고 계속 수신한다.
다른 SDK 오류와 파이프 실패는 실패 종료 코드로 보고한다. SDK 콜백에서
depth/amplitude를 복사한 뒤 별도 스레드가 전송하므로 느린 수신기가 콜백을
붙잡지 않는다. 전송 중인 패킷은 끝까지 보내고 대기 슬롯은 최신 프레임 하나만
유지한다. 과부하에서 교체된 프레임은 `pending_frames_replaced`, SDK 드랍은
`sdk_frame_dropped`로 5초마다 로그에 남는다. 드랍 0개를 보장하는 변경은 아니다.

Pi 연결 후 센서만 60초 검증하려면 기존 센서 프로세스를 종료하고 실행한다:

```bash
cd ~/LOONAR/platforms/loonar/ros2/terrain_navigation
python3 tests/probe_sdk.py install/pi5/loonar_tof_adapter/lib/loonar_tof_adapter/cubeeye_capture --seconds 60
```

먼저 `loonar_description`, `loonar_bringup`, `loonar_tof_adapter`를 다시 복사/빌드해야
한다. probe는 도중에 helper가 종료되면 종료 코드가 0이어도 실패 처리한다.
로컬 검증 결과는 `fly_brain/analysis/20261007/tof_fix_validation/validation.json`과
`summary.json`, 재생 코드는 같은 상위 폴더의 `calibration_replay.py`에 있다.

collision 높이와 self_z_min/max도 base 축 기준이다. 기존 지면 기준 높이에서
바퀴 반지름을 빼서 변환한다. 기본 YAML은 반지름 0.098 m 기준,
Pi의 0.100 m 가정 설정에서는 collision `[-0.03, 0.60]`, self `[-0.08, 0.40]` m다.
CAD spindle 간격을 엔코더 wheel_track 보정값으로 복사하지 않는다.

`/imu/gravity`는 IMU frame에서 **정지 시 위를 향하는 중력 보상 벡터**(평지에서
약 `[0,0,9.81]`)여야 한다. 현재 backend의 SH2/BNO gravity 계약을 따른다.
imu→base static rotation을 먼저 적용하고 그 roll/pitch로 depth를 정렬한다.
센서 raw quaternion/자계 yaw를 그대로 신뢰하지 않는다. accelerometer 평균이
0인지 검사하지 않는다. 다른 IMU driver를 쓸 때는 이 gravity topic과 가속도
계약을 맞춰야 한다. gyro는 base frame으로 회전한 rad/s다.

지도는 매 snapshot 새로 만들고 현재 map_id 하나만 planner에 남긴다.
`terrain_local` TF는 snapshot 시각에만 유효한 시각화용 TF다. 주행 중 지난 지도를
계속 최신 지도처럼 표시/사용하지 않는다. 과거 위치에 고정한 장기 지도는 없다.

## 관측 및 주행

```bash
ros2 launch loonar_bringup terrain.launch.py \
  params_file:=/absolute/terrain.yaml

# 정지 센서·TF 확인 후 지도만 요청
ros2 action send_goal /loonar/build_terrain_map \
  loonar_msgs/action/BuildTerrainMap '{frame_count: 4}' --feedback

# 결과 map_id로 계획만 요청
ros2 service call /loonar/plan_terrain loonar_msgs/srv/PlanTerrain \
  '{map_id: 1, forward_only: false, previous_heading: 0.0}'

rviz2 -d install/loonar_bringup/share/loonar_bringup/rviz/terrain.rviz
```

실측 설정과 AUTO 선택을 완료한 시험 환경에서:

```bash
ros2 launch loonar_bringup terrain.launch.py \
  params_file:=/absolute/measured-terrain.yaml \
  run_base_io:=true calibration_confirmed:=true enable_motion:=true
ros2 service call /loonar/navigation/start std_srvs/srv/Trigger '{}'
ros2 service call /loonar/navigation/stop std_srvs/srv/Trigger '{}'
```

`autostart`는 기본 false다. `STOP`, `STRAIGHT`, `ROTATE` primitive는 별도 action으로도
시험 가능하다. STOP/취소/오류 결과 후에는 zero command를 내고 stationary detector의
확인을 따로 기다린다. 회전은 gyro 적분(±π wrap 없음), 직진은 좌우 누적 encoder의
평균거리와 gyro heading hold를 쓴다. encoder를 실제 ground distance의 truth나
항상 과대추정하는 hard constraint로 사용하지 않는다.

파라미터는 `ros2 param set /노드이름 파라미터 값`으로 바꿀 수 있다.
진행 중인 snapshot/primitive/상태 전이는 먼저 멈춰야 한다. 설정 변경은 해당 노드에만
적용되므로 공통 footprint·물리 한계·안전 값은 YAML을 함께 수정해 다음 실행에
동일하게 적용한다. 잘못된 범위·NaN·불일치 geometry는 거부한다.

## 지도와 hard gate

`/terrain/grid`는 실제 `grid_map_msgs/GridMap`, `/terrain/map`은 map_id와
x-major (`ix * size_y + iy`) cell 배열을 가진 planner용 메시지다.

독립 layer: elevation/min/max/variance/MAD, point_count, confidence,
slope, gradient_x/y, cross_slope, roughness, step_up/down, depression_depth,
drop_suspect, observed, unknown, traversability.

pixel-wise valid median/MAD 후 한 번만 subsampled projection한다.
cell elevation도 median을 사용하며 local plane은 Huber IRLS,
roughness는 plane residual MAD와 cell MAD를 사용한다.
step은 local slope를 제거한 여러 주변 cell의 차이 및 cell 내부 높이 범위를 검사한다.
측정된 depression은 연결영역으로 묶어 `/terrain/depression_regions`에 치수를 표시한다.
관측된 바닥의 전방 경계 뒤 빈 cell은 drop_suspect다. 보이지 않는 구덩이 깊이를
추정하지 않는다. 단순 경계 검출이므로 센서 range/FOV 경계도 보수적으로 suspect가
될 수 있다.

후보는 footprint polygon(현재 구현은 rectangle+rear tail extent)을 회전·전진 sweep한다.
반 cell 간격과 cell 대각선만큼의 여유로 경계 누락을 방지한다. 모든 hard gate를
통과한 후보만 score/turn/history/progress 비용을 비교한다. cross slope는 각 heading에
맞춰 gradient로 계산한다. 기본 unknown 허용 비율은 0이다.

**전방 ToF의 사각지대는 자동으로 채우지 않는다.** 현재 차체 footprint 아래 또는
회전 경로가 unknown이면 flat map처럼 처리하지 않고 거부한다. 실제 장착에서 전체
swept footprint가 보이지 않으면 이 보수적 MVP가 전혀 움직이지 않을 수 있다.
그 경우 관측 가능한 장착/센서 커버리지를 먼저 확보해야 한다. 단순히 x_min을
줄이거나 max_unknown_ratio를 늘리는 것은 관측 확보가 아니다.

no-safe-path의 기본 결과는 SAFE_STOP이다. 안전한 회전 공간을 별도로 확인한 시험에서만
`recovery_rotation_clearance_verified`를 켜면 작은 회전→정지→새 관측 scan을 수행한다.
누적 회전 한도는 기본 2π이며 실패 시 SAFE_STOP을 발행한다. 이 플래그는 rear/side
사각지대가 안전하다는 자동 센서 증거가 아니다. 회전 중에도 독립 safety monitor는
계속 동작한다. 전체 바퀴/꼬리 track별 평가와 360° collision guard는 후속 확장이다.

독립 RViz 출력은 `/terrain/elevation`, `/terrain/slope`, `/terrain/roughness`,
`/terrain/step`, `/terrain/depression`, `/terrain/unknown`, `/terrain/drop_suspect`,
`/terrain/traversability`, `/terrain/candidate_paths`, `/terrain/selected_path`,
`/tof/fused_points`다. PointCloud2 layer는 RViz Intensity transformer의 channel로
해당 layer 값을 선택하거나 GridMap display를 사용해 확인한다.

## rosbag와 offline replay

```bash
ros2 run loonar_bringup record_terrain /absolute/new-bag
```

센서 원본, 보정 depth/amplitude/info, gravity/IMU, wheel/odom, stationary,
terrain map/grid/decision, primitive goal/status/result, safety, base 상태,
cmd_vel, TF, diagnostics를 기록한다.

하드웨어가 없는 별도 ROS domain에서 재생한다. 예: 모든 터미널에 `ROS_DOMAIN_ID=96`.

```bash
ros2 launch loonar_bringup terrain.launch.py use_sim_time:=true \
  run_adapter:=false run_motion:=false run_navigator:=false run_safety:=false
ros2 run loonar_bringup snapshot_replay --ros-args -p use_sim_time:=true
ros2 run loonar_bringup replay_terrain /absolute/bag
```

replay 스크립트는 **측정값과 상태만** 재생하고 기록된 `/cmd_vel`은 재생하지 않는다.
정지 판정의 motion status는 bag에서 공급한다. snapshot_replay는 정지 구간에서
새 action을 요청하고 planner를 호출한다. 계산은 ROS timestamp를 사용한다.
매우 빠른 재생에서는 DDS drop/실행 여유시간에 따라 수집 frame이 달라질 수 있으므로
동일 수치 비교는 동일 입력 snapshot 또는 정상 속도 재생으로 한다.

## 검증 및 실물 시험

자동화 검증:

- 3/4-frame valid median, outlier/MAD, 평지/경사/턱/함몰/unknown/drop
- footprint 밖/unknown/drop/저신뢰/높은 턱·경사 hard rejection
- 최소거리 때문에 safe distance를 초과하지 않는 command distance
- 중력을 포함한 stationary 판정, moving/stale/clock reset
- 실제 ROS adapter→C++ perception→planner action/service 연결
- gyro 회전, encoder 종료, 취소·중복 goal·비상정지·센서 중단
- 실제 ROS 상태 머신의 회전 후 새 capture, bounded recovery/no-forward

이 테스트는 실물 지형 정확도·Pi 5 latency·제동거리 검증을 대신하지 않는다.
최초 실물 순서는 acquisition → 정지 fusion → gravity 평면 → 각 layer →
정적 planner → 회전 단독 → 회전 후 재관측 → 20–25cm 직진 → 전체 loop다.

줄자로 측정한 flat, +5/+10cm step, -5/-10cm depression, 경사판, 자갈,
한쪽만 높은 지형, 부분적으로 보이지 않는 drop을 각각 bag으로 기록한다.
`config/fixture_reference.example.json`을 실측 ROI와 값으로 바꾼 뒤:

```bash
ros2 run loonar_bringup terrain_metrics --ros-args \
  -p reference:=/absolute/fixture-reference.json \
  -p output:=/absolute/reports/terrain-metrics.jsonl
```

각 ROI의 높이·경사·roughness·step·depression median/max/GT MAE,
unknown/drop 비율, safe-ground false-positive ratio를 남긴다. slope 단위는 rad다.
턱/구덩이 ROI는 edge·바닥을 구분해야 값 비교가 의미 있다. 반복 bag에서 roughness
재현성, 좌/우 선택, oscillation, 취소/오류 후 마지막 `/cmd_vel==0`도 확인한다.

향후 `StopRegistration.srv`의 delta_pose/quality를 별도 `loonar_tof_registration`
노드가 제공할 수 있다. 현재 해당 service의 구현이나 odom correction은 없고,
perception/action 성공 여부와 분리되어 있다. Nav2 layer도 현재 범위에 넣지 않았다.
