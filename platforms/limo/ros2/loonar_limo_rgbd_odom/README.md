# LIMO RGB-D Odometry Experiment

This package is intentionally isolated from `loonar_limo_localization`, Nav2,
the 2.5D mapper, cFS and `vehicle_gatewayd`. It publishes no command and the
odometry node publishes no TF.
If the experiment is rejected, removing this package has no effect on the rest
of the rover software.

## Fixed experiment contract

| Item | Value |
| --- | --- |
| Camera | Orbbec DaBai on the LIMO |
| RGB | 640x480 requested, cropped/registered to 640x400, 30 Hz |
| Depth | 640x400 Y11/`16UC1`, 30 Hz, useful range 0.35-2.5 m |
| Odometry processing | at most 10 Hz, image decimation 2 |
| Output | `/rgbd/odom` (`nav_msgs/Odometry`) |
| Quality/debug | `/rgbd/odom_info`, `/rgbd/input_diagnostics` |
| Odometry TF output | disabled |
| Sensor TF | measured `base_link -> tof_link` plus Orbbec internal TF |
| EKF input | disabled; comparison only |

RTAB-Map RGB-D odometry requires depth registered into the color camera frame.
The camera launch requests `depth_registration=true`, RGB-depth synchronization,
and a 640x400 color ROI. The probe reports ERROR if RGB/depth dimensions or
`frame_id` differ, CameraInfo is invalid, or a stream is missing. Do not judge
odometry before this diagnostic reports `RGB-D input contract satisfied`.
The camera launch reuses `loonar_limo_tof/config/limo_tof_extrinsics.yaml`, so
it remains standalone after the mutually exclusive depth-only camera launch is
stopped. Set `publish_mount_tf:=false` only if another node already owns that
exact static transform.

## LIMO test sequence (not yet deployed)

Install the runtime dependency on the LIMO only when deployment is approved:

```bash
sudo apt update
sudo apt install ros-humble-rtabmap-ros
```

Build after copying the repository into `~/loonar_ws/src/loonar`:

```bash
source /opt/ros/humble/setup.bash
source ~/agilex_ws/install/setup.bash
cd ~/loonar_ws
colcon build --base-paths src/loonar/platforms/limo/ros2 \
  --packages-select loonar_limo_rgbd_odom --symlink-install
source install/setup.bash
```

The RGB-D camera profile and the existing depth-only profile are mutually
exclusive because both open the same USB camera. Stop the depth-only launch,
then use two terminals:

```bash
# Terminal 1: registered RGB + depth camera only
ros2 launch loonar_limo_rgbd_odom limo_rgbd_camera.launch.py
```

```bash
# Terminal 2: odometry experiment only
ros2 launch loonar_limo_rgbd_odom limo_rgbd_odom.launch.py
```

Inspect without connecting to EKF:

```bash
ros2 topic echo --once /rgbd/input_diagnostics
ros2 topic hz /rgbd/odom
ros2 topic echo /rgbd/odom_info
ros2 topic echo /rgbd/odom
ros2 topic info /tf --verbose
```

The RGB-D node uses `rgbd_odom` as the message frame but `publish_tf=false`, so
the existing EKF remains the only `odom -> base_link` TF owner.

## Acceptance before any EKF fusion

Record `/rgbd/odom`, `/rgbd/odom_info`, `/wheel/odom`, `/imu`, RGB, depth and TF.
Evaluate these cases separately: stationary 60 s, measured straight drive,
in-place rotation, rigid slope, deliberate blocked-wheel contact, and return to
the start. Accept only if:

1. the input diagnostic stays OK and odometry remains at 8 Hz or higher;
2. stationary translation/yaw does not wander materially;
3. `odom_info` declares loss instead of emitting a large false transform;
4. blocked wheels produce near-zero RGB-D displacement while wheel odometry moves;
5. CPU use leaves adequate margin for the later 2.5D process.

Do not tune the EKF or use `/rgbd/odom` for navigation during this experiment.
If registered depth is not actually published by the DaBai firmware/driver, stop
the test and discard this profile rather than feeding unregistered images to the
odometry node.
