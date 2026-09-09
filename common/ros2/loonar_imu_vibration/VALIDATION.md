# Local validation — 2026-09-08

Implementation is an independent experimental package. No controller, encoder
baseline, existing EKF configuration or terrain-map implementation was changed.
No rover motion command was sent. The LIMO SSH connection timed out; deployment
and on-rover runtime validation have not been performed.

## Software checks

Both `ros:jazzy-ros-base` and `ros:humble-ros-base` containers successfully built
the package with colcon and passed all 11 unittest cases. Containers used
`--network none`, `ROS_DOMAIN_ID=169`, `ROS_LOCALHOST_ONLY=1`, and
`LOONAR_ISOLATED_ROS_TEST=1`, isolating synthetic ROS traffic from the rover.

The integration case published synthetic IMU and wheel messages, loaded a
synthetic constant-C=0.5 model, observed vx=0.10 become 0.05, then stopped IMU
messages and observed fallback to vx=0.10. It checked covariance preservation,
the base frame, and absence of command, TF and corrected-pose topics.

The remaining tests cover known signal statistics, gravity/high-pass behavior,
future-sample exclusion, missing samples and clock reset, small denominators,
reverse/blocked labels, predictor bounds and support, split leakage, missing
GT, and synthetic train/validation/test causal integration without summing
overlapping windows. These checks establish software behavior, not real slip
prediction accuracy.

Reproduce inside either ROS image:

```bash
docker run --rm --network none -e ROS_LOCALHOST_ONLY=1 -e ROS_DOMAIN_ID=169 \
  -e LOONAR_ISOLATED_ROS_TEST=1 \
  -v /home/sb/LOONAR/common/ros2/loonar_imu_vibration:/src:ro \
  ros:jazzy-ros-base bash -lc '
source /opt/ros/$ROS_DISTRO/setup.bash
cd /tmp
colcon build --base-paths /src --packages-select loonar_imu_vibration &&
source install/setup.bash &&
python3 -m unittest discover -s /src/tests -v'
```

## Recorded data check and remaining evidence

The existing September 5 forward-2m bag exported 2,202 IMU and 1,101 wheel
messages. The default feature extractor produced 333 windows, all unlabeled.
Output is under `data/imu_vibration/forward_2m_20260905` and
`data/imu_vibration/features-only.json` in the repository workspace.
The absence of synchronized external GT correctly prevented label creation;
the final tape-measured distance was not converted into per-window truth.

The matching reverse-2m bag also exported successfully (2,201 IMU, 1,101 wheel,
389 command messages). Combined forward/reverse extraction produced 666
windows and zero labels in `data/imu_vibration/forward-reverse-features.json`.

These are LIMO stock-IMU logs, not BNO085 vibration measurements. No physical
model has been fitted or approved. Next evidence needed is synchronized
external longitudinal motion ground truth, repeated no-slip and simulant runs,
and independent held-out preparations. Test BNO085 report/filter bandwidth and
mounting separately; a model trained on LIMO is not assumed transferable.
