"""Launch the local direct-motion script on LIMO over SSH. Executing drives it."""
import argparse
import base64
import shlex
import subprocess
from loonar_apriltag.run_distance_test import ROOT,resolve_host
from loonar_apriltag.ssh_auth import authenticated


def main():
    p=argparse.ArgumentParser(description=__doc__)
    target=p.add_mutually_exclusive_group();target.add_argument('--ip');target.add_argument('--host')
    p.add_argument('--speed',type=float,required=True);p.add_argument('--angular',type=float,default=0.)
    p.add_argument('--duration',type=float,required=True)
    a=p.parse_args();host=resolve_host(a.host,a.ip)
    source=base64.b64encode((ROOT/'platforms/limo/tools/direct_motion.py').read_bytes()).decode()
    code=f'import base64;exec(compile(base64.b64decode({source!r}),"direct_motion.py","exec"))'
    command='source /opt/ros/humble/setup.bash && exec '+shlex.join(['python3','-u','-c',code,'--speed',str(a.speed),'--angular',str(a.angular),'--duration',str(a.duration)])
    print(f'Direct motion target: {host} (no camera or rosbag)',flush=True)
    try:raise SystemExit(subprocess.call(authenticated('ssh')+['-tt','-o','ConnectTimeout=5','-o','StrictHostKeyChecking=accept-new',host,'bash -c '+shlex.quote(command)]))
    except KeyboardInterrupt:raise SystemExit(130)

if __name__=='__main__':main()
