# LOONAR 최소 Local Odometry (ROS 2 Jazzy)

## 범위와 결과

이 패키지는 `robot_localization` EKF 하나만 실행해 `odom -> base_link`와
`/odometry/filtered`를 발행한다. 첫 단계의 입력은 아래 두 측정값뿐이다.

| ROS topic | fuse하는 값 | 상태 배열 index | 입력 covariance | baseline variance |
| --- | --- | ---: | --- | ---: |
| `/wheel/odom` (`nav_msgs/Odometry`) | `twist.twist.linear.x` | `odom0_config[6]` | `twist.covariance[0]` | `0.0225 (m/s)^2` |
| `/imu/data` (`sensor_msgs/Imu`) | `angular_velocity.z` | `imu0_config[11]` | `angular_velocity_covariance[8]` | `0.001 (rad/s)^2` |

`x/y/yaw` pose, wheel yaw-rate, IMU orientation/yaw, linear acceleration,
ToF, map, GPS, and command velocity는 **이 단계에서 fuse하지 않는다**.
따라서 출력은 연속적인 local dead-reckoning이며, 모래 지면의 slip에 의한
장기 위치 오차를 스스로 제거하지 않는다.

```text
Control MCU encoder --RS485--> Pi bridge -- /wheel/odom (vx only) --+
                                                                  +--> EKF --> odom -> base_link
BNO085 calibrated gyro -----> BNO driver -- /imu/data (wz only) --+
```

## 실행 전 메시지 계약

### `/wheel/odom`

RS485 bridge가 만든 `nav_msgs/Odometry`여야 한다. pose는 이 EKF가 읽지
않으므로 0으로 두어도 된다. 단, 아래는 필수다.

```text
header.stamp       Pi ROS time 기준의 encoder 측정시각
header.frame_id    odom
child_frame_id     base_link
twist.twist.linear.x      MCU encoder에서 계산한 전진 속도 (m/s)
twist.covariance[0]       0.0225       # vx variance
twist.covariance[7]       큰 값 또는 0 # vy는 fuse하지 않음
twist.covariance[35]      큰 값 또는 0 # wz는 fuse하지 않음
```

`twist.covariance`는 6x6 row-major 배열이다. index `0`은 `vx`, `7`은
`vy`, `35`는 `wz`다. 이 단계에서는 `twist.covariance[0]`만 의미가 있다.
엔코더 누적 거리나 encoder 기반 pose를 함께 만든 경우에도 같은 메시지의
pose `x/y/yaw`를 true로 바꾸면 안 된다. 속도와 그 적분 pose를 한 EKF에
동시에 넣는 중복 측정이 되기 때문이다.

### `/imu/data`

`sensor_msgs/Imu`의 frame은 `imu_link`다. 이 단계에서 필요한 필드는:

```text
header.stamp                       Pi ROS time 기준 IMU 표본 시각
header.frame_id                    imu_link
angular_velocity.z                 calibrated gyro z (rad/s), CCW 양수
angular_velocity_covariance[8]     0.001       # wz variance
```

`angular_velocity_covariance`는 3x3 row-major 배열이며 index `8`은 z축이다.
orientation covariance index `8`은 yaw variance이지만, orientation 자체를
fuse하지 않으므로 현재 사용하지 않는다. 공분산이 0 또는 임의의 `1e-6`로
채워진 드라이버 출력은 그대로 신뢰하면 안 된다. 이 baseline 값은 Pi bridge
또는 BNO driver에서 명시적으로 설정한다.

## TF 계약

동적 TF publisher는 EKF 하나뿐이다.

```text
odom --(EKF, dynamic)--> base_link --(robot_state_publisher, fixed)--> imu_link
```

- `base_link`: 차체 기준, x 전방, y 좌측, z 위쪽.
- `imu_link`: 실제 BNO085 중심. 장착 위치와 회전은 URDF의 fixed joint로
  정확히 넣는다.
- `odom`: EKF가 시작할 때의 local world frame. 장기 drift와 yaw drift는
  정상이다.
- RS485 bridge, BNO driver, gateway, Nav2는 `odom -> base_link` TF를
  publish하지 않는다.

검증 명령:

```bash
ros2 run tf2_ros tf2_echo odom base_link
ros2 run tf2_ros tf2_echo base_link imu_link
ros2 topic info /wheel/odom --verbose
ros2 topic info /imu/data --verbose
ros2 topic echo --once /odometry/filtered
ros2 run robot_localization ekf_node --ros-args --params-file \
  /path/to/loonar_minimal_ekf.yaml
```

두 `tf2_echo`가 연속 출력되고 `/odometry/filtered`의 child frame이
`base_link`이면 TF 소유권이 맞다. `view_frames` 결과에 `odom -> base_link`
publisher가 둘 이상이면 실행을 중단하고 중복 publisher를 제거한다.

## BNO085 좌표계와 ENU

ROS body frame은 FLU(x forward, y left, z up), ROS world frame은 ENU(x east,
y north, z up) 규약을 쓴다. BNO085 driver가 내는 raw chip axes나 Android/NED
orientation을 가정해서는 안 된다.

초기 구성은 gyro z만 쓰지만, 다음을 bench에서 확인해야 한다.

1. 평평한 차체를 위에서 봤을 때 반시계 회전하면 `/imu/data.angular_velocity.z`
   가 양수인지 확인한다.
2. 시계 회전하면 같은 크기의 음수인지 확인한다.
3. `base_link -> imu_link` fixed rotation을 적용한 뒤에도 위 부호가 유지되는지
   확인한다. 축 remap과 TF rotation을 둘 다 적용해 이중 변환하지 않는다.
4. orientation yaw는 향후 추가 전, 정지 10분·회전·충격 시험에서 연속성과
   자계 교란 영향을 확인한다.

## Timestamp

MCU uptime를 ROS stamp로 직접 쓰면 안 된다. 두 clock epoch가 다르기
때문이다.

초기 구현은 RS485 bridge가 Pi에서 frame을 받은 순간 `rclcpp::Clock(RCL_ROS_TIME)`
으로 stamp한다. MCU의 `measurement_time_us`는 payload에 보존해 지연 진단에만
쓴다. 50 Hz 기준으로 receive-time jitter가 5 ms 이상이면 그 측정치를 bag으로
확인한다.

후속 v2에서는 Pi↔Teensy request/response time-sync를 추가한다. Pi send/receive
시간 `t1/t4`와 MCU sample time `tm`으로 `(t1+t4)/2 - tm` offset을 추정하고,
천천히 갱신한 offset으로 `tm`을 Pi ROS time으로 변환한다. MCU 32-bit microsecond
counter wrap과 ROS system-time jump는 별도로 처리한다. ROS 시간은 Pi에서 chrony로
동기화하되, 이 local EKF가 네트워크 clock sync에 의존하도록 만들지는 않는다.

## Wheel vx covariance 실측

`0.0225`는 시작값일 뿐이다. 모래/비포장 각 조건과 속도마다 최소 10회 이상의
직선 구간을 bag으로 남긴다. 시작·정지 구간을 제외하고 외부 기준 속도
`v_ref(t)`와 encoder 속도 `v_enc(t)`의 residual을 만든다.

```text
r(t) = v_enc(t) - v_ref(t)
bias = mean(r)
variance = mean((r - bias)^2)
```

외부 기준은 바닥 눈금과 영상 timing gate, overhead/AprilTag tracking, 또는
검증된 ToF local matching 중 하나여야 한다. 출발점·종점 줄자만으로는 거리
scale bias는 알 수 있어도 50 Hz `vx` variance는 알 수 없다. slip은 시간상관된
오차이므로 표본 variance를 그대로 작게 쓰지 말고, 95-percentile residual과
연속 slip 구간을 포함해 보수적으로 크게 잡거나 encoder update rate를 낮춘다.

## 다음 단계의 추가 조건

### BNO085 orientation yaw

다음 조건을 모두 충족할 때만 추가한다.

1. ENU/FLU 축과 `imu_link` TF가 bench에서 검증됨.
2. 실제 yaw variance가 측정되어, 임의의 작은 covariance가 아님.
3. 정지·충격·자계 교란 시험에서 재현 가능한 jump가 없음.
4. gyro 적분 drift보다 orientation yaw 보정 이득이 큼.

추가 시에는 yaw만 fuse하고, yaw와 gyro-z covariance를 독립 측정값으로
설정한다. BNO085 orientation이 자계 기반이면 모터 전류/철 구조물 근처에서
jump할 수 있으므로 무조건 absolute truth로 두지 않는다.

### Wheel yaw-rate

wheel differential yaw-rate는 gyro-z와 중복 state(`vyaw`)이지만 독립 센서
측정값으로는 추가할 수 있다. 다만 skid-steer와 모래에서는 좌우 wheel travel
차가 실제 회전을 잘 나타내는지, track width가 맞는지, 제자리 회전과 곡선
시험에서 먼저 측정해야 한다. IMU gyro의 온도 drift가 문제이고 wheel yaw-rate의
residual variance가 충분히 작을 때만 큰 covariance와 함께 추가한다. encoder yaw
pose는 이 최소 단계에 추가하지 않는다.

## 실행

```bash
source /opt/ros/jazzy/setup.bash
source ~/loonar_ws/install/setup.bash
ros2 launch loonar_localization loonar_minimal_ekf.launch.py
```

실행 전 `/wheel/odom`, `/imu/data`, 그리고 `base_link -> imu_link` fixed TF가
반드시 존재해야 한다.
