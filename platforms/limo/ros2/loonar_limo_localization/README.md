# Physical LIMO wheel + IMU odometry

Run after sourcing ROS Humble, `~/agilex_ws/install/setup.bash`, and
`~/loonar_ws/install/setup.bash`:

```bash
ros2 launch loonar_limo_localization limo_imu_velocity_ekf.launch.py port_name:=ttylimo
```

`/odometry/filtered` uses encoder-derived forward speed from `/wheel/odom`
and yaw rate from `/imu`. The EKF is the sole `odom -> base_link` TF publisher.
`/wheel/odom` remains the independent raw wheel-kinematic comparison, including
its uncalibrated differential heading. Do not use that raw heading as the
corrected wheel + IMU estimate.

The 2026-09-05 correction disables wheel `wz` in the EKF input mask; it does
not change command velocities, gyro covariance, or encoder distance scale.
The earlier encoder-dominant profile combined two inconsistent yaw rates:
the first forward run's recorded EKF turned 24.1 degrees while integrating
the recorded gyro produced 3.2 degrees. The left curve produced 368.3 degrees
in the old EKF versus approximately 190.1 degrees from the gyro. Uncalibrated
left/right scales and effective track width make differential wheel yaw an
unsuitable heading input for this profile.

`tools/compare_ekf_replay.py` compares the old/new masks with identical saved
sensor messages in ROS domain 168 on loopback. It plays only wheel odometry,
IMU, and static TF: no `/cmd_vel` or base driver. The first straight replay
reduces estimated lateral travel from 0.423 m to 0.057 m and heading change
from 24.1 to 3.2 degrees. Its manual measurements are 0.033 m lateral offset
and 0.9 degrees, so this fixes the source inconsistency without claiming
that IMU bias/noise and geometry calibration are complete.

Distance remains based on the measured MCU wheel increments. The reverse
run reported 1.87 m actual travel versus 2.055 m mean wheel travel. A single
reverse measurement is insufficient to separate scale from slip or measurement
error; no direction-specific gain has been silently applied. Continue to
record measured distances and heading changes for repeated runs. Stationary
data are needed to establish gyro bias/variance before bias compensation.
