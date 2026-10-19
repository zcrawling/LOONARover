# Pi RGB detector contract

The Pi camera owner sends 640x360 NV12 to the original H.264 encoder and a
bounded 10 fps BGR branch to a shared-memory socket (`/run/loonar/vision.sock`
for systemd, a per-run temporary path for the manual GCS launcher). This node reads
that branch, rotates frames 90° counterclockwise and infers on portrait camera
content using the CPU. The model sees 360x640 source pixels letterboxed to its
configured input size; published boxes refer to the 360x640 portrait source.

`/vision/detections` and `/vision/target_cue` are `std_msgs/String` JSON
topics. The full detection packet also goes to GCS UDP 5601. It contains
`schema=1`, `sequence`, `state`, `direction`, portrait `width` and `height`,
`detections`, `model_mode`, short SHA-256 `model_id`, `processing_ms`,
`receive_time_unix_ns` and `timestamp_source=HOST_RECEIVE`. `processing_ms`
starts when this process receives the frame, not at camera exposure.

The currently seeded COCO model runs in `DEMO` mode; all its detections are
shown as obstacles. An exactly two-class `target_rover`, `obstacle` model runs
in `MISSION` mode. The direction is the highest-confidence target box's center
in the left, middle or right third of the portrait width. No motion command
or ToF input exists in this package.

The raw branch queue and detector appsink each hold at most one frame. A
slow detector cannot block H.264 video. It may skip camera frames, so actual
detection refresh rate and optical latency require Pi measurement.

## NCNN runtime and model replacement

Inference now requires a `*_ncnn_model` directory with `model.ncnn.param`,
`model.ncnn.bin`, and `metadata.yaml` (task=detect, batch=1, imgsz=[640,384]).
Ultralytics 8.4.145 and ncnn 1.0.20260526 are pinned. NCNN owns the inference;
the Ultralytics wrapper still uses CPU PyTorch for preprocessing/results.
`cpu_threads` controls the NCNN network before weights load; default is 2.
The source rotation, ROS/UDP contracts, confidence and stale policy are unchanged.

After pulling this package on the Pi, explicitly install a model:

```bash
# Public COCO demo, NOT trained target recognition:
sudo platforms/loonar/deploy/install-vision-runtime.sh GCS/models/mission02/best_ncnn_model
# Later: run the same command with your exported target_ncnn_model directory.
# Then start/restart the usual manual GCS stack:
bash platforms/loonar/tools/start-ground-support.sh
# Detector log: platforms/loonar/ros2/terrain_navigation/fly_brain/log/vision.log
```

The default no-argument launcher starts the camera branch and detector together
using the current checkout source. Do not also start the systemd camera services.
The explicit `start-ground-support.sh --video` bench path also starts detection;
its detector log is `~/loonar-motor-bench/runtime/vision.log`. Missing runtime,
model config or shmsink leaves video running; detector failure leaves control
running. `LOONAR_FLY_VISION=0` disables detection in either launcher.
Installed systemd deployments instead restart `loonar-vision.service` and read
`journalctl -u loonar-vision.service`. See the
[bring-up guide](../../../GCS/docs/mission02-object-detection.md) for both workflows.

The installer uses binary wheels only, rejects CUDA/TensorRT dependencies before
installation, validates/warmups the model, installs a content-addressed model
directory and updates only model_path/model_sha256 in `/etc/loonar/vision.yaml`.
PyTorch is pinned to the official CPU build 2.8.0+cpu with torchvision 0.23.0;
NumPy stays below 2 and OpenCV below 4.12 for the system ROS environment.
Ultralytics' Python-only `nvidia-ml-py` dependency is allowed; CUDA runtimes are not.
Other configured values are retained. The first config is backed up as
`vision.yaml.before-ncnn`. It never starts or restarts services. Without MODEL_DIR,
it installs/checks the runtime only and leaves the current model/config untouched.
An old config pointing to best.pt now reports MODEL_UNAVAILABLE; no silent fallback.
The package does not install Blender, PNNX, training tools, CUDA or TensorRT.
The launcher disables Ultralytics runtime package auto-installation.

Start logs identify NCNN/CPU, threads, model hash, DEMO/MISSION and actual FP16
options. FP32 exported weights do not imply all arithmetic runs in FP32.
`deployment.json` from the training repository records model provenance and
recommended confidence; installing a new model does not silently change confidence.

## Verification and remaining field work

Windows CPU verification used 12 portrait frames from the supplied indoor TS,
640x384 input, confidence .35, 2 threads, 3 warmups and 2 repeats. PyTorch mean
20.76 ms / p95 24.14 ms; NCNN mean 26.76 ms / p95 32.03 ms. Eight detections matched
with mean IoU 0.9999993. This checks conversion, not target accuracy or Pi speed;
NCNN was slower on this desktop. No Pi performance improvement is claimed yet.

On Pi, compare threads 1/2/3 with video and science collection for 30 minutes:
new results >=2Hz, optical capture-to-display p95 <=500ms; record CPU, RSS,
temperature, throttling, video/sensor losses. `processing_ms` is not optical age.
Existing video and GCS overlay tests must still pass. Missing/wrong-shape/hash
models must report MODEL_UNAVAILABLE; no camera/Gateway/ToF logic is changed.
Real target data is required for recall >=90% overall / >=80% per distance bin,
precision >=90%, and matched-target non-central left/right accuracy >=95%.
