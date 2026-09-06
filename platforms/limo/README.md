# LIMO Validation Platform

This platform is the current development and end-to-end validation target:
NUC12WSKi7, Ubuntu 22.04.3, and ROS 2 Humble. (The initial NUC11 inventory
was corrected by direct inspection.)

It will provide `LimoBackend` to `vehicle_gatewayd`. LIMO-specific driver,
topic and calibration details must stay in this folder. Common autonomy and
mission code must not depend on them.

## Verified integration facts

- Workspace: `/home/wego/agilex_ws`; vendor package: `limo_base`.
- LIMO driver subscribes to `/cmd_vel` (`geometry_msgs/msg/Twist`) and publishes
  `/odom`, `/imu`, and `/limo_status`; its launch remaps odometry to
  `/wheel/odom`.
- The base driver uses a CP2102 serial device at 460800 baud. The observed
  default is `/dev/ttyUSB1`, but two CP2102 devices share the same USB serial
  identifier. A by-path udev alias must be installed and verified before any
  service uses a persistent device name.
- Orbbec depth and UVC camera devices are present. No ROS nodes were active
  during the inventory, so live status rates and LIMO motion mode remain a
  start-up acceptance check.
- `video/` records the inspected Orbbec-integrated RGB UVC identity and uses
  the shared direct-camera software H.264/UDP sender without passing through ROS.

`vehicle_gatewayd` must be the only project publisher to `/cmd_vel`. The vendor
`limo_base` process remains the serial owner inside `LimoBackend`.

## Implemented validation stack

- `ros2/loonar_limo_backend` is the sole project-side `/cmd_vel` publisher.
  It receives only Gateway packets through the backend Unix socket, maps
  `linear_mps` and `angular_radps` to `Twist.linear.x` and `Twist.angular.z`,
  and forwards explicit STOP as a zero Twist. It does not clamp commands or
  create disconnect/status-timeout/expiry behavior.
- `/limo_status`, `/wheel/odom` and `/imu` are subscribed to lock their platform
  contract. They are diagnostic inputs and never gate or rewrite motion. Once
  per second the backend sends their observed battery-voltage, odometry and IMU
  values as common `VehicleStatus`; unavailable fields remain invalid.
- `systemd/` contains user-service templates. They use `%t` (the per-user
  runtime directory), not a machine-wide `/run` path, so sockets are private
  to the `wego` session.

Build on the validation NUC without modifying the vendor workspace:

```bash
source /opt/ros/humble/setup.bash
source /home/wego/agilex_ws/install/setup.bash
cd /home/wego/loonar_ws
colcon build --packages-select loonar_limo_backend --symlink-install
```

The Gateway starts in explicit `STOP` mode. LIMO's physical SWD/control mode
still determines whether the manufacturer base driver will execute `/cmd_vel`.

## Live acceptance harness

`scripts/live_gateway_test.sh` is the operator-facing G4 harness. It is
non-moving by default and displays fresh `/limo_status` as a manufacturer-driver
diagnostic. A non-zero test is opt-in with `--move`; its supplied command values
are handed to the Gateway unchanged.

`control_mode` is printed for diagnosis only. Its numerical mapping is
firmware-specific and must not be used as a Gateway command gate. SWD selects
the vehicle motion mode; it is not a Gateway authority input.

```bash
cd /home/wego/loonar_ws/src/loonar
bash platforms/limo/scripts/live_gateway_test.sh --start-base
# After the no-motion smoke pass and safety confirmation:
bash platforms/limo/scripts/live_gateway_test.sh --start-base --move --linear 0.05 --duration 1000
```

## Offline DaBai point-cloud ICP preview

The LIMO depth device was identified by its Orbbec SDK as **DaBai** (USB PID
`0x060e`), not the Astra Mini profile. Its verified depth profile is
`640x400@30` and the validated ROS 2 launch is:

```bash
ros2 launch orbbec_camera dabai.launch.py \
  camera_name:=tof enable_color:=false enable_ir:=false \
  enable_depth:=true enable_point_cloud:=true \
  enable_colored_point_cloud:=false
```

For a short offline inspection recording, keep the robot still or move it
slowly and record only several seconds of `/tof/depth/points`:

```bash
ros2 bag record -o ~/tof_bags/dabai_multiframe \
  /tof/depth/points /tof/depth/camera_info /tf /tf_static
```

`tools/icp_rosbag.py` is a deliberately limited diagnostic utility. It reads
the bag directly, voxel-downsamples selected frames, performs sequential
point-to-point ICP without TF/odom, and writes a binary PLY for CloudCompare or
MeshLab. It is **not** the planned rover localization/mapping implementation;
it is useful only to judge raw point-cloud quality before the 2.5D pipeline is
built.

On the analysis PC, install its isolated Python dependencies once:

```bash
python3 -m venv .venv-icp
source .venv-icp/bin/activate
python -m pip install --upgrade pip
python -m pip install numpy scipy rosbags
```

Run from the repository root after transferring the rosbag:

```bash
python platforms/limo/tools/icp_rosbag.py ~/Downloads/dabai_multiframe \
  --topic /tof/depth/points \
  --stride 5 --max-frames 60 --voxel-m 0.03 \
  --max-correspondence-m 0.15 \
  --output ~/Downloads/dabai_icp_preview.ply \
  --poses-csv ~/Downloads/dabai_icp_poses.csv
```

Start with five-frame stride and slow motion. If ICP prints poor fitness or
"too few correspondences", use a smaller stride before increasing its
correspondence distance. The resulting PLY has no `odom` frame guarantee and
will accumulate drift by design.

## Fixed LIMO DaBai ToF bringup

Use the project launch rather than the old `astra_camera` command. The LIMO's
connected Orbbec device identifies itself as **DaBai** and was live-verified
with this exact depth-only stream:

| Item | Fixed value |
|---|---|
| ROS namespace | `/tof` |
| Depth | `640x400`, `Y11`, `30 Hz` |
| Enabled outputs | `/tof/depth/image_raw`, `/tof/depth/camera_info`, `/tof/depth/points` |
| Disabled | RGB, IR, coloured point cloud |
| Driver-owned TF | `tof_link -> tof_depth_frame -> tof_depth_optical_frame` |

Install the small LOONAR launch package into the LIMO workspace once:

```bash
cd ~/loonar_ws
colcon build --base-paths src/loonar/platforms/limo/ros2 \
  --packages-select loonar_limo_tof --symlink-install
source install/setup.bash
bash src/loonar/platforms/limo/scripts/start_dabai_tof.sh
```

The old `astra_camera` 640x480 setup must not be used: it was an unsupported
profile on this DaBai and produced an all-zero depth image.

The configuration was re-run through this LOONAR launch on the LIMO: the
driver reported DaBai serial `AU1SB3302CG`, the depth image was `640x400
16UC1`, a cloud frame contained valid points in `tof_depth_optical_frame`, and
the driver reported approximately `29 Hz`.  It sends no vehicle command.

Quick re-check after starting it:

```bash
ros2 topic echo --once /tof/depth/image_raw
ros2 topic echo --once /tof/depth/points
ros2 topic echo --once /tf
```

### TF: fixed boundary and the one measurement still required

The driver publishes its internal sensor chain correctly. What it cannot know
is where LIMO physically mounts the camera, so the remaining edge is:

```text
odom -> base_link -> tof_link -> tof_depth_frame -> tof_depth_optical_frame
                    ^
                    one physical mount transform
```

The manufacturer source on the LIMO contains incompatible **simulation**
values for the depth camera height (`0.03 m` in the Ackermann Xacro and
`0.30 m` in the four-wheel-differential Xacro). Neither is reliable evidence
for this physical rover. We therefore do not publish a guessed transform.
Record the six measured values in
`ros2/loonar_limo_tof/config/limo_tof_extrinsics.yaml`, then pass them
explicitly when ready:

```bash
bash src/loonar/platforms/limo/scripts/start_dabai_tof.sh \
  publish_mount_tf:=true \
  mount_x_m:=MEASURED_X mount_y_m:=MEASURED_Y mount_z_m:=MEASURED_Z \
  mount_roll_rad:=MEASURED_ROLL mount_pitch_rad:=MEASURED_PITCH \
  mount_yaw_rad:=MEASURED_YAW
```

This makes the LIMO and later LOONAR rule identical: each platform supplies
only its measured `base_link -> tof_link` extrinsic; all downstream ToF logic
uses the same internal camera frames.

## ROS-only Four-wheel Differential simulation

`ros2/loonar_limo_sim` is the first hardware-independent validation target. It
does not involve cFS, the GCS, or `vehicle_gatewayd`; it validates the ROS
nodes that those systems will later connect to.

```text
/cmd_vel -> Gazebo differential kinematics -> /wheel/odom
                                             -> /imu
                                             -> EKF -> odom -> base_link

Gazebo depth sensor -> adapter -> /tof/depth/image_raw  (16UC1, millimetres)
                               -> /tof/depth/camera_info
                               -> /tof/depth/points
```

The static part of the frame tree deliberately matches the live DaBai tree:

```text
base_link -> tof_link -> tof_depth_frame -> tof_depth_optical_frame
```

The LIMO mount arguments `tof_x_m`, `tof_y_m`, and `tof_z_m` are **simulation
only**. They must be replaced independently after physical LIMO measurement;
the simulation defaults do not claim to be the real mount transform.

The default world is the supplied `arena_terrain_v04_resend_02.stl`, stored as
the Gazebo model `models/loonar_arena`. Its measured mesh bounds are `4.0 m ×
5.0 m` with a `0.64 m` vertical range. The simulated rover starts at `(1.5,
-2.0, 0.16)` because the mesh at the world origin is raised terrain and would
intersect the wheels. Use `world:=.../tof_test.world` only for a minimal flat
sensor diagnostic.

### Build and run on Ubuntu 22.04 / ROS 2 Humble

Install the simulation dependencies once on the development PC:

```bash
sudo apt update
sudo apt install -y ros-humble-gazebo-ros-pkgs ros-humble-gazebo-plugins \
  ros-humble-robot-localization ros-humble-xacro
```

Build only the LIMO ROS packages, because the repository root is a normal CMake
project rather than a ROS workspace package tree:

```bash
cd ~/loonar_ws
source /opt/ros/humble/setup.bash
colcon build --base-paths src/loonar/platforms/limo/ros2 \
  --packages-select loonar_limo_sim --symlink-install
source install/setup.bash
ros2 launch loonar_limo_sim limo_sim.launch.py
```

In separate terminals, validate the exact ROS contract before adding any
autonomy code:

```bash
ros2 topic echo --once /wheel/odom
ros2 topic echo --once /imu
ros2 topic echo --once /tof/depth/image_raw
ros2 topic echo --once /tof/depth/points
ros2 run tf2_ros tf2_echo odom tof_depth_optical_frame
```

For a deliberate manual simulation movement only:

```bash
ros2 topic pub --rate 10 /cmd_vel geometry_msgs/msg/Twist \
  '{linear: {x: 0.1}, angular: {z: 0.0}}'
```

The simulation now uses the official AgileX `limo_base.dae` and
`limo_wheel.dae` meshes, plus the vendor four-wheel-differential parameters:
base mass `2.1557 kg`, four `0.5 kg` wheels, wheelbase `0.20 m`, track
`0.13 m`, wheel radius `0.045 m`, and ROS 2 Gazebo two-wheel-pair drive
(`0.172 m` separation, `0.09 m` diameter, `20` maximum wheel torque).
The source/provenance and its upstream unlicensed-asset limitation are recorded
in `ros2/loonar_limo_sim/models/loonar_limo/MESH_SOURCE.md`. Do not use this
SIL to validate motor current or wheel-slip physics.
