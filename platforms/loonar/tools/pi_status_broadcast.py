#!/usr/bin/env python3
"""Pi local observations -> two UDP viewers. Never receives network commands."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import signal
import socket
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'GCS'))
from cli.pi_hardware_probe import collect

PORTS={'hardware':6101,'communication':6102}


def communication(hardware):
    components={'cFS':False,'Gateway':False,'Control backend':False,'Payload service':False}
    patterns={'cFS':b'core-cpu1','Gateway':b'vehicle_gatewayd',
              'Control backend':b'mcu_v2.backend','Payload service':b'payload_pca_service.py'}
    for proc in Path('/proc').glob('[0-9]*'):
        try:command=(proc/'cmdline').read_bytes().split(b'\0')
        except OSError:continue
        for key,pattern in patterns.items():
            if any(argument.rsplit(b'/',1)[-1] == pattern for argument in command):components[key]=True
    ground={}
    try:
        value=json.loads(Path('/run/loonar-led/status.json').read_text())
        boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        if value.get('boot_id')==boot and 0 <= time.monotonic()-value['updated_mono'] < 3:
            ground={key:value.get(key) for key in ('gcs_connected','mode')}
    except (OSError,ValueError,KeyError,TypeError):pass
    return dict(components=components,groundlink=ground,
                control=hardware.get('control',{}),payload=hardware.get('payload',{}))


class Broadcast:
    def __init__(self, destinations, ports=PORTS, source=None):
        self.destinations,self.ports,self.source=destinations,ports,source
        self.socket=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.socket.setblocking(False)
        self.boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        self.session=f'{self.boot}:{os.getpid()}:{time.time_ns()}'
        self.sequence=0
        self.dropped=0

    def emit(self,hardware,comm):
        self.sequence+=1
        for kind,data in [('hardware',hardware),('communication',comm)]:
            packet=dict(schema=1,kind=kind,source=self.source,seq=self.sequence,
                stamp_ns=time.time_ns(),pi_boot_id=self.boot,publisher_session=self.session,data=data)
            for host in self.destinations:
                try:
                    # Route lookup only; connect() on UDP sends no packet.
                    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as route:
                        route.connect((host,self.ports[kind]))
                        packet['source']=self.source or route.getsockname()[0]
                    raw=json.dumps(packet,allow_nan=False,separators=(',',':')).encode()
                    if len(raw)>32768:raise ValueError('status packet too large')
                    self.socket.sendto(raw,(host,self.ports[kind]))
                except OSError:self.dropped+=1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gcs-ip', action='append', type=ipaddress.IPv4Address,
                        help='Destination PC; repeat for additional status viewers')
    parser.add_argument('--source-ip', type=ipaddress.IPv4Address,
                        help='Packet source label; defaults to the selected route address')
    args=parser.parse_args()
    peers=args.gcs_ip or [ipaddress.IPv4Address(x) for x in os.environ.get('LOONAR_STATUS_DESTINATIONS','').split(',') if x]
    if not peers:parser.error('Specify --gcs-ip or LOONAR_STATUS_DESTINATIONS')
    sender=Broadcast(tuple(map(str,peers)),source=str(args.source_ip) if args.source_ip else None); stopped=False
    def stop(*_):
        nonlocal stopped
        stopped=True
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,stop)
    try:
        while not stopped:
            began=time.monotonic()
            try:
                hardware=collect();sender.emit(hardware,communication(hardware))
            except (OSError,ValueError) as error:
                print(f'status broadcast: {error}',file=sys.stderr,flush=True)
            time.sleep(max(.05,1-(time.monotonic()-began)))
    finally:sender.socket.close()

if __name__=='__main__':main()
