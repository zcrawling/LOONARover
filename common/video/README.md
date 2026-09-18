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
The UDP sink is clock-paced and requests a 2 MiB send buffer so encoded bursts
do not unnecessarily overflow the LAN socket.

Install `loonar-video-stream` as
`/usr/local/lib/loonar/loonar-video-stream`, install `loonar-video.service` in
`/etc/systemd/system`, and provide the platform-specific
`/etc/loonar/video.env`.

Receive without involving ROS:

```bash
ffplay -fflags nobuffer -flags low_delay -framedrop udp://@:5600
```
