# Repository layout

| Directory | Contents |
| --- | --- |
| `common/` | Platform-independent protocols, Gateway, video and shared ROS packages |
| `platforms/limo/` | LIMO drivers/adapters, launch/config, remote motion recorder and services |
| `platforms/loonar/` | Final-rover firmware, hardware and platform configuration |
| `cfs/` | cFS applications and mission integration |
| `GCS/` | Ground-station project material |
| `config/cameras/` | Measured camera calibration files |
| `tools/apriltag_gt/` | Stable CLI entry points, implementation package and offline tests |
| `tools/analysis/20260909/` | Source for the dated exploratory dataset analysis |
| `data/` | Recorded observations and generated analysis outputs |
| `docs/` | Architecture and operating documentation |

Keep source code out of recording directories. Put reusable code in the owning
tool or ROS package, and dated experiments under `tools/analysis/`. Keep tests
with their owning module under `tests/`. Calibration JSON is measured input,
not disposable output.

Build/install/log directories, virtual environments, node_modules and temporary
files are local generated assets, excluded from Git. Raw AprilTag recordings
are also local: ignoring them is not a backup policy. No recordings were deleted
in this reorganization. Existing `data/limo/` tracked fixtures are retained.

The distance-test interface remains:

```bash
bash tools/apriltag_gt/run_distance_test.sh --speed 0.05 --distance 1
```

Run its local tests without driving hardware:

```bash
bash tools/apriltag_gt/test.sh
```
