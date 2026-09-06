# Corrected wheel + IMU odometry: four new straight trials

Read-only analysis of `data/limo/odom_tests/20260905_16*/bag/*.db3` and the
user-entered `trial.yaml` measurements. Raw bags were copied from LIMO.
No control or odometry parameters were changed during this analysis.

## Distance

Distances below use magnitudes. Mean wheel travel is the mean signed MCU
left/right increment, then absolute value; final odometry distance is the
Euclidean displacement between first and last recorded filtered positions.
For these near-straight runs the quantities are comparable, but they are not
identical definitions for curved paths.

| Trial | Actual m | Mean wheel m | Filtered odom m | Odom minus actual cm | Relative error |
|---|---:|---:|---:|---:|---:|
| forward_1m_01 | 1.000 | 0.9965 | 0.996834 | -0.317 | -0.317% |
| reverse_1m_01 | 1.010 | 0.9965 | 0.996771 | -1.323 | -1.310% |
| forward_2m_01 | 2.000 | 1.9900 | 1.990248 | -0.975 | -0.488% |
| reverse_2m_01 | 2.010 | 1.9925 | 1.993299 | -1.670 | -0.831% |

All estimates slightly under-report measured distance. There is only one run
per condition, and the manual values are rounded to centimetres. Do not infer
a confirmed direction-dependent scale or fit a separate gain to each run.
Current results do not justify the earlier large reverse correction suggested
by the old 1.87 m run. Repeat measurements would establish whether a small
common distance scale is warranted.

## Heading

| Trial | Raw wheel yaw delta deg | Integrated IMU wz deg | Filtered yaw delta deg | IMU orientation delta deg |
|---|---:|---:|---:|---:|
| forward_1m_01 | 16.323 | 1.233 | 1.233 | 1.0 |
| reverse_1m_01 | 15.656 | 0.236 | 0.235 | 0.1 |
| forward_2m_01 | 33.311 | 3.269 | 3.267 | 2.3 |
| reverse_2m_01 | 32.312 | 1.667 | 1.667 | 0.2 |

The final EKF heading closely follows integrated IMU wz, confirming wheel yaw
is excluded. The raw wheel yaw is still unsuitable for heading estimation.
Forwards, right-wheel travel exceeds left-wheel travel; backwards, the left
wheel has greater travel magnitude. This cannot be justified as one constant
left/right radius ratio from these data alone.

The user entered zero final heading change for forward 1 m and both reverse
runs. The forward 2 m angle field contains `3cm 틀어짐`, which is lateral offset,
not a measured final yaw angle. It is not converted into yaw ground truth:
atan(offset/distance) describes a displacement bearing, not final heading.
Filtered forward-2m lateral displacement is approximately 5.1 cm, versus the
reported 3 cm offset (sign not specified).

Pre-motion IMU samples cover only about 0.93-0.96 seconds per trial. Their mean
wz is +0.000113 to +0.000291 rad/s and variance about 0.88e-6 to 1.21e-6
(rad/s)^2. These short samples do not establish a stable gyro calibration;
subtracting their means cannot explain away all observed heading drift.
IMU orientation is an onboard estimate, not independent angle ground truth.

## Timing and acquisition

- Encoder approximately 49.95 Hz; IMU approximately 99.90 Hz.
- No non-increasing sensor timestamps or sensor gaps greater than 1.5 times
  median period detected in these four bags. This is not proof against losses
  before the driver's timestamp assignment.
- Encoder maximum period 21.83 ms; IMU maximum period 11.82 ms.
- EKF approximately 50 Hz, occasional output intervals up to 30.84 ms.
- Bag receipt minus sensor message stamp median approximately 0.21-0.24 ms;
  filtered odometry approximately 5.94-6.68 ms. These are host pipeline timings,
  not calibrated physical sensor latency.
- All four command durations are within 0.3 ms of requested duration in the
  recorded stream, final zeros are present and no nonzero command follows them.
- Every trial completed and every recorder exited with code 0.

Conclusion: final distance estimates are within approximately 1.7 cm for these
four measured straight trials. The remaining prominent limitation is heading
accuracy and uncalibrated raw differential wheel yaw. Keep current distance
scale pending repeats; use 60-120 seconds of independently stationary IMU data
and measured rotations to establish bias and angular accuracy next.
