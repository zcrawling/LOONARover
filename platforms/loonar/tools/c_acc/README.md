# LOONAR 의도적 가속 C 시험

BNO055 내부 융합 출력 LINEAR_ACC_DATA(0x28–0x2D)를 사용한다.
MCU의 기존 통합 Control 펌웨어가 raw accel, gyro, quaternion, linear accel,
gravity를 같은 UART burst에서 읽어 기존 wire-v2 ID 1/2/5/4/6으로 전송한다.
모터 제어/엔코더/배터리/통신 경로는 변경하지 않는다.
완전한 UART EE 오류 응답에는 5 ms backoff 후 재시도한다. Timeout/불완전 응답의
200 ms drain은 유지한다. 기존 무조건 200 ms 대기로 생기던 적분 공백을 줄인다.

## 토픽

- `/imu/accel`: 중력 포함, 기존 Imu 유지.
- `/imu/data`: 자이로, 기존 Imu 유지.
- `/imu/linear_acceleration`: 중력 제거된 Vector3Stamped, 기존 유지.
- `/imu/gravity`: 중력 Vector3Stamped, 기존 유지.
- `/imu/linear`: 새 Imu. 동일 MCU burst timestamp의 자이로와 선형가속도만
  결합한다. orientation unavailable(-1), acceleration covariance unknown(0).
  단위 m/s²/rad/s, frame `imu_link`. 중력을 다시 제거하지 않는다.

실험 시 기존 V1 코드를 독립 `/c_test/v1`과 `/c_test/state`로 실행한다.
기존 EKF 및 `/localization/dr`를 수정하거나 대체하지 않는다.
`/odom_c_test`에만 C를 적용한다. TF는 기존 imu_link 변환이 있으면 검증 후
사용하고, 없으면 CAD 패키지의 명목 위치/사용자 확인 yaw +90°로 생성한다.
가속도는 base_link로 회전한다. IMU 위치는 미실측 명목값이고, 회전운동의
lever-arm 가속도 보정은 구현하지 않았으므로 이 시험은 직진 ramp용이다.

## 실행 — Pi

기존 motor_bench를 `--ros-samples`로 시작한 상태에서:

```bash
cd ~/LOONAR
# 주행 없이 실제 센서·bias·추정기·rosbag 준비 확인
bash platforms/loonar/tools/run-c-acc-test.sh --speed 0.25 --distance 1

# 사용자가 주행을 시작할 때만 --execute 추가
bash platforms/loonar/tools/run-c-acc-test.sh --speed 0.25 --distance 1 --execute
```

기본 가속/감속은 각각 2.5 s, STOP 4 s.
위 1 m 예는 0.25 m/s 목표, cruise 1.5 s다.
`--distance`는 **명령 속도 적분 기준**이며 실제 이동거리 제한이 아니다.
실제 속도는 gateway를 통해 전달하고 CSV와 `/c_test/cmd_vel`에 기록한다.
Ctrl+C는 gateway STOP을 보내고 bag/노드를 정리한다.
실행 중 gateway/cFS/MCU는 종료하지 않는다.
기본 gatewayctl은 `/opt/loonar/current/bin/vehicle_gatewayctl`이며
`--gatewayctl`로 경로를 바꿀 수 있다.

`--dry-run`은 ROS 노드나 bag도 만들지 않고 profile만 출력한다.
실행 환경: ROS Jazzy, scipy/numpy/message_filters/sensor_msgs_py/tf2_ros 및
rosbag2 sqlite3 storage. MCU ROS bridge는 새 소스를 사용해 재시작해야 한다.

## 결과

`~/odom_tests/loonar_c_<timestamp>/` 아래:

- `bag/`: IMU 원본/선형가속도, MCU raw, motor, encoder, 기존 odom,
  test V1, C odom, phase, TF, diagnostics.
- `estimate/samples.csv`: C_acc/C_dec/C_valid, v_imu, encoder/corrected vx,
  accel bias, corrected acceleration, timestamps, test pose.
- `estimate/windows.jsonl`: 가속·감속 회귀에 쓴 원본 window와 clamp하지 않은 C.
- `commands.csv`: 실제 명령 전송 시각, phase와 선속도.
- `trial.json`: profile, TF, 상태, 마지막 추정 결과.

가속 구간만 v_imu를 적분하고 LS C를 추정한다. cruise는 C를 고정한다.
감속 C는 최종 정지 확인 뒤 역적분하여 독립 평가한다. 범위 밖 C나 품질
실패 시 test odom은 encoder vx로 fallback한다. 등속 구간 C 재추정 없음.
`--imu-time-offset`으로 기존 추정기의 IMU 정합 offset을 지정할 수 있다.
기본 0은 필터의 실제 지연이 검증됐다는 뜻이 아니다. MCU 시각은 UART
수신 시각이며 BNO 내부 필터 지연은 별도 가감속 로그로 평가해야 한다.

AprilTag는 입력에 사용하지 않는다. Pi에서 직접 실행하면 외부 카메라 추적을
시작하지 않는다. 기존 GT와 비교하려면 노트북 카메라 기록과 시계를
정렬하고 동일 window의 C_GT를 사후 계산해야 한다.

## 노트북에서 AprilTag와 함께 실행

노트북의 같은 shell 진입점은 자동으로 SSH/카메라 실행기로 분기한다.

```bash
cd ~/LOONAR
bash platforms/loonar/tools/run-c-acc-test.sh \
  --ip 10.254.254.3 --speed 0.25 --distance 1 --tag-size 0.12 --execute
```

노트북에서는 Jazzy가 필요하지 않다. `.venv-apriltag`로 C920를 추적하고,
Pi에서 기존 시험기를 실행한 뒤 bag/CSV를 복사해 `.venv-icp`로 비교한다.
SSH 사용자 loonar, 암호 파일 `~/.config/loonar/loonar-ssh-password`(0600).
기존 wego 암호 파일을 변경하지 않는다. `--ip`로 주소 변경 가능.
`--camera`, `--calibration`, `--forward-axis`, `--focus`, `--no-preview`도 지원한다.
태그 누락 구간은 GT 평가에서 제외하며 태그는 estimator 입력이 아니다.
카메라 프로그램 종료나 Ctrl+C는 원격 stdin으로 취소 요청을 보내 정리한다.
결과: `data/apriltag_gt/loonar_c_vision_<timestamp>/report.html`.
`--execute`가 없거나 `--dry-run`이면 노트북에서는 계획만 출력한다.
Pi에서 직접 실행할 때에는 앞 절처럼 `--tag-size`를 넣지 않는다.
