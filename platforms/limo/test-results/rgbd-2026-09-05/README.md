# LIMO RGB-D deployment and first acquisition, 2026-09-05

Deployed `loonar_limo_rgbd_odom` to `wego@192.168.0.7:~/loonar_ws/src/loonar/platforms/limo/ros2/` and built successfully with ROS Humble. RTAB-Map was already installed. This deploy changes ROS software, not MCU firmware. No motion commands were transmitted and no EKF connection was added.

Recorded approximately 65 seconds without commanded motion. Physical stillness and scene stability were not independently confirmed, so position variation cannot yet be labelled stationary drift.

- Actual registered RGB/depth: both 640x480, `tof_color_optical_frame`; matching dimensions/frame alone do not establish geometric alignment accuracy.
- Recorded RGB 30.02 Hz, depth 28.99 Hz.
- RGB-D odometry 3.82 Hz, 246 messages; 146 tracking failures.
- 100 valid poses: endpoint displacement 0.644 m, maximum displacement from initial valid pose 0.828 m.
- Median reported estimation time 34.36 ms.
- Input diagnostics: 22 OK, 43 timestamp warnings out of 65. Probe compares latest messages, not actual synchronizer pairs; synchronization log also reports paired time differences above 10 ms.
- Driver reports unsupported property 2025 while setting up, then starts D2C hardware alignment and streams. Requested ROI does not produce the originally expected 640x400 output.
- Process lifetime-average snapshot on the Intel NUC: camera 34.4% CPU / 91 MiB RSS, probe 10.0% / 63 MiB, sync 5.9% / 146 MiB, odometry 13.6% / 163 MiB. CPU percentages are relative to one core; these are not Pi 5 measurements.
- Wheel/IMU/EKF/cmd_vel topics were requested for recording but had no active publishers and are absent from this bag.

Result: deployment and output confirmed, quality acceptance failed. Before driving, check physical scene and RGB/depth geometric alignment, trace actual synchronized timestamps and tracking failures, then repeat with independently confirmed stillness. Do not mask these results with EKF tuning.

Full raw bag retained on LIMO: `/home/wego/loonar_rgbd_test/baseline` (2.8 GiB). Local files contain summary, launch logs, recorder log and bag metadata. Camera and odometry test launches were stopped after collection; installed package remains available.

Subsequent rigid-floor calibration must establish encoder distance scale/asymmetry, effective wheel separation, IMU axes/sign/bias and timing before EKF covariance tuning, as specified in the handoff.
