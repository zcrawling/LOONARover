# LOONAR Documentation

`project.md` is the architecture source of truth. The documents in this directory
describe the new common system; platform-specific facts are kept beside their
platform to prevent LIMO and final-rover assumptions from mixing.

| Document | Scope |
| --- | --- |
| `architecture.md` | responsibility split and single motion path |
| `platform_matrix.md` | LIMO and final-LOONAR boundary |
| `migration_status.md` | retained assets and intentionally removed old paths |
| `vehicle_gatewayd_architecture.md` | Gateway ownership, runtime and backend boundary |
| `vehicle_gatewayd_if.md` | cFS/ROS/Gateway motion and telemetry contracts |
| `vehicle_gatewayd_implementation_plan.md` | reviewable implementation slices and code units |

Platform documents:

- `platforms/limo/README.md`
- `platforms/loonar/README.md`
- `common/interfaces/time_identity.md`
