# 기준 odometry / localization architecture

기준일: 2026-09-11. 이 문서는 프로젝트의 odometry/localization 설계 기준이다.
시스템 전체 책임은 [project.md](../project.md)를 따른다.
**설계 기준 확정과 실제 구현·배포 완료를 구분한다.** 현재 상태는 아래 구현 표에 기록한다.

## 목표와 플랫폼 경계

목표는 slip ratio의 완전한 복원이 아니라 wheel slip, lateral slip, contact loss,
obstacle stuck에 따른 encoder 오차를 감지하고 신뢰도를 관리하며, 독립적인 환경
관측이 확보되면 누적 body pose 오차를 보정하는 것이다.

현재 시험 차량은 **LIMO 4WD differential/skid-steer**다. 최종 LOONAR의 좌우 구동륜과
후방 rod/tail 접촉 구조를 LIMO와 같다고 가정하지 않는다.

- 공통 estimator: 시간 정합, V1 적분, stationary 판정, bias 업데이트,
  confidence/constraint gating, registration quality gate, map correction.
- 플랫폼 adapter/config: encoder 단위·부호·wheel mapping·기구 scale, IMU frame과
  가속도 정의, 센서 지연, extrinsic, ToF driver, footprint/contact 구조, 실제 속도 설정.
- 공통 구현 위치는 `common/ros2/`, 플랫폼 launch/config는 `platforms/<platform>/ros2/`.
  기존 V1/V2 분석 코드를 검증 기준으로 재사용하고 별도 운동학을 중복 구현하지 않는다.

**관측 한계:** encoder/IMU만으로 등속 common-mode slip, 일정 속도 외부 이동, 모든
접촉 상실을 식별할 수 없다. confidence 저하나 ZUPT만으로 누적 위치 오차가 없어지지
않는다. ToF도 관측 불가능하거나 계속 실패하면 위치 오차를 유한하게 제한한다고
보장할 수 없다. 실패/불확실성을 드러내며 성공한 독립 보정으로 복구하는 구조다.

## 데이터 흐름

```text
Motion Primitive Manager (command is prior)
    STOP / STRAIGHT_SLOW / STRAIGHT_NORMAL / ROTATE_LEFT / ROTATE_RIGHT
                       ↓
Platform encoder + IMU adapter → continuous V1 DR → odom → base_link
                       ↓                  ↑
              Slip / Contact Monitor → confidence / constraint gating
                       ↓
               stationary confirmed
                       ├→ ZUPT / zero angular-rate / gyro bias update
                       └→ STOP keyframe A–B registration → quality gate
                                                         ↓ accepted
                                                     map → odom
```

상태 감시를 위해 Gateway에 새로운 authority/watchdog를 추가하지 않는다. estimator는
독자적인 `/cmd_vel`을 발행하지 않는다. primitive 실행은 기존 AUTO → Gateway 경로를
사용하고, 운용 STOP과 stationary-confirmed는 별도 상태로 기록한다.

## Motion primitive와 제약

초기 경로는 `ROTATE → STOP → STRAIGHT → STOP`으로 분해한다. 곡선 primitive는
도입하지 않는다. 속도·회전시간은 플랫폼 설정과 실행 요청에서 제공하고 공통 core에
임의로 고정하지 않는다. manual/기존 로그의 곡선 운동은 억지로 STRAIGHT/ROTATE로
분류하지 않고 prior 불명으로 처리한다. 명령의 기대 상태와 관측 상태는 별도 기록한다.

| Primitive | 추정 시 적용 |
| --- | --- |
| STOP | stationary detector의 prior. 명령만으로 ZUPT하지 않음 |
| STRAIGHT_SLOW / NORMAL | yaw는 gyro. `vy_body ≈ 0`는 soft NHC 후보. yaw rate를 0으로 강제하지 않음 |
| ROTATE_LEFT / RIGHT | yaw는 gyro. encoder translation 신뢰도를 낮추되 vx/vy를 0으로 강제하지 않음 |

SUSPECT/DEGRADED/contact 의심 시 NHC를 약화하거나 제거한다. 향후 lateral velocity
상태를 가진 estimator에서도 회전 중 발생하는 병진 slip을 허용한다.
현재 V1은 `vy`를 관측·추정하지 않는다. 모델에 `vy`가 없다는 사실을 soft NHC 구현 완료나
실제 횡방향 속도 0의 근거로 취급하지 않는다. 횡방향 불확실성을 유지하고 ToF로 보정한다.

## Continuous DR: V1 유지

```text
vx = vx_encoder
wz = wz_imu - gyro_bias
x_dot = vx * cos(yaw)
y_dot = vx * sin(yaw)
yaw_dot = wz
yaw_residual = wz_encoder - wz
```

encoder-only pose, encoder wz, gyro raw/corrected wz, yaw residual을 baseline/debug용으로
유지한다. frame·단위·header timestamp와 검증된 signal delay를 정규화한다.
누락 구간을 무조건 보간·적분하지 않으며, 초기 구현에서 longitudinal C를 적용하지 않는다.

confidence 저하는 covariance 증가, 즉 정보량 감소를 뜻한다. 신뢰도가 낮다는 이유로
속도를 0으로 만들거나 일정 배율을 곱하지 않는다. 향후 wheel measurement를 reject할
때에도 대체 예측 모델과 불확실성을 명시하고 정지 상태를 만들어내지 않는다.
현재의 결정론적 V1에 confidence를 붙이는 것만으로 nominal 위치 적분오차는 줄지 않는다.

## Stationary / ZUPT / bias

stationary detector는 동기화된 연속 window에서 다음을 검사한다. threshold, window,
진입/이탈 조건, 누락·데이터 최신성 기준은 parameter로 두고 실측으로 결정한다.

- wheel 속도와 변동. 가능하면 개별 wheel도 확인
- gyro 전체 축 평균·변동, 기존 bias의 유효성
- acceleration 변동, shock, 사용 가능한 attitude 변화
- command prior와의 일관성, 센서 누락 및 멈춘 timestamp 여부

gravity-bearing acceleration의 크기를 0과 비교하지 않는다. 없는 roll/pitch/current를
0으로 채우지 않는다. 센서 정지로 값이 일정한 상태를 실제 정지의 증거로 사용하지 않는다.
일정 속도 미끄러짐처럼 이 센서만으로 구별할 수 없는 상태가 있어 정지 판정에도 한계가 있다.

확인된 정지 window에서 velocity zero update, zero angular-rate update, gyro bias
업데이트를 수행한다. bias 출처, sample 수, variance, 적용 시각을 기록한다. 실제 회전을
bias로 흡수하지 않는다. bias 업데이트는 이후 추정에 적용하며 과거 odom pose를 바꾸지
않는다. ZUPT는 velocity/bias 안정화이고, 누적 위치를 원점이나 이전 정지점으로 돌리지 않는다.

## Slip / Contact Monitor

상태와 근거를 분리하여 wheel confidence, measurement covariance scale, constraint
validity, residual/score와 관측 가능 여부를 출력한다.

- 상태: `VALID`, `SUSPECT`, `DEGRADED`, `CONTACT_LOSS_SUSPECT`, `STUCK_SUSPECT`
- wheel 속도/가속도, wheel-vs-gyro yaw residual
- 중력 보정이 유효한 경우 longitudinal acceleration inconsistency
- 개별 wheel 차이, roll/pitch/vertical shock, 향후 motor current
- ToF body motion과 wheel motion 불일치

단일 residual로 contact loss/stuck을 확정하지 않는다. state에 reason, 사용 신호,
유효 window와 전이 시각을 붙이고 여러 의심 상태의 근거를 동시에 보존한다.
ToF의 낮은 quality나 degeneracy를 body가 움직이지 않았다는 증거로 삼지 않는다.

V2의 현재 로그는 gravity-bearing acceleration과 yaw-only orientation이다. 초기 정지
ax 차분은 fixed-tilt proxy이며 dynamic gravity compensation이 검증되지 않았다.
이를 유효한 body acceleration이나 확정적인 접촉 판정 근거로 연결하지 않는다.
`C_accel`은 diagnostic 전용이고 excitation 부족은 `UNOBSERVABLE`이다.
score가 낮더라도 등속 common-mode slip을 배제할 수 없다.

## STOP-to-STOP ToF correction

1. stationary 확인 후 시각과 extrinsic이 명확한 bounded keyframe A를 획득한다.
2. DR 기반 STRAIGHT/ROTATE 후 stationary를 확인하고 keyframe B를 획득한다.
3. A–B registration을 수행하고 body frame 상대 자세로 변환한다.
4. convergence, residual/fitness, correspondence 수, inlier ratio, overlap,
   degeneracy/방향별 observability와 해의 안정성을 quality gate에서 검사한다.
5. 관측 가능한 보정만 사용한다. 초기에는 필요한 자유도가 부족하면 전체 보정을 reject한다.
   reject 시 DR을 유지하고 uncertainty를 증가시킨다. 가짜 zero motion을 만들지 않는다.

DR을 초기값으로 사용할 수 있지만 wheel과 일치한다는 사실만으로 결과를 수락하지 않는다.
초기값 의존성·국소해와 환경 관측의 정보를 구분한다. 평면은 면내 병진/yaw를 충분히
구속하지 못할 수 있어 낮은 residual만으로 수락하지 않는다. threshold는 실측 전 최종
확정하지 않는다.

점군은 제한된 keyframe/후보만 유지한다. 실패한 B를 신뢰된 새 anchor로 조용히 바꾸지
않는다. 마지막 수락 anchor와 pending frame을 구분한다. overlap을 잃으면 localization
저하 상태와 명시적 재초기화를 다룬다. 순차 registration에도 drift가 있으므로 local
keyframe correction을 global SLAM/절대 위치 기준과 동일하게 취급하지 않는다.

## TF와 보정 계약

`T_X_Y`는 Y 좌표를 X 좌표로 변환하는 행렬로 정의한다.

- `odom → base_link`: continuous DR 전용. ICP가 제어용 odom pose를 jump시키지 않음
- `map → odom`: 수락된 외부 pose correction 전용
- 각 TF edge는 publisher 하나만 소유. 기존 EKF와 새 DR의 중복 발행 금지

body 상대 registration이 `T_A_B`이면 수락 anchor의 `T_map_A`에서
`T_map_B = T_map_A * T_A_B`를 계산한다. B 획득 시각 `t_B`의 DR을 사용해
`T_map_odom = T_map_B * inverse(T_odom_B(t_B))`로 보정한다.
처리 완료 시각의 DR을 섞지 않는다. timestamped 이력, anchor ID, 수락 상태를 관리한다.
map pose는 보정에 따라 달라질 수 있고 control은 continuous odom을 사용한다.

## ROS2 module 계약과 구현 순서

아래는 구현할 책임 분할이며 현재 존재하는 package/topic 이름을 선언하는 표가 아니다.
각 module은 독립 enable/disable과 진단 출력을 제공하고 비활성 상태를 명시한다.

| 순서 / module | 입력 → 출력 | 비활성 시 |
| --- | --- | --- |
| 1 Primitive manager | 경로/실행 요청 → primitive prior / 기존 AUTO 요청 | prior 불명, 실행 없음 |
| 2 Stationary detector | encoder/gyro/accel/prior → 정지 근거 | ZUPT/bias 갱신 금지 |
| 3 Zero update | confirmed 정지 window → velocity update / bias | 기존 V1 bias 방침 |
| 4 Monitor | 동기 신호·유효성 → confidence/state/reasons | confidence 불명 |
| 5 Constraint gate | primitive/confidence → soft constraint weight | 추가 제약 없음 |
| 6 Stop registration | confirmed 정지/ToF/anchor → relative pose/quality | 외부 보정 없음 |
| 7 Map correction | accepted pose + 같은 시각 DR 이력 → map→odom | DR 지속, 외부 보정 무효 |
| 8 2.5D integration | local terrain + localization validity → local navigation | perception 단독 사용 |

진단에는 source timestamp, frame, validity, parameter profile, bias, uncertainty,
primitive와 observed state, gate 채택 여부와 이유를 포함한다. quality를 pose 값에 숨기지 않는다.

## 현재 구현과 이행·검증

| 기존 코드 | 현재 상태 / 유지·확장 방침 |
| --- | --- |
| `platforms/limo/ros2/loonar_limo_encoder_odom/` | platform wheel adapter/encoder baseline으로 유지 |
| `platforms/limo/ros2/loonar_limo_localization/` | wheel vx + gyro wz EKF, 현재 단독 odom TF owner. 미교체 |
| `tools/odom_v1/` | offline bias 보정·V1 적분·yaw residual. 공통 core의 회귀검증 기준 |
| `tools/odom_v2/` | 조건부 acceleration 진단. C를 estimator에 연결하지 않음 |
| `platforms/limo/tools/icp_rosbag.py` / `loonar_limo_rgbd_odom/` | 독립 실험. STOP keyframe quality gate 구현 완료로 취급하지 않음 |
| `common/ros2/loonar_localization/` | primitive sequence, stationary/ZUPT/bias, V1 core, monitor, constraint gating, STOP ICP, map correction 및 ROS2 wrapper 구현 |
| NHC / individual wheel | soft weight 출력만 구현, lateral velocity 상태 업데이트는 미구현. LIMO 좌/우 누적 odometer adapter 구현. 4개 바퀴의 독립 측정으로 취급하지 않음 |
| 2.5D / 운용 적용 | navigation 연결·Gateway intent 실행 bridge·실차 배포는 미실시. shadow 기본값으로 기존 EKF 유지 |

구현은 1–8 순서로 진행한다. 기존 bag으로 재현하는 공통 core와 offline 회귀 검증을
먼저 정리한 뒤 ROS2 wrapper를 추가한다. V1 동일 입력 비교, 실제 회전의 정지 오판 방지,
누락/오래된 sample, bias 변경 시 pose 연속성, 횡방향 관측 불가 상태, ToF 평면
퇴화/reject, 지연된 보정과 TF 단독 소유를 검증한다. 새 데이터 수집·로버 구동은 별도
명시적으로 승인된 범위에서 수행한다.

2.5D perception은 gravity-aligned rolling local terrain grid를 기본으로 하며 full 3D
SLAM이나 ToF odometry 성공을 전제하지 않는다. 자세·국소 지형 관측과 장거리 localization을 분리한다.

구현 사용법과 검증 범위는 [공통 패키지 README](../common/ros2/loonar_localization/README.md)를 따른다.
