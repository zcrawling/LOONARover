#!/usr/bin/env bash
# Read-only recorder for the live LIMO EKF comparison.  This script never
# publishes a vehicle command.
set -eo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 OUTPUT.csv [--print-period SECONDS]" >&2
  exit 2
fi

source /opt/ros/humble/setup.bash
source "$HOME/loonar_ws/install/setup.bash"
exec python3 "$HOME/loonar_ws/src/loonar/platforms/limo/tools/odom_comparison_logger.py" \
  --output "$@"
