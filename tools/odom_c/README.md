# Local IMU / encoder → C_GT pipeline

Offline processing only. No ROS publisher, SSH, deployment, or runtime correction.

From `/home/sb/LOONAR`:

```bash
.venv-icp/bin/python tools/odom_c/pipeline.py --date 20260910 --window 1 --step 0.2
.venv-icp/bin/python tools/odom_c/analyze.py data/apriltag_gt/c_pipeline_20260910
.venv-icp/bin/python tools/odom_c/report.py data/apriltag_gt/c_pipeline_20260910
.venv-icp/bin/python -m unittest discover -s tools/odom_c -p 'test_*.py'
```

Dependencies: numpy, scipy, matplotlib, rosbags in the existing `.venv-icp`.
Ridge uses a weighted standardized least-squares implementation, tested against
synthetic known coefficients. No additional ML framework is required.

`pipeline.py --help` exposes window/step, label epsilon/range, camera quality,
clock-change guard, explicitly measured camera delay, speed bins, and evaluation
label tolerances. Quality thresholds are analysis settings, not physical limits.

## Data and timing

- Native ROS header timestamps for IMU and wheel measurements.
- Camera uses recorded host receipt time: **not exposure time**. The stored CLI
  camera offset is removed before applying measured laptop→rover clock conversion,
  so an offset is not applied twice. Pre/post clock values are interpolated.
- Motion-lag correlation is reported but never automatically applied: it mixes
  optical delay, body dynamics and slip. `--camera-delay` requires a separately
  measured value. Default zero means uncalibrated, not verified zero latency.
- Common 100 Hz CSVs include supporting native timestamps and validity masks.
  GT XYZ/progress are interpolated only across bounded gaps. Confidence fields
  use conservative endpoint bounds; unsupported confidence remains NaN.
- Left/right JointState cumulative positions are differenced at midpoint times.
  They are wheel-derived distance in metres; quantization affects acceleration.
- Encoder distance is the longitudinal velocity integral. GT distance is a
  within-window Huber line fit evaluated over identical t0/t1. No Euclidean
  pose distance, acceleration integration, or unreported moving-average delay.
- GT assumes a straight run along initial tag +X. Full tag-to-body lever-arm
  compensation is not available in the archived camera record.

## Labels and features

One row in `windows.csv` is a [t_end-window,t_end] pair. Overlapping windows are
not independent. Small encoder denominator is rejected, but moving wheels with
stationary body (C≈0) are allowed. Invalid/no-GT rows are never training labels.

Per model: 4 IMU features (az std, ax RMS, az kurtosis, gz RMS) plus 6 encoder
features (vx mean/std, left/right speed means, wz mean, acceleration RMS).
Raw and linear-detrended versions are compared separately. Other descriptive
IMU statistics are saved, not automatically added to the model. PSD is generated
from motion segments; no unsupported body/vibration cutoff is asserted.

## Terrain metadata

Copy `terrain_template.json` to a separate, user-maintained file and pass
`--terrain-metadata PATH`. Do not edit the generated template as the only copy.

```json
{
  "tag_RUN_ID": {
    "terrain_id": "unknown",
    "intervals": [
      {"start_ros": 100.0, "end_ros": 110.0, "terrain_id": "soil"}
    ]
  }
}
```

An explicit whole-run label is optional; segment labels allow terrain changes
within a run. Windows spanning a labelled boundary are `mixed`. Unknown is not
one homogeneous terrain. Terrain never enters the feature vector. The analysis
emits within-terrain and terrain+speed correlations when labels are present.

## Regression and evaluation policy

Run IDs partition the data, not the prediction inputs. Last 20% of sorted run
IDs are test, preceding 20% validation, remaining training (minimum one each;
requires at least five runs). This is fixed before scores. No random window split.
Scaling uses training data only. Run weights prevent longer recordings dominating
without averaging a run's features or C labels.

The currently declared exploratory training gate requires at least one of the
prespecified IMU features to have |speed-adjusted rank correlation| >= 0.3 in
training. This is a transparent screening heuristic, **not significance proof**.
If absent, Ridge fitting is withheld per the requested correlation-first policy.
Status files explain unavailable model/holdout/corrected-distance outputs.

When the gate passes: compare encoder-only/raw/detrended Ridge with alpha
0.1/1/10/100; choose alpha and feature set using validation only. Test metrics
include baseline C=1, train-constant C, C RMSE, provisional no-slip bias/slip
improvement, and distance errors. Nested whole-run holdouts are diagnostic.
No clipping is used to conceal bad predictions.

Distance accumulation uses disjoint accepted intervals; overlapping sliding
windows are never added repeatedly. Reported sums cover those intervals only,
not full-run final distance through missing GT. Physical no-slip/slip status and
terrain-generalization remain unverified until appropriate metadata/reference
measurements exist. No model is exported to rover runtime.
