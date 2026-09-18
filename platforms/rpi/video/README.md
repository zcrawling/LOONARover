# Raspberry Pi 5 UDP video sender

The shared service in `common/video/` sends camera video directly to the
ground-station LAN address as H.264 in MPEG-TS over UDP. It is independent of
cFS, vehicle control and ROS. This platform directory only supplies the Pi
configuration.

Pi 5 has no hardware H.264 encoder.  The sender uses the official low-latency
software `libcamerasrc` + `x264enc` path with one encoder thread and a two-frame
leaky queue.  The camera module is not yet identified: run
`rpicam-hello --list-cameras`. Leave `LIBCAMERA_CAMERA_NAME` empty for the first
camera, or copy its exact libcamera name into that variable. A numeric index is
not passed as `camera-name` because that property expects a camera identifier.

| Profile | Resolution | FPS | Bitrate |
| --- | ---: | ---: | ---: |
| `low` | 640x360 | 30 | 1 Mbps |
| `medium` | 1280x720 | 30 | 3 Mbps |
| `high` | 1920x1080 | 30 | 5 Mbps |

Each profile requires deployment measurement of capture/encode FPS, actual
bitrate, frame age, CPU use and temperature.  A profile that cannot maintain
its FPS is reduced in resolution or FPS; no second camera pipeline is added.

Install `common/video/loonar-video-stream` at
`/usr/local/lib/loonar/loonar-video-stream`, install the common service at
`/etc/systemd/system/loonar-video.service`, copy this directory's example to
`/etc/loonar/video.env`, then
run `systemctl enable --now loonar-video.service`.  The ground station can view
the stream independently with `ffplay -fflags nobuffer -flags low_delay
-framedrop udp://@:5600`.
