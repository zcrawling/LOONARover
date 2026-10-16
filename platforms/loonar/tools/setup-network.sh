#!/usr/bin/env bash
# Application destinations and a receive-only, dual-recipient status service.
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'Run with sudo' >&2; exit 1; }
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
command -v nft >/dev/null
install -d /usr/local/lib/loonar/network /etc/loonar
install -m644 "$ROOT/platforms/loonar/tools/network/policy.nft" /usr/local/lib/loonar/network/policy.nft
install -m755 "$ROOT/platforms/loonar/tools/network/apply.sh" /usr/local/lib/loonar/network/apply.sh
# Check the policy before changing runtime configuration.
/usr/local/lib/loonar/network/apply.sh
python3 - <<'PY'
from pathlib import Path
files={
 '/etc/loonar/video.env': {'GROUND_STATION_IP':'10.254.254.2'},
 '/etc/loonar/ros.env': {'ROS_DOMAIN_ID':'0','ROS_AUTOMATIC_DISCOVERY_RANGE':'LOCALHOST','ROS_STATIC_PEERS':'10.254.254.2'},
}
for filename,updates in files.items():
 p=Path(filename)
 lines=p.read_text().splitlines() if p.exists() else []
 lines=[s for s in lines if s.split('=',1)[0] not in {*updates,'ROS_LOCALHOST_ONLY'}]
 p.write_text('\n'.join(lines+[f'{key}={value}' for key,value in updates.items()])+'\n')
PY
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
Description=LOONAR receive-only status feed to 10.254.254.2 and 10.254.254.4
After=network-online.target loonar-link-policy.service
Wants=network-online.target
[Service]
User=loonar
ExecStart=/usr/bin/python3 $ROOT/platforms/loonar/tools/pi_status_broadcast.py
Restart=always
RestartSec=2
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now loonar-link-policy.service
systemctl enable loonar-status-broadcast.service
systemctl restart loonar-status-broadcast.service
