#!/usr/bin/env python3
"""Render selected IPv4 peers; never change interface addresses or DHCP."""
import argparse
import ipaddress
from pathlib import Path
import subprocess
import tempfile


def ipv4(value):
    return str(ipaddress.IPv4Address(value))


def render(gcs, observers=()):
    gcs = ipv4(gcs)
    destinations = list(dict.fromkeys([gcs, *(ipv4(x) for x in observers)]))
    template = Path(__file__).with_name('policy.nft').read_text()
    return template.replace('@GCS_IP@', gcs).replace('@STATUS_IPS@', ', '.join(destinations)), {
        'GROUND_STATION_IP': gcs,
        'LOONAR_STATUS_DESTINATIONS': ','.join(destinations),
    }


def update_env(path, values):
    path = Path(path)
    lines = path.read_text().splitlines() if path.exists() else []
    lines = [s for s in lines if s.split('=', 1)[0] not in {*values, 'ROS_LOCALHOST_ONLY'}]
    temporary = path.with_suffix('.tmp')
    temporary.write_text('\n'.join(lines + [f'{k}={v}' for k,v in values.items()]) + '\n')
    temporary.replace(path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gcs-ip', required=True, type=ipv4)
    p.add_argument('--status-ip', action='append', default=[], type=ipv4)
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--policy-only', action='store_true', help='Print nft rules without applying')
    a = p.parse_args()
    policy, values = render(a.gcs_ip, a.status_ip)
    if a.policy_only:
        print(policy)
        return
    if a.dry_run:
        print(policy)
        print('\n'.join(f'{k}={v}' for k,v in values.items()))
        return
    installed = Path('/usr/local/lib/loonar/network')
    installed.mkdir(parents=True, exist_ok=True)
    Path('/etc/loonar').mkdir(parents=True, exist_ok=True)
    exists = subprocess.run(['nft','list','table','inet','loonar_link_policy'], capture_output=True).returncode == 0
    with tempfile.NamedTemporaryFile(mode='w') as f:
        f.write(('delete table inet loonar_link_policy\n' if exists else '') + policy)
        f.flush()
        subprocess.run(['nft','--check','--file',f.name], check=True)
        subprocess.run(['nft','--file',f.name], check=True)
    (installed/'policy.nft').write_text(policy)
    update_env('/etc/loonar/network.env', values)
    update_env('/etc/loonar/video.env', {'GROUND_STATION_IP': a.gcs_ip})
    update_env('/etc/loonar/ros.env', {'ROS_DOMAIN_ID':'0', 'ROS_AUTOMATIC_DISCOVERY_RANGE':'LOCALHOST', 'ROS_STATIC_PEERS':a.gcs_ip})


if __name__ == '__main__':
    main()
