# vehicle_gatewayd Architecture

## 목적

`vehicle_gatewayd`는 ROS 2, cFS와 실제 차량 구현 사이의 단일 공통
interface다. 차량 명령은 `linear`, `angular`로 통일하고 platform 차이는
backend에만 둔다.

```text
cFS STOP/MANUAL/mode ---> cfs.sock --+
                                     +--> Gateway core --> backend.sock
ROS AUTO v,w -----------> ros.sock --+                       |
                                                             +--> LIMO ROS `/cmd_vel`
                                                             +--> LOONAR serial (TBD)
```

## 모드 처리

- `STOP`: 0 명령을 backend에 전달한다.
- `MANUAL`: cFS가 보낸 속도를 그대로 전달한다.
- `AUTO`: ROS가 보낸 속도를 그대로 전달한다.
- `PAYLOAD`, `REACTION`: 먼저 0을 전달하고 모드를 유지한다. ROS 속도는 무시한다.
- ROS AUTO가 MANUAL/STOP/PAYLOAD/REACTION을 해제할 수 없다.

이는 authority/lease/TTL 체계가 아니다. 명시적 명령 선택이며 Gateway는 속도
상한이나 장치 상태 기반 거부를 하지 않는다.

## 상태 처리

backend는 선택적으로 `VehicleStatus`를 Gateway에 보낸다. Gateway는 유효
비트를 포함한 값을 변경하지 않고 cFS peer에 전달한다. LIMO backend는
`/limo_status`, `/wheel/odom`, `/imu`를 사용하며 최종 LOONAR backend는 MCU
telemetry를 추가 매핑한다.

## 로그

- 명령 수신 때 source와 command를 즉시 출력한다.
- 현재 모드와 선택된 속도를 1초마다 출력한다.

정상 동작을 숨기는 자동 전환, disconnect stop, watchdog은 구현하지 않는다.
