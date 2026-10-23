#!/usr/bin/env bash
# Application destinations and a receive-only, dual-recipient status service.
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'Run with sudo' >&2; exit 1; }
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
command -v nft >/dev/null
install -d /usr/local/lib/loonar/network /etc/loonar
python3 "$ROOT/platforms/loonar/tools/network/configure.py" "$@"
install -m755 "$ROOT/platforms/loonar/tools/network/apply.sh" /usr/local/lib/loonar/network/apply.sh
cat > /etc/systemd/system/loonar-link-policy.service <<'UNIT'
[Unit]
Description=LOONAR control PC and status receiver network policy
Before=loonar-status-broadcast.service
After=network-pre.target
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/lib/loonar/network/apply.sh
[Install]
WantedBy=multi-user.target
UNIT
cat > /etc/systemd/system/loonar-status-broadcast.service <<UNIT
[Unit]
Description=LOONAR receive-only status feed to selected PCs
After=network-online.target loonar-link-policy.service
Wants=network-online.target
[Service]
User=loonar
EnvironmentFile=/etc/loonar/network.env
ExecStart=/usr/bin/python3 $ROOT/platforms/loonar/tools/pi_status_broadcast.py
Restart=always
RestartSec=2
[Install]
WantedBy=multi-user.target
UNIT
# Installed cFS also reads the same selection on its next start.
install -d /etc/systemd/system/loonar-cfs.service.d
printf '[Service]\nEnvironmentFile=/etc/loonar/network.env\n' > /etc/systemd/system/loonar-cfs.service.d/network.conf
systemctl daemon-reload
systemctl enable --now loonar-link-policy.service
systemctl enable loonar-status-broadcast.service
systemctl restart loonar-status-broadcast.service
