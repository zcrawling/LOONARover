#!/usr/bin/env bash
# Run manually on the Pi. No firmware upload or motor motion commands.
set -euo pipefail

TOOLS_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export PYTHONPATH="$TOOLS_DIR${PYTHONPATH:+:$PYTHONPATH}"

usage() {
  cat <<'EOF'
Usage:
  bash test-teensy-usb.sh list
  bash test-teensy-usb.sh discover control /dev/serial/by-id/ACTUAL_DEVICE
  bash test-teensy-usb.sh discover payload /dev/serial/by-id/ACTUAL_DEVICE
  bash test-teensy-usb.sh health control [registry.json]

list:     USB/serial enumeration only; opens no serial port.
discover: HELLO only on the explicitly selected device; requires LNR2 firmware.
health:   Registered UID/role handshake and 5 seconds of health responses.
          Creates a new session and sends STOP on exit. No CONFIGURE/MOTION.
EOF
}

mode=${1:-list}
if [[ $mode == list ]]; then
  echo '=== USB devices ==='
  lsusb
  echo '=== Stable serial paths ==='
  shopt -s nullglob
  devices=(/dev/serial/by-id/*)
  if (( ${#devices[@]} == 0 )); then
    echo 'No /dev/serial/by-id entries. Check the USB data cable and firmware USB mode.'
    echo 'A Teensy in bootloader mode may appear in lsusb without a serial port.'
    exit 1
  fi
  for device in "${devices[@]}"; do
    printf '%s -> %s\n' "$device" "$(readlink -f -- "$device")"
    ls -lL -- "$device"
  done
  echo '=== Current user groups ==='
  id -nG
  echo 'Match each physical Teensy to its by-id path before discovery.'
  exit 0
fi

role=${2:-}
case "$mode:$role" in
  discover:control|discover:payload|health:control|health:payload) ;;
  *) usage; exit 2 ;;
esac

if systemctl is-active --quiet "loonar-mcu@$role.service"; then
  echo "Stop loonar-mcu@$role.service before opening its serial port." >&2
  exit 1
fi
python3 -c 'import serial' 2>/dev/null || {
  echo 'Missing pyserial. Install with: sudo apt install python3-serial' >&2
  exit 1
}

if [[ $mode == discover ]]; then
  device=${3:-}
  [[ $device == /dev/serial/by-id/* && -c $device ]] || {
    echo 'Select an existing /dev/serial/by-id/ path from the list output.' >&2
    exit 2
  }
  [[ -r $device && -w $device ]] || {
    echo 'Serial permission denied. Check dialout membership and log in again.' >&2
    exit 1
  }
  echo "HELLO only: role=$role device=$device"
  if ! python3 -m mcu_v2.inspect --role "$role" --discover-device "$device"; then
    echo 'No matching LNR2 reply: check role, selected device and installed firmware.' >&2
    echo 'USB enumeration alone does not require LNR2; do not flash automatically.' >&2
    exit 1
  fi
else
  registry=${3:-/etc/loonar/mcu-registry.json}
  [[ -r $registry ]] || {
    echo "Missing registry: $registry. Register actual MCU UIDs and paths first." >&2
    exit 2
  }
  python3 -m mcu_v2.inspect --role "$role" --registry "$registry" --seconds 5
fi
