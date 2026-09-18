# LOONAR Documentation

`project.md` is the architecture source of truth. The documents in this directory
describe the new common system; platform-specific facts are kept beside their
platform to prevent LIMO and final-rover assumptions from mixing.

| Document | Scope |
| --- | --- |
| `architecture.md` | responsibility split and single motion path |
| [`odometry-localization.md`](odometry-localization.md) | 기준 V1 DR, slip/contact monitor, stationary/ZUPT, STOP ToF correction |
| `platform_matrix.md` | LIMO and final-LOONAR boundary |
| `migration_status.md` | retained assets and intentionally removed old paths |
| `vehicle_gatewayd_architecture.md` | Gateway ownership, runtime and backend boundary |
| `vehicle_gatewayd_if.md` | cFS/ROS/Gateway motion and telemetry contracts |
| `vehicle_gatewayd_implementation_plan.md` | reviewable implementation slices and code units |
| [`main-master-merge-20260918.md`](main-master-merge-20260918.md) | main/master 이력 병합, 로컬 작업물과 payload 구현 상태, 검증 기록 |

Platform documents:

- [LIMO → LOONAR Pi 5 / Ubuntu 24.04 포팅 계획·검증 절차](../platforms/loonar/porting/limo_to_loonar_plan.md)
- `platforms/limo/README.md`
- `platforms/loonar/README.md`
- `common/interfaces/time_identity.md`
