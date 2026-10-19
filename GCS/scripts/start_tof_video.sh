#!/usr/bin/env bash
# Standalone depth viewer; no GCS/backend or camera process is started here.
set -euo pipefail
PORT=${1:-5602}
[[ $PORT =~ ^[0-9]{1,5}$ ]] && ((10#$PORT >= 1 && 10#$PORT <= 65535)) || {
  echo 'Usage: start_tof_video.sh [UDP_PORT]' >&2; exit 2;
}
command -v ffplay >/dev/null || { echo 'Install ffmpeg (ffplay required).' >&2; exit 127; }
echo "[LOONAR] ToF UDP $PORT; low-latency decoding; quit: Q / Esc"
# A single decoder thread avoids frame-thread queues. External clock and frame
# dropping prevent playback from retaining a backlog after network jitter.
exec ffplay -hide_banner -loglevel warning -window_title 'LOONAR ToF' \
  -an -threads 1 -fflags nobuffer -flags low_delay -framedrop -sync ext \
  -probesize 32 -analyzeduration 1 -max_delay 0 \
  "udp://@:$PORT?fifo_size=256&buffer_size=65536&overrun_nonfatal=1"
