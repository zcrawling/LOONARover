# Mission 02: Raspberry Pi RGB detection

## Data path

```text
Camera Module 3 Wide (Pi, 640x360 at 30 fps)
  └─ one loonar-video-stream capture
       ├─ unchanged H.264 MPEG-TS → UDP 5600 → GCS portrait viewer
       └─ leaky one-frame branch → shared memory → Pi ROS 2 YOLO node
            └─ 90° counterclockwise, 360x640 detection coordinates
                 ├─ /vision/detections and /vision/target_cue (JSON String)
                 └─ UDP 5601 metadata → boxes/direction in that same GCS viewer
```

Video display never waits for the detector. The GCS does not run YOLO or need
Ultralytics, PyTorch, or CUDA. Recording stays in the original 640x360 encoded
format. ToF and motor commands are not part of this path.

The Pi reads a validated NCNN model directory named in `/etc/loonar/vision.yaml`.
The public COCO demo can draw generic object boxes (`obstacle`) but cannot
identify the target rover. The status bar says `범용 모델 데모`. After training
and field validation, install an exported NCNN model with exactly the classes
`target_rover`, `obstacle`. The status bar then says `목표 모델`; boxes remain advisory.

```bash
# One-time Pi setup, from the repository root (or use your trained NCNN folder):
sudo bash platforms/loonar/deploy/install-vision-runtime.sh GCS/models/mission02/best_ncnn_model
```

This installs the pinned CPU runtime and validates/copies the model, updating its
path and hash in the config. It does not launch a camera or service. `.pt` and
`.onnx` files are not accepted by the NCNN runtime. A git pull alone does not
install the Python runtime or deployed model. Training tools/CUDA are not needed.

The node accepts `/etc/loonar/vision.yaml` for confidence, input size, model
path and optional SHA-256 gate. Set `model_sha256` only if a pinned artifact is
desired; an empty value allows a weight swap at the same path. The GCS scales
portrait source-pixel boxes onto the shown frame and hides them when the known
processing plus GCS arrival age exceeds 500 ms. This is not a measured optical
capture-to-display delay, and rapid motion may misalign boxes.

## Bring-up and checks

### Normal checkout launcher

After the one-time runtime/model setup above, run the usual Pi command:

```bash
bash platforms/loonar/tools/start-ground-support.sh
```

The default GCS recording session now starts the existing NCNN node alongside
its single camera owner. The camera publishes video to GCS UDP 5600, recording
JPEG frames, and a separate 10 fps BGR shared-memory branch. Both camera and
detector use the same per-run socket under `$XDG_RUNTIME_DIR` (or `/tmp`), so no
root-owned `/run/loonar` directory is required. The detector waits up to 30 seconds
for camera startup. It uses the pulled Python source, without requiring another
colcon build for this pure Python package. The existing terrain workspace is
still required as before.

Check these logs from the repository root:

```bash
tail -n 60 platforms/loonar/ros2/terrain_navigation/fly_brain/log/vision.log
tail -n 40 platforms/loonar/ros2/terrain_navigation/fly_brain/log/camera.log
pgrep -af loonar_target_vision.node
```

`NCNN / CPU / ... threads=...` confirms model loading. `vision model unavailable`
reports missing/incompatible models or runtime versions. `Camera frame socket
unavailable` reports camera startup failure. Missing `shmsink` disables only the
recognition branch; camera/recording remain available. Detector exit is reported
in `~/loonar-motor-bench/runtime/sensors.log`, without stopping video or control.
The recording session copies `vision.log` into its `logs/` directory on exit.
Ctrl+C stops the detector with its camera and removes the per-run socket directory.

Restart the manual launcher after model installation. Do not simultaneously start
`loonar-video.service`/`loonar-vision.service`: those are an alternative camera
owner. `LOONAR_FLY_VISION=0` explicitly disables detection for comparison runs.
This automatic wiring applies to the no-argument GCS launcher; legacy explicit
bench options retain their existing separate startup procedure.

### Alternative installed systemd deployment

Follow [Pi deployment](../../platforms/loonar/deploy/README.md). With the manual
launcher stopped, the installed-service workflow remains:

```bash
sudo systemctl enable --now loonar-video.service loonar-vision.service
systemctl status loonar-video.service loonar-vision.service
journalctl -u loonar-vision.service -f
source /opt/ros/jazzy/setup.bash
source /opt/loonar/current/ros/install/setup.bash
ros2 topic echo /vision/target_cue
```

On the GCS, the existing `bash scripts/start_video.sh --compass --rotate-left`
receives UDP 5600 and 5601. Set `LOONAR_VISION_SENDER_IP` to the Pi's IPv4
address to accept detection packets only from that host. Allow inbound UDP
5601 through the GCS firewall. The camera/compass viewer needs only system
Tk, Pillow and FFmpeg. The launcher defaults to `/usr/bin/python3`; an old
`.venv-vision` is not selected automatically. `LOONAR_VIDEO_PYTHON` can override
the viewer's Python. Close the existing video window before changing it.

For a replay of the supplied `.ts` file, FFmpeg can send its video to UDP
5600, but Pi detection requires a live shared-memory branch or a separate
Pi-side replay harness. A video-only replay therefore shows `인식 갱신 지연`.

Measure Pi CPU and memory during video plus vision with `htop` or
`pidstat -u -r -p $(pgrep -f loonar_target_vision.node | head -n 1) 1`.
No FPS, latency, target accuracy, or Pi hardware result is claimed from code
tests alone.
