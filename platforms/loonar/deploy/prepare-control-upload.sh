#!/usr/bin/env bash
# User-run Pi setup. Installs USB upload tools; firmware is built on the PC.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
export PATH="$HOME/.local/bin:$PATH"
sudo apt-get update
sudo apt-get install -y build-essential cmake git pkg-config libudev-dev python3-serial
mkdir -p "$HOME/.local/src" "$HOME/.local/bin"
SOURCE="$HOME/.local/src/tytools-0.9.8"
if [[ ! -d $SOURCE ]]; then
  git clone --branch v0.9.8 --depth 1 --recurse-submodules https://github.com/Koromix/tytools.git "$SOURCE"
fi
cmake -S "$SOURCE" -B "$SOURCE/build" -DCMAKE_BUILD_TYPE=Release \
  -DCONFIG_TYCOMMANDER_BUILD=OFF -DCONFIG_TYUPLOADER_BUILD=OFF \
  -DBUILD_TESTS=OFF -DBUILD_EXAMPLES=OFF
cmake --build "$SOURCE/build" --target tycmd -j2
install -m755 "$SOURCE/build/tycmd" "$HOME/.local/bin/tycmd"
sudo install -m644 "$ROOT/platforms/loonar/deploy/99-loonar-usb.rules" /etc/udev/rules.d/99-loonar-usb.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hidraw
sudo usermod -aG dialout "$(id -un)"
echo 'Tools ready. Use PATH="$HOME/.local/bin:$PATH" in your upload shell.'
echo 'If dialout was newly added, log out of SSH and reconnect before uploading.'
