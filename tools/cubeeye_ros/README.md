# LIMO I200DK / STOP-to-STOP ICP test

## Shared bridge recovery and timestamp diagnostics

The bridge is also used by LOONAR's `platforms/loonar/deploy/run-tof.sh`.
It restarts its owned SDK helper on EOF, helper exit, or missing frames:
`--startup-timeout 20`, `--frame-timeout 3`, `--retry-delay 2` (seconds).
Retries continue until shutdown; a missing/disconnected camera is not reported
as healthy. Each new helper has an independent reader and frame buffer, so frames
from the previous session are not replayed. Recovery necessarily leaves a gap.

`/tof/status` includes `state`, `restarts`, and fault reasons. Frame records also
include `host_callback_ns`, `host_receive_ns`, `host_publish_ns` (after publish
returns), and the unconverted `device_timestamp`. Waiting/restart records do not
contain a frame timestamp. Consumers should check for that field before treating
a status record as a frame.

PointCloud2 headers remain host SDK callback time, **not calibrated exposure
time**. The publisher checks for frames every 5 ms, publishes the latest frame at
at most `--hz`, and deliberately skips excess SDK frames. Callback-to-recording
delay is not an exposure-time correction. The SDK helper's pipe write remains
blocking; receive/publish diagnostics make that downstream delay inspectable.

SDK error 3 is `NoSuchDevice`. Restarting fixes the former silent, permanent
stream stall when the device becomes available again; it cannot recover missing
frames or guarantee a physically disconnected device returns.

Synthetic recovery tests (source the installed ROS distribution first):

```bash
/usr/bin/python3 tools/cubeeye_ros/test_bridge_recovery.py
```

Deployed on wego@172.20.10.12. SDK lives outside the repository at ~/cubeeye_sdk
(vendor Ubuntu22 SDK v2.5.11). Source bridge compiles its SDK helper into
~/.cache/loonar/cubeeye, leaving ROS Python separate from SDK native libraries.

## On LIMO through SSH

Sensor/ICP recording without any motion command:

```bash
bash ~/loonar_ws/src/loonar/platforms/limo/scripts/run_tof_icp_test.sh --observe-only
```

Actual short straight motion, surrounded by stationary-confirmed STOP dwell:

```bash
bash ~/loonar_ws/src/loonar/platforms/limo/scripts/run_tof_icp_test.sh \
  --distance 0.3 --speed 0.1 --stop-hold 4
```

The distance target is DR displacement, not guaranteed ground-truth distance.
Ctrl+C stops the owned trial and sends zero command if motion was started.
The script prepares the existing sensor/EKF stack, starts the I200DK bridge and
shadow ICP, records the test and stops its owned bridge/DR/ICP processes afterward.
Existing baseline sensor/EKF processes remain. The script refuses a duplicate DR.
Results: ~/odom_tests/tof_<timestamp>/, including icp_summary.json, rover/bag,
events/states, SDK/ICP logs, and up to 30 optical XYZ .npy snapshots.

## Frames and topics

User specified I200DK mount equals the previous ToF mount:
base_link -> sensor body = (0.150,0,0.033) m, roll/pitch/yaw = 0 (provisional
measurement, not refined calibration). Unique optical frame `cubeeye_optical`:
optical right/down/forward -> base forward/left/up via (z,-x,-y).
The bridge publishes that static TF; it does not reuse DaBai frame names.
CLI --x/--y/--z/--roll/--pitch/--yaw override geometry (angles radians).

SDK PointCloud F32 arrays are used directly, not deprojected with invented camera
intrinsics. Vendor example scales XYZ by 1000 for millimetre display; ROS points
are published in metres. Frame timestamp is the host SDK callback timestamp;
raw device timestamp is recorded in /tof/status without pretending it is ROS epoch.
Actual camera scale, axis convention and exposure latency still need measured
scene validation. Native raw SDK frame format is not a physical accuracy certificate.

- /tof/depth/points: sensor_msgs/PointCloud2, optical coordinates, default 5 Hz,
  image stride 4, finite points with optical Z>0.1m and range<5m.
- /tof/status: input dimensions, valid points, depth median, timestamps, rate.
- /localization/dr: existing encoder/gyro continuous baseline.
- /localization/registration: quality gate and correction details.
- /odom_tof_test: map-frame corrected pose, gyro yaw retained. Before any accepted
  correction it follows DR. Covariance is an uncalibrated placeholder.

ICP preserves gyro relative yaw, fits translation and relative roll/pitch,
applies XY correction only, and retains its accepted anchor on rejection.
No map->odom TF is broadcast by this test. No existing EKF/odom pose is overwritten.
Points are range/voxel limited before ICP. Flat or poorly observed geometry must
be rejected, even when DR initializes the match. Frame-to-frame overlap is required.
One cloud per STOP is used; no temporal denoising or global accumulation is performed.
The summary displacement numbers compare estimators, not accuracy against GT.

## Verified on hardware, 2026-09-16

I200DU2608000212 recognized; 640x480 SDK XYZ received. USB connection was 480M
(USB2). Stationary integration recorded 49 point clouds in approximately 10 seconds,
with fresh IMU/wheel/V1 and zero motion commands. ICP inputs reached the node, but
current scene produced near-range clouds (median optical Z around 0.11m) and too
few points after voxel aggregation: no accepted correction. This is a functioning
sensor/ROS/recording path, not a successful moving ICP accuracy validation.
Do not lower quality thresholds merely to label this scene successful.

Follow-up scene check: after the user's front-scene check, median optical depth
was 1.2–1.5 m with about 16k valid points per published cloud. A second stationary
trial recorded 47 clouds and `anchor_initialized`; no movement commands were sent
and all three odometry displacement outputs were zero. There is no accepted A-B
correction in this stationary trial because it contains only one confirmed STOP.
Actual moving A-B correction accuracy remains untested.
