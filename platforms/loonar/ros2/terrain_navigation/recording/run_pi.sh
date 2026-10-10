#!/usr/bin/env bash
set -eo pipefail
RECORD_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ -f /etc/loonar/cpu-layout.json ]]; then
  sudo -n /usr/local/sbin/loonar-cpu-enter work "$BASHPID"
fi
source "$RECORD_DIR/../env.sh"
export PYTHONPATH="$RECORD_DIR:$RECORD_DIR/../../../tools${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m loonar_recording.session "$@"
