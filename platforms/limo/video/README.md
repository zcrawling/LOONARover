# LIMO direct camera stream

The inspected LIMO uses an Orbbec/Sonix RGB UVC camera alongside its depth
sensor. The RGB device is opened directly; ROS and the Astra depth driver are
not required for video streaming.

Verified hardware on `wego-NUC12WSKi7`:

- USB RGB device: `2bc5:050e`, serial `AU1SB3302CG`
- stable capture path:
  `/dev/v4l/by-id/usb-Sonix_Technology_Co.__Ltd._USB_2.0_Camera_AU1SB3302CG-video-index0`
- `video-index1` is UVC metadata and must not be used for capture
- MJPEG modes: 640x480, 1280x720 and 1920x1080 at 30 fps

The common sender uses MJPEG capture to avoid USB 2.0 raw-frame bandwidth, then
decodes and software-encodes H.264 exactly like the final Pi path. For the low
profile it centrally crops 640x480 to 640x360 instead of stretching it.

Required Ubuntu 22.04 packages:

```bash
sudo apt install v4l-utils gstreamer1.0-plugins-ugly gstreamer1.0-plugins-bad
```

Copy `video.env.example` to `/etc/loonar/video.env`, set the ground-station IP,
install the two files from `common/video/`, and start
`loonar-video.service`. Do not run `astra_camera` or another UVC consumer at the
same time because only one process can own this capture node.

## Live verification (2026-09-03)

All profiles were captured from the installed camera and received as H.264 over
the LIMO-to-development-PC Wi-Fi link:

| Profile | Negotiated stream | Approx. sender CPU | Max RSS |
| --- | --- | ---: | ---: |
| low | 640x360 @ 30 fps | 4% | 28 MB |
| medium | 1280x720 @ 30 fps | 5% | 48 MB |
| high | 1920x1080 @ 30 fps | 19% | 74 MB |

The installed service is enabled with `medium`, 3 Mbit/s, destination
`192.168.0.86:5600`. A received frame was decoded successfully at 1280x720.
CPU percentages are short six-second measurements and should be repeated under
the full rover workload before choosing the final operational profile.
