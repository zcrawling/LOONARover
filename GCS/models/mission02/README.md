# Temporary model seed for Pi deployment

`best.pt` is the COCO YOLO26n demonstration weight. The Pi installer copies
it to `/var/lib/loonar/vision/best.pt` only if that slot is empty. The GCS
viewer does not load this file. Replace the Pi slot with the validated
`target_rover`, `obstacle` model and restart `loonar-vision.service`.
