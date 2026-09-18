# External AprilTag ground truth — straight runs

Fixed USB camera on this computer, **AprilTag 36h11 ID 0**, default black outer
edge **150 mm**. OpenCV supports this family directly. The standalone camera
commands only measure; the integrated distance test starts a remote ROS command
publisher. Default experiment speed is **0.05 m/s**.
At that speed 1 m takes nominally 20 seconds; actual travel is measured, not
inferred from duration. A single speed validates only that operating condition.

## Source layout

- `run_distance_test.sh`, `run_distance_test.py`, `gt.py`, `replay_tracking.py`:
  stable command-line entry points.
- `loonar_apriltag/`: implementation; relative imports inside the package.
- `tests/`: offline unit tests and an explicitly isolated ROS integration test.
- `../../config/cameras/c920_20260909_17mm.json`: measured default calibration.
- `../analysis/20260909/`: historical bag analysis source, separate from runtime.

Run local tests with `bash tools/apriltag_gt/test.sh` from the repository root.
The integrated test writes raw recordings and `c_windows.csv` / `c_analysis.json`
under `data/apriltag_gt/`. Default `--settle-seconds 2` excludes start/resume
transients from labels, while preserving raw data and the target distance.

## Integrated distance test (actually drives LIMO)

Hotspot / changing IP: connect laptop and LIMO to the hotspot, then obtain the
LIMO address from the hotspot device list or `hostname -I` on LIMO. Example
address below must be replaced with its actual address:

```bash
bash /home/sb/LOONAR/tools/apriltag_gt/run_distance_test.sh \
  --ip 172.20.10.2 --check-connection
bash /home/sb/LOONAR/tools/apriltag_gt/run_distance_test.sh --distance 1
```

The first command checks SSH only and saves the successful target in
`~/.config/loonar/rover-ssh.json`; it does not launch the camera, driver or motion.
Later runs reuse this target. `--ip` or `--host user@hostname` overrides it and
updates the saved value only after SSH succeeds. `--ip NEW_IP --distance 1`
also works directly and actually starts the experiment. The selected host is
printed before connection. The same host is used for commands and bag copying.
No subnet scanning or guess-based selection is performed. If the hotspot
isolates clients, SSH will still require enabling communication between them.
Where mDNS is supported, `--host wego-NUC12WSKi7.local` can avoid numeric IP
changes; availability depends on the hotspot and host configuration.

```bash
bash /home/sb/LOONAR/tools/apriltag_gt/run_distance_test.sh --distance 2
```

Defaults: forward 0.05 m/s, angular command zero, tag ID 0 / 150 mm, calibrated
C920 at calibration-file resolution, SSH `wego@192.168.0.7`. Authenticate when
prompted. Keep the camera fixed and rover stationary at startup. Once the tag
is detected, this command **automatically starts motion**. The tag-measured
distance terminates motion; 40 seconds is only nominal metadata for 2 m, not
the stopping criterion. Constant speed means braking/transport latency can
overshoot; final measured error is saved. No existing EKF/odometry is changed.

The host streams STOP at the target or on Ctrl+C. The current mount observed
on September 9 has rover forward along **tag +X**, so the integrated runner now
defaults to `--forward-axis x`. The standalone tracker defaults to +Y, matching
the printed FORWARD edge. Set `--forward-axis x|y|-x|-y` explicitly when moving
the printed tag; mounting orientation is not inferred from encoder odometry.

The tracking gate starts paused until 3 consecutive valid frames. Missing or
invalid measurements are tolerated for `--tracking-grace-s 0.3`, keeping the
current command during this interval (nominal 15 mm at 0.05 m/s, excluding
transport/braking delays). Set grace to zero for immediate pause. Longer loss
streams PAUSE (zero command, recording continues), and 3 consecutive valid
frames (`--recovery-frames`) resume unless already at the target.
`--tracking-timeout-s 5` ends a run that cannot recover; it does not wait forever.
These are experiment parameters, not vehicle-wide authority or watchdog rules.
Invalid frames never become ground-truth samples. Camera stream stalls also
pause and then terminate; grace does not manufacture missing positions.
The external runner starts
paused and handles these commands over stdin. Transient detection loss does not
terminate the run or reset the camera distance origin. The existing runner
publishes zero and finalizes rosbag at STOP. SSH stdin EOF also stops the runner when delivered; a severed or
hung network is not a guaranteed immediate stop. This is an attended experiment,
not a new vehicle authority/watchdog layer. Do not run a second motion publisher.

Results appear under `data/apriltag_gt/tag_<timestamp>/`: `camera/`,
`rover/` (automatically copied trial and rosbag), `rover.log`, and `test.json`.
If copying fails, the original remains on LIMO and its path is recorded.
The local runner sends its current motion-script source to the remote Python
process in memory, so this mode does not need a separately deployed script
update. Required ROS environment/workspace must already be installed on LIMO.

Arguments: `--distance`, optional `--speed`, `--camera`, `--calibration`,
`--tag-size`, `--tag-id`, `--host`, `--output`, `--time-offset-s`, `--no-preview`.
The zero time-offset default still needs measurement before vibration training.
Forward straight runs only; use a new recording for each trial.

Regression result (September 9): replay of all 815 frames from
`tag_20260909_161328_464446` yielded 809 valid +X samples, 6 invalid samples,
one short pause followed by recovery, no terminal tracking stop. +Y would yield
77 valid and 738 invalid samples. This validates the mounting-axis correction
on the recorded short movement, not accuracy over a full 1.5 m drive.
The replay command is `python replay_tracking.py CAPTURE_DIR --output report.json`.
Eight local tests plus the isolated Humble ROS test cover dropout grace,
consecutive-frame recovery, persistent loss, supervisor stdin delivery, and
actual zero/nonzero Twist publication across pause/resume/stop. Run the ROS
test only with network isolation and `LOONAR_ISOLATED_ROS_TEST=1`.

## Separate camera operations

Camera-only diagnosis (does not connect to LIMO or drive):

```bash
.venv-apriltag/bin/python tools/apriltag_gt/gt.py inspect \
  --camera /dev/v4l/by-id/usb-046d_HD_Pro_Webcam_C920_E4159DCF-video-index0 \
  --width 1920 --height 1080
```

Preview fits the whole image within 960x540 and is resizable. Detection,
recording and calibration use the original capture pixels; preview scaling does
not crop or alter intrinsics. Startup logs negotiated resolution/FPS and
focus/zoom controls where supported. Equal resolution alone does not establish
matching camera optics/crop/focus with another application. Keep the printed
20 mm white margin around all four sides of the tag: cutting to its black edge
against a dark chassis prevents separation of the outer quadrilateral. Tag
decoding itself does not use the calibration matrix; calibration errors affect
pose/distance after decoding. The inspector displays detected IDs and rejected
candidate counts to distinguish decoding from pose problems.

Python environment: `/home/sb/LOONAR/.venv-apriltag` (OpenCV contrib + NumPy).
On another computer: create a venv and pip-install `requirements.txt`.

```bash
cd /home/sb/LOONAR
.venv-apriltag/bin/python tools/apriltag_gt/gt.py print \
  --tag-id 0 --tag-size 0.15 --output tools/apriltag_gt/prints
```

Print `prints/tag36h11.svg` at **100% / actual size**, not fit-to-page. Measure
the black outer edge with a ruler and use the measured value for `--tag-size`.
Keep the white margin, glue onto a flat rigid surface on the rover top, and
point the printed **FORWARD** edge toward the rover front. Do not rotate the
tag relative to the rover between runs. Avoid glossy lamination.

`prints/checkerboard.svg` uses **9 by 6 inner corners**, 25 mm squares and fits
A4 landscape. Print at 100%, verify square size, mount flat.

## One-time intrinsic calibration per camera setup

```bash
cd /home/sb/LOONAR
.venv-apriltag/bin/python tools/apriltag_gt/gt.py calibrate \
  --camera /dev/video0 --width 1280 --height 720 --fps 30 \
  --cols 9 --rows 6 --square-size-mm 25 --output camera_calibration.json
```

Show the checkerboard at varied tilts, distances and positions, including image
edges. SPACE stores one detected view; collect at least 15 varied views, then
q computes calibration. It prints RMS and stores per-view residuals. View count
and square size are saved with the camera matrix and distortion coefficients.
`--square-size-mm` is the measured length of **one square**, e.g. `24.8` mm;
the older `--square-size 0.0248` metre input is also supported, but not together.
`--cols 9 --rows 6` counts inner corner intersections, not squares (the printed
board has 10 by 7 squares). Results include fx/fy/cx/cy in pixels and distortion
k1/k2/p1/p2/k3. The output JSON can be passed directly to `track --calibration`.
View count
alone is not a quality guarantee. Fix focus/zoom after calibration; changing
them invalidates it. The tracker refuses a resolution mismatch. Calibration
files cannot silently overwrite an existing file.

## Capture a straight forward/reverse run

Existing photographs can also be calibrated without opening the camera:

```bash
.venv-apriltag/bin/python tools/apriltag_gt/gt.py calibrate \
  --images /home/sb/Pictures/Camera --cols 9 --rows 6 \
  --square-size-mm 17.0 --output config/cameras/c920_20260909_17mm.json
```

All images must have the same resolution; at least 15 must have detected corners.
The JSON includes source filenames and each accepted image's residual.

Place the camera on a rigid mount above the whole test area; a slightly oblique
view can help single-tag pose ambiguity, while too oblique a view loses corner
accuracy. Keep the rover stationary when starting: the first accepted pose sets
the origin and forward axis. No floor marker is required at every distance.

```bash
cd /home/sb/LOONAR
.venv-apriltag/bin/python tools/apriltag_gt/gt.py track \
  --camera /dev/video0 --width 1280 --height 720 --fps 30 \
  --calibration camera_calibration.json \
  --tag-id 0 --tag-size 0.150 --nominal-speed 0.05 \
  --time-offset-s 0 --output data/apriltag_gt/forward_01
```

This command starts **camera recording only**. Start your existing rover logger
and motion test separately. q or Ctrl+C closes files; `--duration 35` stops the
camera automatically after 35 seconds, without stopping or driving the rover.
`--no-preview` supports an already calibrated headless capture.

Optional quality gates: `--max-reprojection-px 2 --max-rotation-deg 10
--max-lateral-m 0.1`. These are configurable measurement checks, not calibrated
mechanical limits or motion restrictions.

Outputs:

- `video.avi`: unannotated frames, for audit. AVI playback FPS is nominal;
  use `frames.csv` for actual frame times.
- `frames.csv`: every captured frame's timestamp, valid/invalid status, reason,
  camera XYZ, signed distance, reprojection residual and rotation change.
- `gt.csv`: accepted `t,s_m` rows for the vibration dataset.
- `capture.json`: camera, tag, threshold and time-offset settings; initially
  `verified_for_training=false`.

Distance is the projection of tag displacement on its initial forward axis,
so reverse displacement is negative and frame-to-frame position noise is not
integrated into accumulated path length. This measures longitudinal displacement
for **straight, nearly fixed-attitude runs**. It rejects large attitude/lateral
departures. It is not a curved-route or slope ground-truth system; tag/base
lever arm and full base orientation must be handled for those experiments.
Single-tag reprojection residual alone cannot guarantee metric accuracy.

## Required measurement checks before training

1. Record stationary data and inspect longitudinal jitter against the expected
   **50 mm per 1-second window** at 0.05 m/s. If noise is comparable, improve
   camera geometry/resolution/lighting/tag visibility before collecting training
   runs. No millimetre accuracy is promised without measurements.
2. Move the rover a measured 0.5 or 1 m both directions and compare camera
   displacement with the ruler, at several parts of the image. Check sign too.
3. Synchronize this computer and the LIMO sensor clock (e.g. the same NTP/chrony
   source). Camera timestamps here are host frame-receipt times, **not exposure
   hardware timestamps**. USB buffering adds delay even with synchronized clocks.
   `--time-offset-s` is the measured correction taking camera receipt time into
   the ROS sensor time domain, including camera delay. A camera delay of 0.08 s
   with otherwise matching clocks requires approximately **-0.08**, not +0.08.
   The example zero is only for preview or a verified negligible offset. Measure
   latency using an independently timed visible event (e.g. timestamped LED
   pulse); do not align traces by assuming encoder travel is true during slip.
4. Inspect invalid-frame intervals and outliers. The dataset rejects GT gaps
   beyond its configured limit (default 0.2 s); shorter gaps are interpolated.
   Use a tighter limit if even short interruptions are unacceptable. Camera
   movement invalidates the run. Retain raw video for verification.

Only after these checks, copy `gt.csv` beside an exported sensor run's
`records.jsonl` and `run.json`. In `run.json`, document `gt_kind: external`,
`gt_source` identifying this calibrated camera capture, and
`gt_time_offset_s: 0` **if the measured offset was already applied by this tool**.
Never apply the offset twice. Recording some stationary time before and after
the wheel experiment helps cover the whole evaluation interval. Do not label
unverified zero-offset captures as synchronized training truth.

## Validation

```bash
.venv-apriltag/bin/python -m unittest discover -s tools/apriltag_gt -v
```

Tests decode the actual generated SVG marker pattern and recover known metric
forward/reverse translations from synthetic camera projections. Camera
calibration, printing scale, capture timing and real measurement precision need
hardware validation with your camera and printed target.

Primary references:
- https://github.com/AprilRobotics/apriltag (36h11 for ArUco compatibility)
- https://docs.opencv.org/4.x/d5/dae/tutorial_aruco_detection.html
- https://docs.opencv.org/4.x/dc/dbb/tutorial_py_calibration.html
