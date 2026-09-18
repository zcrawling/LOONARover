# LIMO offline odometry V1

Existing LIMO 4WD skid-steer logs only. No ROS installation, network connection,
commands to the rover, EKF changes, or new recordings required.

From `/home/sb/LOONAR`:

```bash
.venv-icp/bin/python tools/odom_v1/analyze.py --residual-threshold 0.05 --residual-window 0.25
.venv-icp/bin/python tools/odom_v1/report.py
.venv-icp/bin/python -m unittest discover -s tools/odom_v1 -p 'test_*.py'
```

Dependencies: numpy, scipy, matplotlib, rosbags (available in `.venv-icp`).
Default report: `data/imu_vibration/odom_v1_analysis/report.html`.
Both commands accept `--output DIRECTORY`.

Baseline integrates original encoder vx and wz. V1 uses identical vx and
static-bias-corrected gyro wz transformed to base_link. Both use header-time
alignment and identical integration. Recorded wheel pose is also preserved.
Missing sensor intervals are not bridged. `series/*.csv` contains aligned rates,
residual, normalized score, suspect flag, and both poses. No longitudinal scale.

Static bias: zero-command/wheel-stop intervals trimmed at each end; use pre-motion
static preferentially. If absent, a measured reference within one hour is used,
with explicit provenance. No assumed zero-bias fallback. Stationary-by-command
is a proxy; external disturbances cannot be excluded from these signals alone.

`--gyro-delay SECONDS` subtracts a **known** IMU measurement delay from its header.
Default 0: interpolate by recorded header time, do not invent a physical latency.
Wheel/gyro cross-correlation is diagnostic only because wheel yaw is unreliable.
Header phase is not a measurement of hardware latency.

Suspect threshold is a diagnostic parameter, not proof of slip. Effective track,
wheel scales and other errors can also cause residual. Score floor defaults to
0.01 rad/s; it is not a calibrated probability. V1 always uses gyro yaw, not a switch.

GT is evaluation-only. Approximate +/-28 degree manual trials support the yaw
comparison but cannot certify degree-level accuracy. AprilTag saved progress can
only evaluate longitudinal projection under axis alignment assumptions; saved
unsigned 3D heading change is not signed planar yaw. No GT fitting is performed.
The explicitly excluded uphill trial remains excluded. Log exports of the same
source bag are not added as additional trials.
