# GCS object detection model

`best.pt` is the COCO YOLO26n demonstration weight. The GCS camera viewer
loads it on the PC CPU using `GCS/.venv-vision/bin/python`.
Replace this file with a validated `target_rover`, `obstacle` model and
restart the viewer to use mission classes. The current generic model is
not trained to identify the mission rover.

The Pi detector remains available through explicit `LOONAR_FLY_VISION=1`;
normal support launches do not start it or its BGR camera branch.
