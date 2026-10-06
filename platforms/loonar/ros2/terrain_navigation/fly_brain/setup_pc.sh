#!/usr/bin/env bash
set -euo pipefail
FLY_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$FLY_DIR"
python3 bootstrap.py
docker build -t loonar-fly-brain:783 "$FLY_DIR"
mkdir -p "$FLY_DIR/log" "$FLY_DIR/cache"
echo 'Setup complete. bash run_pc.sh starts whole-brain ROS inference in shadow mode.'
