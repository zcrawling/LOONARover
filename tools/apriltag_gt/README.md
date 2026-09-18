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

SSH and scp use `sshpass -f ~/.config/loonar/ssh-password`. This machine's
password file is configured with mode 600; the password is not in the repository,
command arguments or trial metadata. The same file handles connection checks.

Defaults: forward 0.05 m/s, angular command zero, tag ID 0 / 150 mm, calibrated
C920 at calibration-file resolution, SSH `wego@192.168.0.7` unless a host is saved.
Keep the camera fixed and rover stationary at startup. Once the tag
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
PYTHONPATH=tools/apriltag_gt .venv-apriltag/bin/python -m unittest discover -s tools/apriltag_gt/tests -v
```

Tests decode the actual generated SVG marker pattern and recover known metric
forward/reverse translations from synthetic camera projections. Camera
calibration, printing scale, capture timing and real measurement precision need
hardware validation with your camera and printed target.

Primary references:
- https://github.com/AprilRobotics/apriltag (36h11 for ArUco compatibility)
- https://docs.opencv.org/4.x/d5/dae/tutorial_aruco_detection.html
- https://docs.opencv.org/4.x/dc/dbb/tutorial_py_calibration.html

## C920 tracking update (2026-09-10)

The existing command remains:

```bash
bash tools/apriltag_gt/run_distance_test.sh --speed 0.1 --distance 1
```

Tracking uses the native AprilTag 3 decoder through `pupil-apriltags`. It searches
at full calibration resolution (no image resizing or changed intrinsics), uses
an expanded tag ROI with full-frame reacquisition, and retries blurred images
with mild sharpening. Each measurement must decode the tag: at most one corrected
bit and decision margin at least 30. No optical-flow prediction or filled gaps
are written as measured GT. The existing pose/straight-run checks remain.

By default the integrated run enables autofocus while stationary, waits for one
second of valid detections with unchanged focus readback, then disables autofocus
before creating the distance origin or starting motion. `--focus N` explicitly
sets a fixed C920 focus control (0..250); `--focus-mode keep` leaves current focus
controls unchanged. Exposure is retained. The calibration photographs did not
record fixed focus, so this prevents focus changes within a run but does not
establish absolute calibration accuracy at the locked focus.

A capture thread continuously drains the camera, and processing consumes the
latest frame. Video and CSV still have matching processed frame indices; skipped
capture frames, receipt timestamps, decision margin, and bit corrections are
recorded explicitly. CSV timestamps, not AVI nominal FPS, define measurement time.

Offline replay of all CSV-indexed frames in the three available Sept 10 runs:

| Run | Original valid frames | Revised valid frames | Revised longest detection gap |
| --- | ---: | ---: | ---: |
| 16:18:51 | 173 / 264 | 260 / 264 | 0.089 s |
| 16:37:31 | 232 / 412 | 412 / 412 | 0 s |
| 16:42:19 | 167 / 341 | 341 / 341 | 0 s |

The original tracking gate produced no post-start PAUSE/STOP on these revised
replays with the current +X mount. Mean detector time was approximately 34, 8,
and 11 ms respectively; these are offline detector timings, not camera FPS.
Reproduce with `replay_tracking.py CAPTURE_DIR --output NEW_REPORT.json`;
`--detector legacy` selects the original OpenCV decoder. The native binding's
family cleanup ordering is handled locally to prevent an observed exit crash.
Hardware focus control, live capture rate, and full-distance physical accuracy
were **not** validated in this update because camera and rover were unavailable.

## 2026-09-14 primitive / ZUPT trial

```bash
bash tools/apriltag_gt/run_primitive_test.sh --dry-run
bash tools/apriltag_gt/run_primitive_test.sh
# Override saved hotspot address if necessary:
bash tools/apriltag_gt/run_primitive_test.sh --ip 172.20.10.12
```

The second/third commands **drive the rover**. Automatically starts the existing LIMO driver, wheel odom and EKF when the
stack is absent, and checks fresh sensor messages before opening the camera. A
partially running/duplicate stack is reported explicitly rather than duplicated. Do not separately launch another shadow DR: the trial
owns its isolated DR instance. The script uploads a temporary Python bundle without
replacing the installed stack. Existing password-file authentication and saved host
selection are reused. It checks remote ROS/SciPy dependencies before motion.

Sequence: forward .5m, left 30°, forward .5m, left 60°, forward .2m,
left 60°, forward .3m, left 30°, forward .5m. STOP is inserted before/after each
motion. Total forward distance 2.0m, total rotation 180°. All forward requests are
0.1m/s, turns default to 0.15rad/s (`--angular`). Each confirmed stationary state
is held another 2s (`--stop-hold`). Distance completion uses V1 DR and rotation uses
gyro yaw; these are not GT-guaranteed distances/angles. Ctrl+C sends STOP and
finalizes recording. No ToF correction is enabled.

Tag is horizontal, centred on rover, +Z up, configured tag axis aligned to rover
forward (existing mount default `--forward-axis x`). Camera must remain fixed with
all path locations in view. No straight-run rotation/lateral rejection is used.
Full camera-to-tag rotation and position are saved. Tag dropouts do not pause the
motion because camera is evaluation-only. Closing the camera program or Ctrl+C
cancels the trial; a hidden tag merely produces missing evaluation samples.

Output: `data/apriltag_gt/primitive_TIMESTAMP/`. Includes video, full-pose frames,
remote rosbag, command/transition events, estimator states, pre/post clock probes,
and automatic report.html / comparison.csv when GT overlap and clocks are valid.
Comparison aligns initial pose only, never scales trajectories. It assumes tag XY
centre coincides with base_link XY, +Z upward and fixed camera; mounting offset,
tilt and camera exposure delay remain limitations. No GT is interpolated through
missing video intervals. Missing comparison prerequisites preserve all raw files.

Re-run analysis with:

```bash
.venv-icp/bin/python tools/apriltag_gt/compare_primitive_test.py data/apriltag_gt/primitive_TIMESTAMP
```

The trial's ROS executor runs continuously on its own thread. The control loop
reads the latest estimator snapshot; it never throttles subscription processing
to a fixed number of callbacks per command cycle. The remote runner supports
`--observe-only-seconds N` for recording-load validation: it exercises STOP/intent
transitions but publishes no velocity commands, including zero commands. Trial
metadata records maximum feedback age, motion readiness and whether any command
was published. The 2026-09-14 real LIMO 20s recording probe reached STRAIGHT intent
without publishing motion; maximum feedback age was 0.02495s.

## Ramp C versus AprilTag (laptop + SSH)

On the laptop, pass the current LIMO IP explicitly; SSH user is always `wego`.
The existing local password-file authentication is reused.

```bash
bash tools/apriltag_gt/run_c_vision_test.sh --ip 192.168.0.7 \
  --speed 0.25 --ramp 2.5 --cruise 2 --decel 2.5 --stop 4
```

**This executes motion** after camera/tag and stationary-bias preparation. Use
`--dry-run` to print the profile without camera, SSH, or motion. Default nominal
commanded travel is 1.125 m; this is not a distance-limited controller.

The script uploads the current experimental Python modules into an isolated /tmp
bundle on LIMO, sources Humble/agilex_ws/loonar_ws, checks existing sensors, captures
C920 AprilTag frames locally, then runs the remote ramp and bag recorder. Installed
baseline code is not overwritten. V1 is started if absent; an already running V1
is retained. Camera observations are evaluation only: tag misses do not alter the
motion profile. Camera program exit or Ctrl+C requests remote cleanup. Remote stdin
EOF/STOP interrupts the owned motion process, whose finalizer sends zero velocity.

The code uses the LIMO `static_bias_experiment` acceleration mode; pitch changes
can contaminate C. This is not verified full gravity compensation.

Results are copied to `data/apriltag_gt/c_vision_<date_time>/`:

- `report.html`: C_acc vs C_GT on the exact acceleration window, C_dec vs C_GT on
  the exact deceleration-to-confirmed-STOP window; absolute/relative C differences.
- `c_comparison.csv`, `c_comparison.json`: window times, encoder/vision distances,
  raw estimated C, vision C and missing-data status.
- `evaluation/evaluation.json`: per-phase distance ratios and start-aligned errors
  for encoder-only, V1, existing EKF and `/odom_c_test`.
- `rover/estimate/samples.csv`, `windows.jsonl`, `rover/bag/`: original evidence.
- `camera/frames.csv`, `capture.json`, `test.json`: camera poses and pre/post SSH
  clock probes. Camera hardware exposure latency remains uncalibrated.

Recompute a copied run without hardware:

```bash
.venv-icp/bin/python tools/apriltag_gt/compare_c_test.py \
  data/apriltag_gt/c_vision_<date_time>
```

Do not interpret agreement from a single trial as slip-correction validation.
Unavailable tag endpoints yield N/A, not a predicted replacement. C_GT is signed
forward projection, not 3D terrain arc length. Existing C920 calibration, 15 cm
36h11 tag and forward axis x are defaults; override `--camera`, `--calibration`,
`--tag-size`, `--forward-axis`, `--focus`, or `--no-preview` if appropriate.

### 모래 slip 통합 시험 (laptop 실행)

```bash
bash tools/apriltag_gt/run_slip_test.sh --ip 172.20.10.12 --tof
```

`--tof`는 LIMO에 I200DK가 연결되어 있고 `~/cubeeye_sdk`가 설치되어 있을 때 사용한다.
센서 없이 실행할 때는 `--tof`만 생략한다. SSH 암호는 기존 ssh-password 설정을 사용한다.
노트북 AprilTag 카메라와 LIMO 센서 준비 후 실제 주행하므로 로버를 정지시킨 상태에서 실행한다.

기본 프로파일: STOP 4초 → 2.5초 가속 → 0.25 m/s 정속 1초 → 2.5초 감속 → STOP 4초.
명령상 거리 0.875 m이며 실제 거리 제한이나 AprilTag 거리 제어는 아니다. 변경 예:

```bash
bash tools/apriltag_gt/run_slip_test.sh --ip 172.20.10.12 --tof --speed 0.2 --ramp 2.5 --cruise 1 --decel 2.5 --stop 4
# SSH/카메라/주행 없이 인자 확인
bash tools/apriltag_gt/run_slip_test.sh --ip 172.20.10.12 --tof --dry-run
```

동일 bag에 `/wheel/odom`, `/odometry/filtered` (기존 EKF), `/localization/dr` (V1),
`/odom_c_test`, IMU, 명령, TF, stationary/monitor/C diagnostics를 기록한다.
`--tof` 사용 시 cloud, ToF 상태, ICP 판정, `/odom_tof_test`도 기록한다.
기존 EKF 및 V1 알고리즘/TF는 변경하지 않고 독립 test branch로 비교한다.
현재 C 실험은 일정 자세의 static-bias 가정이며 검증된 중력 보상은 아니다.
모래에서 pitch가 변하면 C가 오염될 수 있으므로 raw 값과 유효성 판정을 함께 본다.
ICP 거절 시 ToF odom은 V1 fallback이며 개선으로 해석하지 않는다.

AprilTag는 추정기 입력이 아니다. GT 원본은 **노트북 camera/frames.csv**에 따로 저장하고,
SSH 전후 시간 오프셋으로 ROS bag과 정렬한다 (카메라 노출 지연은 남음).
태그 누락만으로 주행을 멈추지 않으며 누락 구간은 GT 평가에서 제외한다.
종료 후 원격 bag을 복사하여 `report.html`, `comparison.csv`, `c_comparison.json`,
`icp_summary.json`을 생성한다. `--tof` 결과는 `data/apriltag_gt/slip_*/`,
생략 시 `data/apriltag_gt/c_vision_*/` 아래 저장한다.
ICP 적용 전후 위치 오차는 AprilTag가 관측된 시각에서만 비교한다.

### ㄷ자 primitive 시험

```bash
bash tools/apriltag_gt/run_primitive_test.sh --ip 172.20.10.12 --u-shape 0.9 0.7 0.9 --speed 0.1 --angular 0.15 --stop-hold 3
```

세 길이는 첫 직선/중간 직선/마지막 직선(m). 각 직선 사이 좌회전 90도,
각 직진 및 회전 후 confirmed STOP을 유지한다. 거리 종료는 V1 encoder translation,
각도 종료는 gyro yaw 피드백이므로 slip 시 실제 거리와 다르다.
AprilTag는 평가에만 사용한다. 카메라가 전체 ㄷ자 경로를 볼 수 있게 배치한다.
기존 encoder/EKF/V1 및 센서·진단 bag과 카메라 기록을 저장하고 비교 보고서를 만든다.
이 primitive runner는 C ramp 시험이나 ToF bridge를 자동 실행하지 않는다.
`--u-shape` 생략 시 기존 5단계 경로를 유지한다. `--dry-run`은 주행/SSH 없이 경로만 출력한다.
