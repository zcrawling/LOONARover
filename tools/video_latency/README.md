# Pi camera video latency and resource benchmark

This tool runs a temporary instrumented version of the existing libcamera → x264 →
MPEG-TS → UDP pipeline on the Pi. It does not edit the installed video configuration
or start/stop the production service. Run only when the production camera service is
already stopped, and keep the receiver's separate UDP 15600 port free.

## Measurement contract

- Start: `CLOCK_REALTIME` sampled in a GStreamer pad probe at x264's input.
- End: the complete decoded, rotated, scaled PPM frame has been read on the laptop.
- Each frame carries magic, 64-bit microsecond timestamp, 16-bit sequence, CRC16 in
  black/white luma blocks. Invalid CRC frames are counted rather than used.
- This is **NOT camera-exposure-to-monitor latency**: sensor/ISP/source queue and
  physical display/Tk rendering are outside the timed interval.
- An SSH RPC clock calibration uses 25 four-timestamp exchanges before and after
  each case. The minimum residual round-trip sample estimates clock offset. Half
  the residual RTT bounds asymmetry uncertainty at the sampled instant; offsets are
  linearly interpolated across the case. Clock steps during a run require rejecting
  the result. This procedure does not make a physical end-to-end measurement exact.
- Local recording and the production decoder's rotation/scale/PPM filters are used.
  The Python/Tk live view is replaced by a continuously drained measurement reader.
- Process CPU ticks and resident memory are sampled every 0.5 seconds. 100% CPU
  means one logical core, so values may exceed 100%. Process RSS is not total OS RAM.
- First 3 seconds after the first valid frame are excluded from steady statistics;
  separate statistics retain these startup frames. Maximum means observed maximum,
  not a guarantee under every scene/network/load condition.

## Setup and run

Requires local FFmpeg, Python 3, sshpass; remote GCC and gstreamer-video development
headers. No credentials are written into the scripts or evidence directory.

```bash
read -rs -p 'Pi SSH password: ' SSHPASS; echo
export SSHPASS
sshpass -e ssh loonar@192.168.0.14 'mkdir -p /tmp/loonar-video-latency-20260926'
sshpass -e scp tools/video_latency/stamped_sender.c tools/video_latency/remote_agent.py \
  loonar@192.168.0.14:/tmp/loonar-video-latency-20260926/
sshpass -e ssh loonar@192.168.0.14 'cd /tmp/loonar-video-latency-20260926 && gcc -O2 -Wall -Wextra stamped_sender.c -o stamped_sender $(pkg-config --cflags --libs gstreamer-video-1.0)'
python3 -B tools/video_latency/run_pi_bench.py --seconds 33 --suffix _r1
python3 -B tools/video_latency/run_pi_bench.py --seconds 23 --suffix _r2 --reverse
python3 -B tools/video_latency/summarize.py
unset SSHPASS
```

The GCS destination defaults to 192.168.0.2; change with `--host`.
Names must be unique: existing evidence folders cause a refusal, not overwriting.
`--profiles low1_current,low1_lowdelay` selects cases.
The remote child is stopped when the agent's SSH stdin closes. If a run is interrupted,
verify no `stamped_sender` remains and UDP 15600 has been released.

Evidence: `output/video-latency-pi-20260926/`. `raw.json` retains all valid per-frame
samples, calibration exchanges and resource samples. `encode.csv` records Pi-side
encoder timing. `record.ts` preserves the received stream, including the timing bar.
`summary.json` is per run; `pooled.json` combines `_r*` repetitions per configuration.
