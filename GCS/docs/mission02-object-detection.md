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

The Pi model path is `/var/lib/loonar/vision/best.pt`. The deployment installer
copies the current COCO demo weight there only when the file is absent. This
weight can draw generic object boxes (`obstacle`) but cannot identify the
target rover. The status bar says `범용 모델 데모`. After training and field
validation, replace this **Pi file** with a two-class model whose class names
are `target_rover` and `obstacle`, then restart `loonar-vision.service`. The
status bar then says `목표 모델`; its boxes remain advisory.

```bash
# On the Pi, after validating the trained two-class checkpoint:
sudo install -o loonar -g loonar -m 644 /path/to/trained/best.pt /var/lib/loonar/vision/best.pt
sudo systemctl restart loonar-vision.service
```

The node accepts `/etc/loonar/vision.yaml` for confidence, input size, model
path and optional SHA-256 gate. Set `model_sha256` only if a pinned artifact is
desired; an empty value allows a weight swap at the same path. The GCS scales
portrait source-pixel boxes onto the shown frame and hides them when the known
processing plus GCS arrival age exceeds 500 ms. This is not a measured optical
capture-to-display delay, and rapid motion may misalign boxes.

## Bring-up and checks

Follow [Pi deployment](../../platforms/loonar/deploy/README.md), then on Pi:

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
Tk, Pillow and FFmpeg; any old `.venv-vision` is unused.

For a replay of the supplied `.ts` file, FFmpeg can send its video to UDP
5600, but Pi detection requires a live shared-memory branch or a separate
Pi-side replay harness. A video-only replay therefore shows `인식 갱신 지연`.

Measure Pi CPU and memory during video plus vision with `htop` or
`pidstat -u -r -p $(pgrep -f loonar_target_vision.node | head -n 1) 1`.
No FPS, latency, target accuracy, or Pi hardware result is claimed from code
tests alone.
