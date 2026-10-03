# cFS 통합

NASA cFS 자체는 외부에서 가져오며 이 디렉터리는 LOONAR 앱과 mission 설정을 제공한다.

| 앱 | 설치 모듈 | 역할 |
| --- | --- | --- |
| GroundLink | `lnr_ground.so` | TCP 7443 명령·텔레메트리 |
| VehicleAdapter | `lnr_vehicle.so` | Software Bus ↔ Gateway |
| McuBridge | `lnr_mcu.so` | MCU health 전달 |
| PayloadAdapter | `lnr_payload.so` | Payload PCA 서비스 명령·이벤트 |

앱 목록과 로딩 순서는 [startup fragment](mission/cfe_es_startup.scr.fragment),
빌드 목록은 [targets fragment](mission/targets.cmake.fragment),
MID는 [loonar_cfs_messages.h](apps/common/loonar_cfs_messages.h)에 있다.

## 빌드·실행

저장소 루트에서:

```bash
bash tools/run_gcs_test.sh --build-only --skip-tests --jobs 2
```

산출물은 `build/gcs-test/cFS/build-native_std/exe/cpu1`이다.
Pi에서는 [ground-support](../platforms/loonar/porting/ground_control_runbook.md)가
Gateway와 cFS를 함께 실행한다. 장치 없는 실행은 [PC 통합 시험](../tools/gcs_test/README.md)을 따른다.

`LOONAR_GATEWAY_SOCKET`은 Gateway의 `cfs.sock` 위치다. 시스템 기본값은
`/run/loonar/vehicle-gateway/cfs.sock`이며 bench는 runtime 경로를 지정한다.

## Payload

VehicleAdapter가 정지·PAYLOAD 모드를 선택한 뒤 PayloadAdapter가
`/run/loonar/payload-pca.sock`으로 명령을 보낸다. 별도
[Payload 서비스](../platforms/loonar/porting/payload_pca_runbook.md)가 필요하다.
센서 전원은 켠 채 측정을 시작·종료한다. REACTION 액추에이터는 `NOT_IMPLEMENTED`다.

[GroundLink 계약](../docs/ground_link_protocol.md), [Gateway 계약](../docs/vehicle_gatewayd_if.md).
