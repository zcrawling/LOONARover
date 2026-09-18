#!/usr/bin/env bash
# Install software only; never opens a sensor or starts the rover stack.
set -euo pipefail
if [[ $EUID != 0 ]]; then
  echo "Run with sudo on the Ubuntu 24.04 ARM64 rover." >&2
  exit 2
fi
source /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $(dpkg --print-architecture) == arm64 ]] || {
  echo "Expected Ubuntu 24.04 arm64." >&2; exit 2;
}
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y software-properties-common ca-certificates curl python3 locales
add-apt-repository -y universe
locale-gen en_US.UTF-8
if ! dpkg-query -W -f='${Status}' ros2-apt-source 2>/dev/null | grep -q 'install ok installed'; then
  # Official ROS repository configuration package, not an unsigned apt source.
  release=$(curl -fsSL https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])')
  [[ $release =~ ^[0-9A-Za-z._+-]+$ ]] || exit 2
  download=$(mktemp -d)
  chmod 755 "$download"
  curl -fL "https://github.com/ros-infrastructure/ros-apt-source/releases/download/$release/ros2-apt-source_${release}.noble_all.deb" \
    -o "$download/ros2-apt-source.deb"
  chmod 644 "$download/ros2-apt-source.deb"
  apt-get install -y "$download/ros2-apt-source.deb"
fi
apt-get update
mapfile -t packages < <(sed '/^[[:space:]]*#/d; /^[[:space:]]*$/d' "$HERE/apt-packages.txt")
apt-get install -y "${packages[@]}"
echo "Dependencies installed. Rover/sensor services have not been started."
