# Common direct-camera video sender

This is the shared LIMO and final Raspberry Pi video data plane. It opens the
camera directly without ROS, software-encodes H.264, wraps it in MPEG-TS, and
sends UDP to the ground station.

Both sources use the same profiles and downstream pipeline:

| Profile | Output | Bitrate |
| --- | --- | ---: |
| `low` | 640x360 @ 30 fps | 1 Mbit/s |
| `medium` | 1280x720 @ 30 fps | 3 Mbit/s |
| `high` | 1920x1080 @ 30 fps | 5 Mbit/s |

`VIDEO_SOURCE=libcamera` selects the final Pi camera. `VIDEO_SOURCE=v4l2`
selects a UVC/V4L2 camera such as the LIMO Orbbec-integrated RGB camera. The
V4L2 default input is MJPEG so USB 2.0 can sustain 30 fps before software H.264
encoding. A two-frame leaky queue bounds latency if encoding falls behind.
The libcamera path feeds NV12 directly to x264; it does not convert to I420.
V4L2 sources retain conversion to I420 for camera-format compatibility.
The UDP sink is clock-paced and requests a 2 MiB send buffer so encoded bursts
do not unnecessarily overflow the LAN socket.

For Pi installation and recording, use the
[Pi runbook](../../platforms/loonar/porting/ground_control_runbook.md).
The standalone sender defaults to `medium`; the Pi bench explicitly selects `low`.
`VIDEO_RECORD_PATH` enables local MPEG-TS recording after the shared encoder.
`VIDEO_STREAM_ENABLED=0` selects recording without UDP. Recording branches use
bounded queues and may drop data under load.

Receive without involving ROS:

```bash
ffplay -fflags nobuffer -flags low_delay -framedrop udp://@:5600
```
