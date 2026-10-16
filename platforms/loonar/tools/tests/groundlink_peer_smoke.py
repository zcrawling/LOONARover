#!/usr/bin/env python3
"""Real cFS peer policy. No gateway, serial port, ROS or actuator commands."""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
ROOT=Path(__file__).resolve().parents[4]
CPU=ROOT/'build/gcs-test/cFS/build-native_std/exe/cpu1'
with socket.socket() as probe:
    probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    probe.bind(('0.0.0.0',7443))
shutil.copy2(ROOT/'build/gcs-test/cFS/build-native_std/native/default_cpu1/apps/loonar_ground_link/lnr_ground.so',CPU/'cf/lnr_ground.so')
with tempfile.TemporaryDirectory() as tmp:
    env=dict(os.environ,LOONAR_GATEWAY_SOCKET=tmp+'/NO_GATEWAY.sock',
             LOONAR_MCU_HEALTH_SOCKET=tmp+'/NO_MCU.sock',
             LOONAR_PAYLOAD_PCA_SOCKET=tmp+'/NO_PAYLOAD.sock',LOONAR_LED_SOCKET=tmp+'/NO_LED.sock')
    log=open(tmp+'/cfs.log','w')
    process=subprocess.Popen([str(CPU/'core-cpu1')],cwd=CPU,env=env,stdout=log,stderr=log)
    try:
        sock=None
        for _ in range(150):
            sock=socket.socket();sock.settimeout(2);sock.bind(('127.0.0.2',0))
            try:sock.connect(('127.0.0.1',7443));break
            except OSError:sock.close();time.sleep(.05)
        assert sock.recv(16)==b'', 'unapproved peer received telemetry'
        sock.close()
        with socket.create_connection(('127.0.0.1',7443),timeout=3) as approved:
            assert approved.recv(16).startswith(b'LNK1')
        print('GROUNDLINK_PEER_POLICY_OK: unauthorized peer rejected; loopback recorder accepted; NO COMMANDS')
    finally:
        process.terminate()
        try:process.wait(timeout=8)
        except subprocess.TimeoutExpired:process.kill();process.wait()
        log.close()
