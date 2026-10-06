# LOONAR CAD 기반 TF

원본: `platforms/loonar/261004rover.step` (2026-10-04 조립 상태).
STEP의 820개 occurrence 프레임과 실사용 프레임을 구분한다.

## 실행

Pi에서 저장소를 복사한 뒤:

```bash
source /opt/ros/jazzy/setup.bash
cd ~/LOONAR
colcon build --base-paths platforms/loonar/ros2/loonar_description \
  --build-base build/description --install-base install/description
source install/description/setup.bash
ros2 launch loonar_description description.launch.py
```

`robot_state_publisher`, `xacro`, `launch_ros`가 필요하다. 이 실행은 TF만
발행하며 모터 명령, EKF 시작, joint_states 모의 발행은 하지 않는다.
기존 terrain launch에서는 `publish_tf:=false`를 유지해 TF 중복을 피한다.

## 좌표와 신뢰 수준

- `base_link`: 좌우 바퀴 보어 축 중앙(CAD `[0,0,57]` mm).
  ROS X=CAD +Y(전방), ROS Y=CAD -X(왼쪽), ROS Z=CAD +Z.
  CAD 꼬리는 -Y 쪽에 있다. `odom -> base_link`는 기존 estimator 소유다.
- `*_cad`: STEP 부품 원점. 센서 측정 원점이나 관절축이라고 간주하지 않는다.
  반응휠·꼬리는 조립체 장착 프레임까지만 정의한다. STEP에는 작동 관절 제한과
  실제 관절 상태가 없으므로 내부 작동 관절을 만들어 내지 않는다.
- `left/right_wheel_spindle`: CAD 바퀴 원점, base 기준 y=±0.1285 m.
  바퀴 보어의 CAD 원점/축을 사용한다. 타이어 접촉 중심 간격이 아니므로
  **0.257 m를 wheel separation 보정값으로 복사하지 않는다.**
- `left/right_wheel_link`: continuous joint, +Y 회전축. 실제 `/joint_states`의
  `left_wheel_joint`, `right_wheel_joint`가 있어야 회전 TF가 나온다.
- `imu_link`: 사용자가 확인한 BNO055 실제 방향. x=좌측, y=후방, z=상방,
  따라서 base 기준 yaw=+π/2. CAD의 `4754 v1` 위치는 사용하지 않는다.
  위치 기본값 `[0.03575,0,-0.057]` m는 ToF 아래 중앙/바닥 기준 **명목값**이다.
  CAD 바닥 datum z=0에 놓았으며 바닥 두께, PCB 높이, 실제 칩 중심 높이는
  미측정이다. `imu_xyz` 인자로 덮어쓴다. 축 방향 확정과 위치 실측을 혼동하지 않는다.
- `tof_link`: `[0.03575,0.00005,-0.0075]` m, 전방 수평 가정.
  CAD MS22MF005-B 부품 원점에서 가져온 장착 기준이며, SDK의 거리 원점과
  광학 중심이 일치한다는 검증은 아직 없다. `tof_xyz`, `tof_rpy`로 보정한다.
- `tof_assembly_cad`: I200DK 전체 모델 원점. 센서 중심과 큰 차이가 있다.
- `camera_assembly_cad`: Camera Module 3 모델 원점. 광학 중심 아님.

광학 TF는 기본으로 발행하지 않는다. 실제 광학 원점/축 변환을 확인하면:
`publish_optical_frames:=true`, `tof_optical_offset`,
`camera_optical_xyz`, `camera_optical_rpy`를 지정한다.
카메라 인자는 camera_assembly_cad 기준, ToF offset은 tof_link 기준이다.
ToF optical 축은 x=오른쪽, y=아래, z=전방이다.
센서 driver의 frame_id와 이 축 계약도 확인해야 한다.

`map`, `odom`, `base_footprint`를 정적 CAD 프레임으로 생성하지 않는다.
경사에서의 지면 투영, 실제 회전, 외부 위치 보정은 별도 동적 입력이다.

## CAD 전체 프레임과 재생성

`../../hardware/tf/cad_frames.json`: STEP entity ID, 계층, 변환행렬, 원본 SHA256.
`../../hardware/tf/cad_snapshot.urdf`: 전체 820개 occurrence를 고정한 **CAD 검토용**
스냅샷. 움직이는 부품도 CAD 자세에 고정되므로 실주행 TF 대용이 아니다.
FreeCAD 독립 import 결과는 같은 폴더의 `freecad_geometry.json`이다.

저장소 루트에서:

```bash
.venv-icp/bin/python platforms/loonar/tools/cad/extract_step_frames.py \
  platforms/loonar/261004rover.step --output platforms/loonar/hardware/tf
.venv-icp/bin/python platforms/loonar/tools/cad/build_description.py
.venv-icp/bin/python platforms/loonar/ros2/loonar_description/test/test_frames.py
```

추출 도구는 numpy/scipy, 검증은 추가로 xacro를 사용한다.
CAD가 바뀌면 entity ID와 물리적 축 선택을 다시 검증해야 한다.
현재 기존 EKF, 엔코더 기구학, 펌웨어, 실기 TF 설정은 변경하지 않았다.
