# vehicle_gatewayd Implementation Status

## 구현 완료

### G1 — 공통 core와 codec

- 5모드: `STOP`, `MANUAL`, `AUTO`, `PAYLOAD`, `REACTION`
- 명령: hello, motion, stop, mode select, backend status
- 공통 `VehicleStatus` field-wise codec
- non-finite motion 프레임 거부
- mode/명령 선택 단위 테스트

### G2 — Unix socket daemon

- `cfs.sock`, `ros.sock`, `backend.sock`의 `SOCK_SEQPACKET` endpoint
- cFS status fan-out과 backend motion 전달
- 명령 수신 로그와 1초 상태 로그
- daemon 통합 테스트

### G3 — LIMO backend

- 공통 motion을 `geometry_msgs/Twist` `/cmd_vel`로 그대로 변환
- `/limo_status`의 battery voltage 변환
- `/wheel/odom`의 pose/yaw/twist 변환
- `/imu` quaternion의 roll/pitch/yaw 변환
- 유효한 필드만 표시하는 `VehicleStatus`를 1 Hz로 전송

### G4 — cFS/Ground 연동

- GroundLink TCP codec 및 mock
- cFS GroundLink 앱과 VehicleAdapter 앱
- 다섯 지상 명령의 Software Bus route
- GatewayStatus와 VehicleStatus의 지상 telemetry route
- PAYLOAD/REACTION 전환 전 명시적 STOP
- REACTION `NOT_IMPLEMENTED` 결과

## 다음 최소 구현 단위

1. LIMO NUC에서 ROS 2 package를 `colcon build`한다.
2. 정지 상태에서 `/limo_status`, `/wheel/odom`, `/imu`가 Ground mock의
   `VehicleStatus`까지 전달되는지 확인한다.
3. MANUAL/AUTO/STOP 실제 주행 회귀 시험을 수행한다.
4. ROS 2 주행 로직을 단위 node부터 추가한다.
5. 최종 LOONAR 포팅 때 serial backend와 MCU telemetry producer를 구현한다.
6. payload MCU 시퀀스와 reaction wheel actuator/복구 로직을 구현한다.

## 의도적으로 제외

- authority, epoch, TTL, command lease
- Gateway 속도 제한과 clamp
- backend health 기반 command gate
- 연결 종료를 명령으로 해석하는 자동 정지
- Gateway 내부 payload/reaction 하드웨어 로직

최종 장치 보호와 MCU 자체 동작은 실제 하드웨어 요구사항 검수 후 별도 구현한다.
