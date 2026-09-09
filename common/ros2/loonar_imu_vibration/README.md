# IMU vibration -> longitudinal wheel correction experiment

This package implements an **unproven supervised experiment**, not a deployed
slip solution. It estimates `C_v = signed_GT_distance / signed_encoder_distance`
over a trailing window. It never derives a label from IMU/encoder agreement,
integrates acceleration into velocity/position, changes wheel yaw, modifies the
existing EKF, or publishes vehicle commands. It has no terrain-map dependency.

## Paper and scope

Yi et al., *Kinematic Modeling and Analysis of Skid-Steered Mobile Robots With
Applications to Low-Cost Inertial-Measurement-Unit-Based Motion Estimation*,
IEEE T-RO 25(5), 2009, DOI 10.1109/TRO.2009.2026506, is **not** a vibration-feature
regression paper. Section III assumes a four-wheel platform, firm ground, and
four-wheel contact. Equations (12)-(15) form virtual velocity observations from
kinematic/slip constraints; Section IV uses an EKF. Section V uses synchronized
external vision as reference. Its coefficients are not transferred to LOONAR's
two driven wheels and rear support. The supplied scalar-C design is a separate
hypothesis motivated by slip compensation, not a reproduction of that paper.

Vibration need not uniquely determine slip: surface, speed, wheel design,
mounting, motor vibration, load and sensor filtering all affect the signal.
Improvement must be established on held-out, independently measured runs.

## Files and data flow

- `core.py`: shared causal windowing, raw/high-pass time-domain features,
  inference and fallback, independent of ROS.
- `record.py`: read-only rosbag acquisition and run metadata.
- `data.py`: rosbag/normalized CSV input and independent signed GT contract.
- `pipeline.py`, `cli.py`: feature dataset, run-separated OLS/Ridge training,
  causal longitudinal A/B evaluation and per-run bootstrap summaries.
- `node.py`: shadow runtime; corrected twist plus diagnostics. No pose/TF.
- `tests/`: deterministic signal, external-GT, leakage and runtime checks.

```
baseline /wheel/odom ----> original encoder/EKF (unchanged)
          | vx,wz
IMU 6 axes + wheel history -> trailing features -> fitted C_v
          |                                      |
          +------------------- vx * C_v ----------+--> /wheel/twist_corrected

external GT + recorded history -> window labels -> train/validation/test by run
```

First-version features: raw and/or window-local first-order high-pass versions
of ax/ay/az/gx/gy/gz, each with mean, std, RMS, peak-to-peak, MAD, skewness,
excess kurtosis and first-difference RMS. Encoder vx and wz receive the same
eight raw statistics. Default `both` gives 112 features. The high-pass filter
separates slow changes only approximately; maneuvers are not guaranteed to be
removed. No FFT, neural network or stuck classifier is required.

## Build

On the rover, after sourcing the appropriate ROS and workspace environment:

```bash
cd ~/loonar_ws
colcon build --base-paths src/loonar/common/ros2 \
  --packages-select loonar_imu_vibration --symlink-install
source install/setup.bash
```

Runtime needs NumPy and standard ROS messages. Offline commands need NumPy;
`export-bag` additionally needs `rosbags` (the optional `bag` pip extra).
From this repository's existing analysis venv, no ROS installation is required:

```bash
export PYTHONPATH=/home/sb/LOONAR/common/ros2/loonar_imu_vibration
/home/sb/LOONAR/.venv-icp/bin/python -m loonar_imu_vibration.cli --help
```

## Collect data

Run the existing base/encoder launch separately. The following recorder does
not move the rover; use the existing timed-motion test or manual driving.

```bash
ros2 run loonar_imu_vibration vibration_record \
  --output ~/vibration_runs/sand_low_01 \
  --run-id sand_low_01 --terrain-id simulant --preparation-id sand_batch_A \
  --profile-id bno085_mount_A_raw100_encodercal_A \
  --imu-topic /imu/data --wheel-topic /wheel/odom \
  --gt-topic /ground_truth/odom
```

Use `/imu` and a **different profile id** for LIMO's stock IMU. Do not identify
old LIMO logs as BNO085 training data. Profile ids must identify hardware,
mounting/axes, accel report type (gravity-containing or gravity-removed), sample
rate/filter configuration, load configuration when relevant, and encoder
calibration. Different profiles cannot silently share a trained model.

Requested topics: IMU, wheel odom, `/wheel/odometer`, external GT, `/cmd_vel`,
`/tf`, `/tf_static`, `/odometry/filtered`, corrected twist and diagnostics.
`--extra-topic` can be repeated for MCU counts, left/right velocity and motor
current. Existing LIMO `/wheel/odometer` contains cumulative metres, **not raw
encoder counts**; the logger cannot manufacture unavailable MCU measurements.
Check bag metadata for actual topic presence. Six-axis IMU history plus vx/wz
is the minimum model input. Optional command history is exported for inspection,
not used to derive GT or included in the initial model features.

Collect repeated hard-floor no-slip runs and independently prepared simulant
runs at several speeds, acceleration/deceleration, turns, spin, blocked-wheel
conditions and slopes when available. Store independent preparation ids.
Feature amplitude can be driven by speed; keeping wheel-state features and
testing across speeds is necessary. Verify real IMU sample freshness, filtering
and vibration bandwidth before interpreting a nominal 100 Hz stream.

## Export and label

```bash
vibration_tool export-bag ~/vibration_runs/sand_low_01/bag \
  --output ~/vibration_dataset/sand_low_01 \
  --run-id sand_low_01 --terrain-id simulant --preparation-id sand_batch_A \
  --profile-id bno085_mount_A_raw100_encodercal_A \
  --imu-topic /imu/data --gt-topic /ground_truth/odom \
  --gt-source overhead_apriltag_calibration_A
```

GT must be synchronized independent `nav_msgs/Odometry` of the **robot base**,
in a stable external frame, with a valid orientation. Resolve camera/tag lever
arm and axes upstream. The exporter projects successive external position
increments on the midpoint body-forward axis to obtain signed longitudinal
distance. It handles reverse sign and 3D attitude; lateral displacement is not
mistaken for longitudinal travel. This projection assumes sufficiently sampled
external poses. Noisy external position data can make labels noisy too.

Alternatively provide `gt.csv` with `t,s_m`: timestamp seconds in the same clock
as sensors and independently measured cumulative **signed longitudinal** metres.
Set `gt_source`, `gt_kind: external`, and any measured `gt_time_offset_s` in
`run.json`. GT gaps are rejected, not interpolated across arbitrarily.
Pseudo-GT may be exported only with explicit `--gt-kind pseudo`; the first
train/test baseline rejects it so unvalidated ToF/EKF cannot masquerade as truth.

With no GT topic, export still works for feature diagnostics. A run's final
tape-measured distance **does not label each 1 s window**. Such runs remain
unlabeled even if `actual_distance_m` is populated. Do not spread a final
distance uniformly across time using the command or encoder trajectory.

Normalized input may be `records.jsonl` or `records.csv` beside `run.json`:

- IMU row: `kind=imu,t,ax,ay,az,gx,gy,gz` in SI units.
- Wheel row: `kind=wheel,t,vx,wz` in SI units.
- Optional command row: `kind=cmd,t,vx,wz`.

Preserve event delivery order. Each sensor's stamps must strictly increase;
split runs at clock resets. CSV row order represents availability, not an
invitation to use future IMU samples. Native bag export preserves delivery order.

```bash
vibration_tool dataset --runs ~/vibration_dataset/run01 ~/vibration_dataset/run02 \
  --output dataset.json --window-s 1 --sample-hz 100 --stride-s 0.05
```

The example lists two runs for feature extraction, not enough for all three
training partitions. Every sample stores its run/terrain/preparation, window
bounds, encoder/GT distance, features and C_v (null when GT is unavailable).
Low-distance and reversing windows are excluded from regression. Encoder moving
with zero external displacement legitimately labels C=0; this does not make a
runtime stuck detector. Commanded and actual speeds are recorded where available.

## Train and evaluate

Provide explicit `split.json`, for example:

```json
{"train":["run01","run02"],"validation":["run03"],"test":["run04"]}
```

```bash
vibration_tool train dataset.json --split split.json --split-preparations \
  --output ridge.json
vibration_tool evaluate dataset.json --model ridge.json --output evaluation.json
```

All dataset runs must belong to exactly one partition. `--split-preparations`
also rejects preparation overlap. Scaling is fitted only on training data;
OLS (`alpha=0`) and Ridge candidates are selected with mean validation-run C
MAE. The test set is not used in fitting or selection. Keep sufficient no-slip
and slipping runs in held-out data; one run per class cannot establish a
statistical improvement. Export is inert JSON, never executable pickle.

Evaluation replays event order using the runtime feature/inference engine and
applies C only to each new wheel increment. It does **not** sum overlapping
1 s window distances. Warmup, gaps and invalid predictions use C=1. It reports
signed distance, final and relative errors, cumulative longitudinal-distance
RMSE, C statistics/window residuals and fallback counts. Spatial trajectory ATE
is explicitly unavailable: this module does not change yaw or lateral slip.

The report separates no-slip runs from other terrain runs. Bootstrap resamples
whole runs, not overlapping windows. `--no-slip-tolerance-m` supplies the user's
chosen allowable no-slip degradation; there is no silently fixed acceptance
threshold. Small-run intervals are exploratory. Model artifacts remain marked
`approved_for_use: false`; writing a model file alone is not proof of efficacy.

## Shadow runtime

```bash
ros2 run loonar_imu_vibration imu_vibration_correction_node --ros-args \
  -p imu_topic:=/imu -p profile_id:=limo_stock_imu_mount_v1
```

No model means C=1. `enabled` defaults to false. Only after reviewing held-out
results, explicitly enable a model matching the sensor profile and all feature
parameters:

```bash
ros2 run loonar_imu_vibration imu_vibration_correction_node --ros-args \
  -p imu_topic:=/imu/data -p profile_id:=bno085_mount_A_raw100_encodercal_A \
  -p model_path:=/absolute/path/ridge.json -p enabled:=true
```

Outputs:

| Topic | Type / meaning |
|---|---|
| `/wheel/twist_corrected` | `TwistWithCovarianceStamped`, only linear.x multiplied by C |
| `/terrain_correction/c_v` | `Float64`, applied coefficient |
| `/terrain_correction/confidence` | `Float64`, feature-support score, **not probability** |
| `/terrain_correction/diagnostics` | stamped reason, raw/corrected increments, 112 features |

The original `/wheel/odom` remains untouched. `/wheel/odom_corrected` is
deliberately not published: changing twist while copying an uncorrected pose
would make that Odometry message inconsistent. Pose integration and EKF
attachment are later responsibilities. Angular twist is unchanged, even when
the raw encoder yaw is inaccurate. Twist covariance is transformed and retains
at least the original vx variance; learned-model uncertainty is not calibrated.

Fallback reasons include no model, disabled correction, incomplete/gapped
history, small longitudinal travel, direction reversal, frame/time mismatch,
out-of-training-support input, low support score and out-of-range prediction.
Bad C is **rejected to C=1**, not clipped to an apparently valid correction.
This fallback does not assert encoder accuracy during slip; it preserves the
baseline while the experiment lacks reliable evidence. Missing wheel input
emits diagnostics rather than inventing vehicle motion or issuing a stop.

Defaults are experiment settings, parameterized rather than mechanical limits:
window 1 s, resample 100 Hz, max sample gap 0.05 s, minimum encoder travel 0.02 m,
minimum speed for sign checks 0.005 m/s, high-pass tau 0.15 s, C range [0,2],
maximum standardized feature magnitude 6, minimum support 0.05, max stamp age
0.2 s. Runtime updates on each wheel message (typically 50 Hz); the offline
training stride defaults to 20 Hz. All feature settings must match the model.
Model portability across sample profiles is not assumed.

## Verification

```bash
PYTHONPATH=common/ros2/loonar_imu_vibration .venv-icp/bin/python -m unittest \
  discover -s common/ros2/loonar_imu_vibration/tests -v
```

Synthetic tests exercise known signals, signed reverse/zero-motion labels,
missing GT, gaps, time reset, split leakage, C rejection and causal accumulated
distance. Synthetic success validates plumbing, not physical slip correction.
ROS integration is checked separately in a network-isolated container/domain.

The label describes average slip over the preceding window. Applying its
prediction to the newest wheel increment assumes slip changes slowly enough
within that window. Abrupt terrain changes can therefore produce lag even with
accurate retrospective window predictions. Causal accumulated-distance tests,
including transitions, are required before choosing the window size.

See [VALIDATION.md](VALIDATION.md) for the local build and data checks.
