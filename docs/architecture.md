# 현재 명령 경로

```text
GCS 웹/Xbox → GCS/.runtime/backend.sock → real_app → TCP 7443
  → cFS GroundLink → VehicleAdapter → gateway/cfs.sock
  → vehicle_gatewayd → gateway/backend.sock → mcu_v2.backend
  → USB CDC, LNR2 → Control Teensy → Serial2 → RoboClaw

ROS AUTO → gateway/ros.sock → vehicle_gatewayd
Control BNO055·모터 표본 → Pi backend → ROS / cFS → GCS
Pi 카메라 → H.264/MPEG-TS UDP 5600 → GCS 영상 수신기
```

GCS 로컬 `backend.sock`과 Pi Gateway의 `backend.sock`은 별개다.
Pi 직렬 포트는 `mcu_v2.backend`가 소유하며 ROS 브리지는 전달받은 표본을 사용한다.
LIMO에서는 별도 ROS backend를 사용한다.

## 주행

Gateway는 STOP/MANUAL/AUTO/PAYLOAD/REACTION을 선택한다.
MANUAL은 cFS 입력, AUTO는 ROS 입력이다. PAYLOAD/REACTION 진입 전 정지한다.
Gateway 자체가 주기적으로 마지막 명령의 유효기간을 갱신하지 않는다.
Control MCU는 Pi의 마지막 새 주행 명령에서 200ms가 지나면 목표를 0으로 만든다.
IMU 초기화 실패는 주행을 차단하지 않는다. 실제 정지 조건은
[Control 펌웨어](../platforms/loonar/firmware/control/README.md)를 참고한다.

속도 정규화는 GCS 실제 backend와 Pi backend에서 한다. 바퀴 상한 0.4m/s,
윤거 0.21m 기준 제자리 회전 상한은 약 3.8rad/s다.
IMU 수신과 방향 표시가 구현되어 있지만 IMU 직진 피드백 제어를 의미하지는 않는다.
ROS 위치추정·AUTO는 별도 실행 구성이 필요하다.

## Payload

`PAYLOAD_START/STOP` → GCS 웹 서버 → 실제 backend → GroundLink type 0x0004
→ cFS VehicleAdapter(정지·PAYLOAD 선택) → PayloadAdapter
→ `/run/loonar/payload-pca.sock` → `payload_pca_service.py`
→ 별도 Payload Teensy의 USB ASCII `START/STOP`.

결과는 EVENT(type 0x8006)로 돌아온다. cFS 명령 수락은 MCU 측정 완료와 다르다.
STOP은 측정 시작 후 최소 5초가 지난 뒤 PCA 행과 완료 응답을 반환한다.
[운용 절차](../platforms/loonar/porting/payload_pca_runbook.md).
REACTION의 실제 액추에이터 제어는 미구현이다.

## 실행 구성

`start-ground-support.sh`는 checkout의 gateway·cFS·Control backend를 시작한다.
영상·ROS 기록은 선택 사항이며 Payload 서비스는 별도로 시작해야 한다.
`/opt/loonar/current` 기반 systemd 설치와 checkout 실행을 혼용해 같은 포트·장치를
중복으로 열지 않는다. [실행 안내](../platforms/loonar/porting/ground_control_runbook.md).
