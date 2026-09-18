# Acceleration-window C experiment

This branch adds `/odom_c_test` only. It does not edit V1, wheel odometry, EKF,
primitive manager, or TF. The test node reads `/wheel/odom`, `/imu`,
`/localization/dr`, `/localization/state`, and `/c_test/phase`.

## Input definition and limits

LIMO's previously evaluated IMU includes gravity and its orientation is yaw-only.
Do not select `linear` for this raw topic. The default `unvalidated` mode marks
C invalid and falls back to encoder vx. Select the mode explicitly:

- `linear`: input is verified gravity-free acceleration; no gravity subtraction.
- `orientation`: subtract gravity in the sensor frame, then transform to base_link;
  requires `orientation_validated:=true` and valid full attitude in a ROS ENU
  convention (stationary acceleration points up). Yaw-only orientation is insufficient.
- `static_bias_experiment`: subtract the stationary forward-axis mean, including
  constant gravity projection. This is an explicit constant-attitude experiment,
  not robust gravity compensation. Pitch changes, vibration, lever-arm effects,
  and actual slip can all contaminate C. `C_valid` in this mode checks numerical
  eligibility only; it is not evidence that the physical scale is correct.

Sensor-to-base TF is required. `imu_time_offset_s` shifts the IMU timestamp for
alignment (positive means later); default zero is not an estimated latency.
Approximate synchronization permits 25 ms header mismatch and logs the difference.
Actual signal latency must be evaluated separately; no GT is used to fit it.
The max experiment yaw rate is parameterized, default 0.05 rad/s, and affects
C eligibility only, not vehicle commands.

## Estimation

A continuous stationary window (default 1 s of already-confirmed V1 stationary
samples) estimates acceleration bias. ACCEL must start from that zero-velocity
condition. Trapezoidal acceleration integration starts at zero; least squares
uses the complete acceleration window, omits encoder speeds below the configured
minimum, and requires minimum velocity excursion, sample count and denominator.
`C_raw` is never clamped. In-range valid C_acc is applied after acceleration ends;
there is no retrospective rewriting of the acceleration trajectory. Before that,
or if invalid, the test odom falls back to encoder vx. Cruise never updates C.

DECEL is recorded through subsequent settling until stationary is confirmed.
Its velocity is reconstructed backwards from the independent terminal v=0 boundary:
`v_imu(t) = -integral(t .. confirmed_stop, a_corrected dt)`.
This avoids assuming C_acc to initialize deceleration velocity. C_dec therefore
becomes available only at the final stop. If it differs from C_acc beyond
`max_c_difference` (default absolute 0.25), is unobservable, or outside the valid
range, the run is marked unreliable and further application falls back. Previously
published poses are never retroactively changed.

Yaw orientation and angular rate come directly from V1. Test XY uses corrected
velocity and midpoint V1 yaw. Its covariance is deliberately uncalibrated (large
placeholder), and this topic is for comparison, not fusion into the existing EKF.
`v_imu` in samples.csv is causal during ACCEL and empty otherwise; reconstructed
DECEL v_imu is saved with every deceleration sample in windows.jsonl after STOP.

## Execute on a ROS2 host after building/sourcing this package

Start existing LIMO sensors and V1 as usual. Use a new output directory per run.
For the explicitly assumed constant-attitude LIMO experiment:

```bash
ros2 run loonar_localization odom_c_test --ros-args \
  -p acceleration_mode:=static_bias_experiment \
  -p output_dir:=/tmp/c_acc_run_01
```

Record on another terminal (bag directory must not exist):

```bash
ros2 bag record -o /tmp/c_acc_run_01/bag \
  /imu /wheel/odom /odometry/filtered /localization/dr /localization/state \
  /odom_c_test /c_test/phase /c_test/diagnostics /cmd_vel /tf /tf_static
```

The profile tool is dry-run unless `--execute` is present:

```bash
ros2 run loonar_localization c_ramp \
  --speed 0.25 --ramp 2.5 --cruise 2 --decel 2.5 --stop 4
```

To run the actual motion, repeat with `--execute`. It sends STOP during the initial
bias period and requires fresh valid bias diagnostics before beginning the ramp.
It sends zero command on completion/Ctrl+C. This is a time-based speed profile,
not an actual-distance controller: the default nominal commanded distance is
1.125 m and slip changes the actual distance. No camera or GT controls motion.
Stop the bag recorder with Ctrl+C after the profile ends.

Outputs: samples.csv, windows.jsonl, config.json, /odom_c_test and
/c_test/diagnostics. C_acc/C_dec are recorded raw, along with validity, applied
coefficient, corrected acceleration, stationary bias, encoder velocity, V1 yaw,
and test XY. Missing input messages produce no new odometry; the next timestamp
gap invalidates the experiment. Sensor/TF errors are reported on diagnostics.

## Evaluation only

The evaluator consumes a *previously ROS-clock-aligned* AprilTag comparison.csv
in the existing primitive comparison schema. It does not collect GT or estimate
the camera time offset. Independently captured GT must first be synchronized and
converted to that schema; do not substitute camera receipt time for ROS time.

```bash
PYTHONPATH=common/ros2/loonar_localization .venv-icp/bin/python \
  -m loonar_localization.c_evaluate \
  --samples /path/c_acc_run_01/samples.csv \
  --gt-comparison /path/aligned/comparison.csv \
  --output /path/c_acc_run_01/evaluation
```

Produces evaluation.json with raw C_acc, C_dec, per-phase signed
C_GT=projected GT displacement/integrated encoder displacement, and start-aligned
position errors for encoder-only, V1 and test odometry; paired.csv retains evidence.
GT endpoint interpolation rejects gaps above 0.25 s; test interpolation rejects
0.08 s gaps. Phase endpoints exclude the small interval between phase samples.
No scale or heading parameter is fitted to minimize tracking error.

Synthetic core tests and isolated ROS Humble adapter checks passed. No physical
ramp trial has been performed and no real C accuracy is claimed. Existing constant
speed primitive bags are not a substitute for this deliberately excited profile.
