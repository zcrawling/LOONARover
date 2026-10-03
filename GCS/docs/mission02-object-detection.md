# Mission 02: GCS RGB object detection

## Live input and display

```text
Pi Camera Module 3 Wide → existing H.264/MPEG-TS → UDP 5600
  → one GCS receiver → optional .ts recording → FFmpeg portrait decode
    ├─ newest frame → existing camera/compass window for driving
    └─ newest frame (one-slot queue) → YOLO worker → boxes and target cue
                                           └─ overlay in that same window
```

The supplied `camera-1790692539219661618.ts` stores H.264 at 640×360 and
30 fps. The GCS's existing counterclockwise 90° rotation makes its normal
preview 360×640. Detection sees those **same decoded portrait RGB pixels**;
its boxes use the 360×640 coordinate system. Other camera profiles are handled
using their decoded frame dimensions. The GCS does not open the Pi camera and
no second network video receiver is started. Recording remains the encoded
stream without rotation. ToF, ROS 2, the Gateway, and rover motion controls
are outside this detector path.

The video receiver and display never wait for inference. While the model is
busy, newly decoded frames replace the older pending inference frame. The
highest-confidence `target_rover` box gives LEFT/CENTER/RIGHT by dividing the
portrait frame width into thirds; obstacle boxes are displayed separately.
With no target, the cue is `미검출`. Boxes are hidden 500 ms after the GCS
received/decoded their source frame; then the window says `인식 갱신 지연`.
This timestamp is **not** the camera exposure time, so it does not establish
end-to-end optical latency.

## One-time GCS setup

Use the normal `bash scripts/start_loonar_gcs.sh` launcher. The default video
window runs `/usr/bin/python3`. Install `ultralytics` and its dependencies in
the Python environment used by that window. On Ubuntu, a dedicated venv can
reuse the existing system Tk/Pillow packages:

```bash
sudo apt install python3-venv python3-tk python3-pil python3-pil.imagetk ffmpeg
cd /path/to/LOONARover-main/GCS
python3 -m venv --system-site-packages .venv-vision
.venv-vision/bin/python -m pip install ultralytics==8.4.145
LOONAR_VIDEO_PYTHON="$PWD/.venv-vision/bin/python" bash scripts/start_loonar_gcs.sh
```

Set `LOONAR_VIDEO_PYTHON` in the launch environment for later sessions too.
The launcher checks Tk/Pillow and the vision worker reports any missing model
or runtime in the video status bar while the video and compass remain usable.
The model runs on the GCS CPU with 640-pixel YOLO input and confidence 0.35;
this does **not** square-crop the portrait display. Actual detection rate and
display latency must be measured on the team's laptop during simultaneous
video recording and driving.

## Install the temporary YOLO26n weight

The current `main` includes `GCS/models/mission02/yolo26n.pt`. Pull that
version on the GCS and restart the video window. `LOONAR_VISION_MODEL=/absolute/path/model.pt`
can override the slot. The model runs on the GCS and is not deployed to the
Pi or Payload Teensy. The GCS accepts the model's detection classes: `rover` or
`target_rover` is displayed as `target_rover` (class 0), and every other
detected class is displayed as `obstacle` (class 1). The generic COCO YOLO26n
model has no rover class, so it can demonstrate boxes for its supported
objects but cannot identify a rover. This mapping is for the demonstration;
it does not validate obstacle semantics or detection accuracy. The model
still runs on the GCS CPU, and its actual rate and latency must be measured.

For a recorded-stream input check without the rover, run from `GCS`:

```bash
ffmpeg -re -i /path/to/camera-1790692539219661618.ts -c:v copy -f mpegts \
  'udp://127.0.0.1:5600?pkt_size=1316'
```

Start `bash scripts/start_video.sh --compass --rotate-left` in a second
terminal first. The provided clip is an indoor format sample, not a labeled
target-rover or white-sand accuracy test set.
