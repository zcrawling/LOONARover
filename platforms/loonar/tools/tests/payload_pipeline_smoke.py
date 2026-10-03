#!/usr/bin/env python3
"""Real cFS -> Pi service -> emulated USB MCU -> real GroundLink decoder.
Run after tools/run_gcs_test.sh --build-only; no physical devices are opened.
"""
import os
from pathlib import Path
import pty
import select
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'GCS'))
from backend.real_app import RealState, GroundLinkConnection
from cli.groundlink_monitor import FrameParser
HEADER=struct.Struct('<4sHHII')


def main():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',7443))
    master,slave=pty.openpty()
    stopped=threading.Event()
    def mcu():
        buffer=b''; state='IDLE'
        while not stopped.is_set():
            if not select.select([master],[],[],.1)[0]: continue
            buffer+=os.read(master,4096)
            while b'\n' in buffer:
                raw,_,buffer=buffer.partition(b'\n')
                f=raw.decode().strip().split(',')
                if f[0]=='STATUS':
                    reply=f'HEALTH,1,{f[1]},0000000000000001,1,{state},1,1000,7,100,12,payload-1\n'
                elif f[0]=='CMD' and f[2]=='RESULT': reply=f'ERROR,{f[1]},no_result\n'
                elif f[0]=='CMD' and f[2]=='START':
                    state='MEASURING'; reply=f'ACK,{f[1]},START\nDONE,{f[1]},START,1\n'
                elif f[0]=='CMD' and f[2]=='STOP':
                    state='IDLE'
                    reply=f'ACK,{f[1]},STOP\nPCA,DEMO_ONLY_260927,1,1000,6000,10,10,1,34.0,27.0,28.0,0.1,0.2,0.3,0,DEMO_ONLY\nDONE,{f[1]},STOP,1\n'
                else: continue
                os.write(master,reply.encode())
    thread=threading.Thread(target=mcu); thread.start()
    children=[]
    try:
        with tempfile.TemporaryDirectory(prefix='payload-smoke-') as tmp:
            runtime=Path(tmp)
            with (runtime/'process.log').open('w') as log:
                service=subprocess.Popen([sys.executable,str(ROOT/'platforms/loonar/tools/payload_pca_service.py'),
                    '--device',os.ttyname(slave),'--socket',str(runtime/'payload.sock'),'--log-dir',str(runtime/'logs')],stdout=log,stderr=log)
                children.append(service)
                env=dict(os.environ,LOONAR_PAYLOAD_PCA_SOCKET=str(runtime/'payload.sock'))
                runner=subprocess.Popen([sys.executable,str(ROOT/'tools/gcs_test/run.py'),'--skip-build'],env=env,stdout=log,stderr=log)
                children.append(runner)
                deadline=time.monotonic()+15
                while True:
                    if runner.poll() is not None: raise AssertionError((runtime/'process.log').read_text())
                    try: tcp=socket.create_connection(('127.0.0.1',7443),timeout=.3); break
                    except OSError:
                        if time.monotonic()>deadline: raise AssertionError((runtime/'process.log').read_text())
                        time.sleep(.1)
                with tcp:
                    tcp.settimeout(5)
                    parser=FrameParser(); state=RealState('emulated'); state.connection='CONNECTED'
                    decoder=GroundLinkConnection('emulated',7443,state)
                    def until(predicate):
                        end=time.monotonic()+10
                        while time.monotonic()<end:
                            for kind,_,payload in parser.feed(tcp.recv(8192)):
                                decoder.handle(kind,payload)
                            if predicate(): return
                        raise AssertionError(state.snapshot())
                    until(lambda: state.values.get('Payload MCU 연결')=='ONLINE')
                    print('PASS MCU STATUS -> service -> cFS -> GCS ONLINE')
                    for opcode,wanted in ((1,'MEASURING'),(2,'IDLE')):
                        body=struct.pack('<QHH',100+opcode,opcode,0)
                        tcp.sendall(HEADER.pack(b'LNK1',1,4,opcode,len(body))+body)
                        until(lambda: state.payload['state']==wanted and
                              (opcode==1 or state.payload_sample is not None))
                        print(f'PASS opcode {opcode}: {wanted}')
                    assert state.payload_sample['values']['자기상센서']['value']==34
                    service.terminate(); service.wait(timeout=5)
                    until(lambda: state.values.get('Payload 서비스')=='OFFLINE')
                    assert state.values['Payload MCU 연결']=='OFFLINE'
                    print('PASS missing service -> cFS -> GCS OFFLINE')
                    assert any('PCA,' in p.read_text() for p in (runtime/'logs').glob('*.csv'))
                runner.terminate(); runner.wait(timeout=15)
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try: child.wait(timeout=15)
                except subprocess.TimeoutExpired: child.kill(); child.wait()
        stopped.set(); thread.join(timeout=2); os.close(master); os.close(slave)

if __name__=='__main__': main()
