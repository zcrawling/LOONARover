#!/usr/bin/env bash
# One PC command. Run setup_pc.sh once before first use.
set -euo pipefail
FLY_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ ${1:-} == --help ]]; then
  echo 'Usage: bash run_pc.sh [--drive] [--motivation-hz 0..150] [--step-ms 1..50]'
  echo 'ROS_DOMAIN_ID defaults to 0; set it to the same value as the Pi.'
  echo '--drive applies P9 tonic stimulation (150Hz); physical motion requires Pi --drive.'
  exit 0
fi
brain_args=()
for arg in "$@"; do
  if [[ $arg == --drive ]]; then
    brain_args+=(--motivation-hz 150)
  else
    brain_args+=("$arg")
  fi
done
python3 "$FLY_DIR/bootstrap.py"
docker image inspect loonar-fly-brain:783 >/dev/null 2>&1 || {
  echo 'Run bash setup_pc.sh first.' >&2; exit 1;
}
mkdir -p "$FLY_DIR/log" "$FLY_DIR/cache"
# Host networking is necessary for discovery with the physical Pi. Only small
# feature packets cross DDS; full depth images stay on the Pi.
exec docker run --rm --init --network host --name "${LOONAR_FLY_CONTAINER:-loonar-fly-brain}" \
  --user "$(id -u):$(id -g)" -e ROS_LOG_DIR=/fly/log/ros \
  -e ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}" -e ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST \
  -e ROS_STATIC_PEERS=10.254.254.3 \
  -v "$FLY_DIR:/fly" loonar-fly-brain:783 \
  bash -c 'source /opt/ros/jazzy/setup.bash; exec /opt/fly-env/bin/python -m loonar_fly.brain_node "$@"' bash "${brain_args[@]}"
