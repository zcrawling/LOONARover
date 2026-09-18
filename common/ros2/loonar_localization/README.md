# Slip/contact-tolerant localization

Implementation of the [project architecture](../../../docs/odometry-localization.md).
Platform-independent NumPy/SciPy core and three ROS2 nodes; no actuator publisher.
Provisional thresholds are parameters, not validated LIMO/LOONAR mechanical limits.

## Components

- `core.py`: command primitive prior and feedback-driven rotate/stop/straight/stop sequence;
  windowed stationary detector; forward-only zero/bias update; V1 integration;
  encoder baseline; causal confidence monitor; motion-dependent constraint gating.
- `registration.py`: bounded stop keyframes; point-to-plane ICP; correspondence,
  inlier, convergence, residual, normal-information degeneracy and tilt gates;
  retained accepted anchor and planar map correction. High-quality near-zero body
  translation with substantial encoder travel produces STUCK_SUSPECT evidence.
- `ros_nodes.py`: synchronized wheel/IMU adapter and separate stop registration node.
  TF transforms inputs into base_link. No zero-filled missing sensors.
- `replay.py`: existing bag offline replay, compares unchanged V1 with zero updates disabled.

V1 still has no lateral velocity state: NHC weight is an output for a future
velocity estimator, `nhc_applied=false`. It does not pretend to measure lateral
slip or implement a soft lateral-state update. Covariances are configurable model
uncertainty, not validated error bounds. Confidence changes do not rescale vx.
The primitive state machine accepts relative yaw/distance goals, waits for confirmed
STOP, checks gyro/DR target completion, and emits intent. `/localization/primitive_goal`
and `/localization/primitive_intent` use JSON String. Goal fields: relative_yaw (rad),
distance (signed m), slow (bool); cancel=true cancels explicitly. Only an autonomy
caller may route intent through the existing Gateway. Nothing here publishes cmd_vel.
DR distance completion is not a guarantee of actual travel distance under slip.

LIMO V2 acceleration is gravity-bearing and orientation is yaw-only: default
`gravity_compensation_validated=false`. Longitudinal score is unavailable until a
platform adapter supplies independently validated gravity/lever-arm compensated
acceleration. A low score never rules out constant-speed common-mode slip.
Optional wheel_position_topic consumes named cumulative positions with an explicit
SI scale. The LIMO profile uses its recorded left/right chassis odometers in metres;
it does not claim four independent wheel sensors. Missing configured side data
prevents stationary confirmation, while aggregate V1 remains available. Motor
current is not fabricated.

## Build and shadow execution

```bash
colcon build --base-paths common/ros2/loonar_localization --packages-select loonar_localization
source install/setup.bash
ros2 launch loonar_localization localization.launch.py
```

Default publishes `/localization/dr` (Odometry) and `/localization/state` (JSON String).
It does not launch a driver, issue motion commands, replace the existing EKF, or
publish TF. `/cmd_vel` is a prior only; command_prior_age controls prior freshness,
not command authority or an actuator timeout.

To run stop registration with an already verified point cloud and TF:

```bash
ros2 launch loonar_localization localization.launch.py registration_enabled:=true
```

`/localization/registration` reports anchor/quality/rejection/correction evidence.
`publish_odom_tf` and `publish_map_tf` are independently opt-in. Before enabling
odom TF, explicitly remove the existing EKF's ownership of that same edge. The
package never changes existing localization launch/services on its own.
Topic names can be remapped; base/odom/map frames and all thresholds are parameters.
Modules can be disabled at startup with `primitive_enabled`, `stationary_enabled`,
`zero_update_enabled`, `monitor_enabled`, `constraints_enabled`, and
`registration_enabled`. Parameters are startup configuration; restart to apply changes.

In gyro_yaw mode ICP uses DR translation as initialization and gyro yaw as a fixed prior.
Acceptance still requires independent geometric quality gates. Planar/degenerate scenes
are rejected even if residual is tiny. Converged ICP can still find a wrong local
minimum; thresholds and scene-specific ambiguity need physical validation before
using map correction for navigation. Retain bounded last accepted anchor, no global
cloud accumulation. Failed registration does not reset DR or replace the anchor;
it reports increasing correction uncertainty. Odom uncertainty continues to grow.

Stationary cloud acquisition must match fresh stationary evidence in the history.
Map correction uses that stop's historical odom, never the processing-time pose.
A planar correction is accepted only within the configured inter-keyframe tilt
bound. Three-dimensional pose estimation is not silently claimed by a planar DR.

## Offline verification

```bash
PYTHONPATH=common/ros2/loonar_localization .venv-icp/bin/python -m unittest discover -s common/ros2/loonar_localization/tests -v
PYTHONPATH=common/ros2/loonar_localization .venv-icp/bin/python -m loonar_localization.replay \
  --manifest data/imu_vibration/odom_v1_analysis/results.json \
  --output data/imu_vibration/localization_architecture_replay
```

Replay needs rosbags in addition to core dependencies. Existing V1 exclusions and
bias provenance are preserved. Missing command event logs leave the prior UNKNOWN.
Synthetic tests exercise static bias, false STOP, gaps, V1 identity, rotation with
translation, planar degeneracy, known relative pose and rejected-anchor retention.
These are not claims of successful outdoor ToF localization.

LIMO profile: `ros2 launch loonar_limo_localization limo_slip_contact_shadow.launch.py`
requires building this package and the existing LIMO localization package. It uses
LIMO frame/sensor settings and leaves both TF publishers disabled.


## Gyro-yaw constrained ToF translation correction

Default ICP `mode=gyro_yaw`: keep the relative DR gyro yaw fixed, optimize XYZ
translation and relative roll/pitch (five variables). Only XY correction is applied
into the planar map->odom transform; Z/tilt remain diagnostics. Existing continuous
DR and encoder vx are unchanged. `mode=full_6d` retains the older six-variable ICP.
This is a local registration initialized by DR, not global relocalization.

Inputs: `/localization/state` from the existing DR node and metric XYZ PointCloud2
on `/tof/depth/points`, transformed to base_link at the cloud timestamp using TF.
Configure the actual optical/sensor extrinsic, not an identity guess. The node
accepts a cloud only at a confirmed stationary time, retains one accepted keyframe,
and does not accumulate a global point cloud. One registration attempt is made per
stop after sufficient points are available. Rejected registration keeps the anchor
and map correction unchanged. `uncertainty_growth` is diagnostic, not a fused
covariance update. Stop keyframes need overlap; this implementation does not
accumulate/average multiple depth frames to reduce ToF noise.

Launch alongside an existing DR/state node (after colcon build and sourcing install):

```bash
ros2 launch loonar_localization tof_translation.launch.py \
  points_topic:=/tof/depth/points
ros2 topic echo /localization/registration
```

The launch starts only registration, not a driver or motion publisher. TF publishing
is off for shadow evaluation. After validating results, `publish_map_tf:=true`
enables map->odom broadcasting; ensure no competing map->odom publisher and that
odom->base_link is the same DR used by `/localization/state`.
The diagnostic JSON includes acceptance/rejection, inlier ratio, Euclidean and
point-plane RMSE, conditioning, fixed yaw, XYZ translation, corrected stop pose,
and map->odom. Quality thresholds are provisional ROS parameters, not validated
I200DK terrain limits. `max_tilt` defaults to 0.15 rad; larger inter-stop tilt is
rejected because the correction frame is still planar.

A flat floor is insufficient for XY translation; fixed yaw does not make planar
translation observable. Texture visible in RGB alone does not help this depth ICP.
Fixed gyro yaw error can bias translation, and successful convergence is not proof
of the correct match in repetitive geometry. Compare against AprilTag for evaluation.

Offline pair check (clouds must already be in their respective base_link frames):

```bash
PYTHONPATH=common/ros2/loonar_localization .venv-icp/bin/python -m loonar_localization.icp_pair \
  --target /path/stop_a.npy --source /path/stop_b.npy \
  --yaw-deg 30 --initial-x 0.05 --initial-y 0 \
  --output /tmp/icp_pair.json
```

`initial-x/y` are DR relative displacement in STOP A coordinates, not world
coordinates. Synthetic known-transform tests cover lateral displacement, relative
tilt, fixed yaw, planar rejection, and unchanged DR/anchor on rejection. Physical
I200DK performance and ROS sensor integration still require validation.

## Independent acceleration C test

See [C_ACCEL_EXPERIMENT.md](C_ACCEL_EXPERIMENT.md) for the independent `/odom_c_test`
node, deliberate ramp command tool, acceleration definitions and evaluation.
V1/core/TF are unchanged by this experiment.
