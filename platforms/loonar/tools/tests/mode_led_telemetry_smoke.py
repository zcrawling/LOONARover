#!/usr/bin/env python3
"""Real cFS -> passive LED telemetry, using an isolated gateway with NO MCU backend.

Requires built cFS and host gateway. Does not start serial owners, ROS or motors.
Refuses to run if TCP 7443 is already occupied. The LED socket is a private test
socket, never the installed LED service. Run on either the development PC or Pi.
"""
import json
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[4]
CPU = ROOT/'build/gcs-test/cFS/build-native_std/exe/cpu1'
GATEWAY = Path(os.getenv('GATEWAY_TEST_BIN', str(ROOT/'build/gcs-test/host/common/vehicle_gateway/vehicle_gatewayd')))


def main():
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        probe.bind(('0.0.0.0',7443))
    module = ROOT/'build/gcs-test/cFS/build-native_std/native/default_cpu1/apps/loonar_ground_link/lnr_ground.so'
    shutil.copy2(module, CPU/'cf/lnr_ground.so')
    children=[]
    with tempfile.TemporaryDirectory(prefix='loonar-led-smoke-') as temp:
        work=Path(temp)
        led=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM)
        led.bind(str(work/'led.sock'));led.settimeout(.2)
        env=dict(os.environ,LOONAR_GATEWAY_SOCKET=str(work/'gateway/cfs.sock'),
                 LOONAR_PAYLOAD_PCA_SOCKET=str(work/'NO_PAYLOAD.sock'),
                 LOONAR_MCU_HEALTH_SOCKET=str(work/'NO_MCU.sock'),
                 LOONAR_LED_SOCKET=str(work/'led.sock'))
        logs=[]
        fake_backend = socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET)
        def start(name,command,cwd=None):
            log=(work/(name+'.log')).open('w');logs.append(log)
            child=subprocess.Popen(command,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT)
            children.append(child)
        def take(predicate):
            end=time.monotonic()+8
            latest=None
            while time.monotonic()<end:
                assert all(c.poll() is None for c in children), 'test process exited'
                try:latest=json.loads(led.recv(1024))
                except socket.timeout:continue
                if predicate(latest):return latest
            raise AssertionError(f'Telemetry timeout: {latest}')
        try:
            start('gateway',[str(GATEWAY),'--runtime-dir',str(work/'gateway')])
            for _ in range(100):
                try:
                    fake_backend.connect(str(work/'gateway/backend.sock'))
                    break
                except (FileNotFoundError,ConnectionRefusedError):
                    time.sleep(.05)
            fake_backend.sendall(struct.pack('<IHHI',0x4c4e5247,1,1,0))
            start('cfs',[str(CPU/'core-cpu1')],CPU)
            take(lambda s:not s['gcs_connected'] and s['mode']==3 and not s['explicit_stop'])
            with socket.create_connection(('127.0.0.1',7443),timeout=5) as client:
                # Fake backend consumes no serial port and has no actuators.
                for seq,(kind,data,mode) in enumerate([
                    (2,struct.pack('<dd',0.,0.),2),(3,b'',1),(1,b'',3),
                    (4,struct.pack('<QHH',100,1,0),4),
                    (5,struct.pack('<QHH',101,1,40)+struct.pack('<8H6I',1488,1500,25,50,25,50,800,2200,5000,10000,10000,10,3000,5000),5)],1):
                    client.sendall(struct.pack('<4sHHII',b'LNK1',1,kind,seq,len(data))+data)
                    state=take(lambda s:s['gcs_connected'] and s['mode']==mode and
                               (mode!=3 or s['explicit_stop']))
                    print('PASS',state)
            take(lambda s:not s['gcs_connected'])
            print('PASS GCS disconnect remains observable, with no LED/control peer connections')
        finally:
            for child in reversed(children):
                if child.poll() is None:
                    child.terminate()
                    try:child.wait(timeout=10)
                    except subprocess.TimeoutExpired:child.kill();child.wait()
            led.close()
            fake_backend.close()
            for log in logs:log.close()


if __name__=='__main__':main()
