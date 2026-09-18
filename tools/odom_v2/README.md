# LIMO V2 offline acceleration consistency

Existing LIMO 4WD bags only. Requires completed `tools/odom_v1/analyze.py` output.
No motion, recording, ROS node, EKF change or vx correction.

```bash
cd /home/sb/LOONAR
.venv-icp/bin/python tools/odom_v2/analyze.py --cutoff 2 --window 1 --excitation-rms 0.03
.venv-icp/bin/python tools/odom_v2/report.py
.venv-icp/bin/python -m unittest discover -s tools/odom_v2 -p 'test_*.py'
```

Output: `data/imu_vibration/odom_v2_analysis/{report.html,results.json,windows.csv,series/}`.
Dependencies: numpy, scipy, matplotlib, rosbags in existing `.venv-icp`.

**Gravity limitation:** all processed bags contain gravity-bearing acceleration
and yaw-only orientation. Rotating into base_link and subtracting initial static
ax creates a **fixed-tilt proxy**, not validated gravity-compensated body acceleration.
C_accel is conditional and every window is marked GRAVITY_UNVERIFIED_FIXED_TILT_PROXY.
EXCITED is necessary but insufficient for observability; UNOBSERVABLE has no C.
Dynamic tilt, accelerometer bias change, lateral motion, rotational acceleration
at the IMU mount, and timing can all produce longitudinal residual.

100 Hz header alignment reuses V1 timestamps. Filter each uninterrupted segment
with third-order zero-phase Butterworth and 0.21s quadratic SG derivative.
Exclude 1s at segment boundaries. These filters use future samples and are offline.
Use non-overlapping windows; records/windows are not assumed statistically independent.

Normal calibration references are existing hard-floor forward/reverse 2m runs
whose metadata in `data/imu_vibration/*/run.json` says no_slip=true. That metadata
is not a new GT verification. Estimate apparent lag on these references only
(search +/-0.3s in 10ms steps); require both peaks >0.6, non-boundary, lag spread
<=50ms to apply their median globally. It cannot separate sensor latency from
wheel/body dynamics. Per-target lag is diagnostic only. Estimate sigma from both
normal references' aligned valid residuals. It is not a calibrated slip probability.

GT is held apart: clock interpolation, known +X axis, valid frames, reprojection
<=1.5px, gaps <=0.25s, encoder distance >=0.02m. C_GT is longitudinal projection
ratio, not curved arc length. Camera exposure delay and attitude errors remain;
paired GT does not provide a clean binary slip label. No GT threshold labels
are inferred and no GT is used to tune filters, lag, normalization or estimates.

Sensitivity outputs at 1 and 3 Hz are stored under the main output directory.
The report uses the primary 2 Hz run and reports both sensitivity results.
Tests cover derivative/gain, constant-speed unobservability and delay sign.
V1 yaw is copied unchanged into every output series. Existing user-excluded
uphill recording remains excluded; four old runs without initial acceleration
reference are excluded instead of guessing gravity from another trial.
