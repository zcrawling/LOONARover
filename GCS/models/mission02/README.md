# GCS object detection model

The GCS camera viewer loads `best_ncnn_model/` on the PC CPU using
`GCS/.venv-vision/bin/python`. This is the trained two-class NCNN FP32 export:
`0: target_rover`, `1: obstacle`. The GUI displays `rover`, `obstacle`.
Real-field accuracy is unverified. Undetected objects are not automatically obstacles.
Keep `.param`, `.bin`, `metadata.yaml`, and `deployment.json` together when replacing
the model; the loader verifies artifact hashes and the mission class contract.
`best.pt` is the old COCO demonstration weight, retained but not loaded or used as fallback.

The Pi detector remains available through explicit `LOONAR_FLY_VISION=1`;
normal support launches do not start it or its BGR camera branch.
