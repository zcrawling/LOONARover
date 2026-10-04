# Pi RGB detector contract

The Pi camera owner sends 640x360 NV12 to the original H.264 encoder and a
bounded 10 fps BGR branch to `/run/loonar/vision.sock`. This ROS 2 node reads
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
