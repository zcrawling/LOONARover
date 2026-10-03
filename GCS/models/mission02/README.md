# Mission 02 model slot

The video window loads `best.pt` by default. In the current `main`, that file
is a copy of `yolo26n.pt` for the temporary live demonstration. Replace only
`best.pt` with the validated two-class trained weight and restart the window.
Pull the same `main` on the GCS and restart the video window. A detected class named `rover` or
`target_rover` displays as `target_rover`; every other detected class displays
as `obstacle`. Generic COCO YOLO26n has no rover class, so its boxes display
as `obstacle`. The currently tracked `best.pt` has the same SHA-256 hash as
`yolo26n.pt`; it is not a separately trained rover/obstacle model.
