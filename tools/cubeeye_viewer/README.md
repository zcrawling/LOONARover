# CubeEye I200DK desktop depth preview

ROS-independent hardware test on Ubuntu 26.04 x86_64, using the vendor's
Ubuntu 22.04 SDK v2.5.11. The SDK remains outside the repository.

```bash
bash tools/cubeeye_viewer/run.sh --auto-scale
```

The SDK default matches the downloaded release directory. Override with
`--sdk /path/to/release` or `CUBEEYE_SDK`. The launcher uses the existing
`.venv-apriltag` environment (NumPy and OpenCV), and `/usr/bin/g++` compiles
the acquisition helper into ignored `build/cubeeye_viewer/`.

The resizable window shows the full 640x480 depth frame, received FPS,
nonzero/non-65535 pixel fraction, and center 7x7 median. Depth is displayed in
native SDK U16 units pending a measured-target scale check; the displayed valid
fraction is only a sentinel-value check, not a confidence certification.
`--auto-scale` adjusts preview colors from the 2nd/98th percentiles. Without
it, `--max-depth 3000` sets a fixed color scale. Neither changes camera data.

- `S`: save the current lossless 16-bit depth PNG and colored preview.
- `Q`, Escape or closing the window: stop capture.
- `--seconds 15`: bounded acquisition test.
- `--headless --seconds 15`: acquisition without a window.

Outputs are local under `data/cubeeye/YYYYMMDD_HHMMSS/`: SDK log, last raw
depth PNG, preview and summary. They are ignored by Git. Snapshots are not
continuous recording and host receive rate is not a hardware exposure timestamp.

The USB camera needs read/write access. If missing, the viewer invokes the
system authentication dialog to grant the current user ACL access to exactly
the attached `3674:0200` device. This access expires on replug. No system-wide
permissions or camera settings are rewritten.

`capture.cpp` links only the vendor SDK and its bundled libraries. A dedicated
pipe carries depth to Python, avoiding the old SDK OpenCV/Python ABI in the GUI
process. The reader keeps only the newest frame. On this host SDK global teardown
hangs after camera stop/destroy, so the helper exits directly after explicit
camera cleanup. The parent also bounds shutdown if the SDK itself stalls.

Hardware acceptance: device I200DU2608000212, USB 5000M, actual 640x480 depth
received around 15 FPS. Calibration, depth units, distance accuracy and long-run
reliability have not yet been certified.
