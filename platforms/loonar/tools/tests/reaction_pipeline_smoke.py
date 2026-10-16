#!/usr/bin/env python3
"""GCS -> real cFS/gateway -> fake MCU -> GCS status. NEVER opens USB."""
import asyncio
from collections import deque
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
ROOT=Path(__file__).resolve().parents[4]
sys.path[:0]=[str(ROOT/'GCS'),str(ROOT/'platforms/loonar/tools')]
from backend.real_app import RealState,GroundLinkConnection
from mcu_v2.reaction_gateway import ReactionController
from mcu_v2.reaction_wheel import Settings,STATUS
from mcu_v2.wire import Frame,Kind
from mcu_v2.link import Link
CPU=ROOT/'build/gcs-test/cFS/build-native_std/exe/cpu1'
GATEWAY=os.getenv('GATEWAY_TEST_BIN',str(ROOT/'build/gcs-test/host/common/vehicle_gateway/vehicle_gatewayd'))
HEADER=struct.Struct('<IHHI')

async def exercise(work,children):
    backend=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET);backend.setblocking(False)
    loop=asyncio.get_running_loop()
    for _ in range(100):
        try:await loop.sock_connect(backend,str(work/'gateway/backend.sock'));break
        except (FileNotFoundError,ConnectionRefusedError):await asyncio.sleep(.05)
    backend.send(HEADER.pack(0x4c4e5247,1,1,0))
    class FakeMCU:
        check_result=staticmethod(Link.check_result)
        def __init__(self):self.sent=[];self.frames=deque()
        def send(self,kind,payload=b''):
            self.sent.append((kind,payload));seq=len(self.sent)
            if kind in (Kind.REACTION_CONFIGURE,Kind.REACTION):
                self.frames.append(Frame(1,Kind.RESULT,sequence=seq,payload=struct.pack('<BBHI',kind,0,0,seq)))
                if kind==Kind.REACTION:
                    self.frames.append(Frame(1,Kind.REACTION_STATUS,payload=STATUS.pack(2,payload[0],1,0,1518,1500,0,1)))
            return seq
    fake=FakeMCU()
    def report(text):
        raw=text.encode();backend.send(HEADER.pack(0x4c4e5247,1,11,len(raw))+raw)
    controller=ReactionController(fake,report)
    async def receive_backend():
        while True:
            try:raw=await asyncio.wait_for(loop.sock_recv(backend,256),.01)
            except asyncio.TimeoutError:raw=b''
            if raw:
                _,_,kind,_=HEADER.unpack_from(raw)
                if kind==8:
                    controller.cancel();fake.send(Kind.STOP)
                elif kind==10:controller.request(raw[12:])
            while fake.frames:controller.receive(fake.frames.popleft())
            controller.tick()
    backend_task=asyncio.create_task(receive_backend())
    reader=writer=None
    for _ in range(120):
        try:reader,writer=await asyncio.open_connection('127.0.0.1',7443);break
        except OSError:await asyncio.sleep(.05)
    assert writer,'cFS did not open TCP'
    state=RealState('ISOLATED_FAKE_MCU');connection=GroundLinkConnection('127.0.0.1',7443,state)
    task=asyncio.create_task(connection.connected(reader,writer))
    async def wait_for(predicate):
        end=time.monotonic()+8
        while time.monotonic()<end:
            if predicate():return
            assert all(p.poll() is None for p in children),'child exited'
            await asyncio.sleep(.02)
        raise AssertionError(state.snapshot())
    try:
        await wait_for(lambda:state.connection=='CONNECTED')
        # Allow VehicleAdapter to connect before any command.
        await asyncio.sleep(.7)
        for command,side in [('REACTION_LEFT',1),('REACTION_RIGHT',2)]:
            result=await connection.command(command,reaction_settings={'left_first_offset':30})
            assert result['ok'],result
            await wait_for(lambda:controller.running)
            assert fake.sent[-1]==(Kind.REACTION,bytes([side]))
            configs=[data for kind,data in fake.sent if kind==Kind.REACTION_CONFIGURE]
            assert configs[-1]==Settings(left_first_offset=30).encode()
            await wait_for(lambda:state.reaction['state']=='FIRST')
            result=await connection.command('STOP' if side==1 else 'AUTO');assert result['ok']
            await wait_for(lambda:not controller.running)
            await wait_for(lambda:state.reaction['state']=='CANCELLED')
        # A GCS disconnect must cancel an active cycle through cFS.
        await connection.command('REACTION_LEFT')
        await wait_for(lambda:controller.running)
        await wait_for(lambda:state.mode=='REACTION')
        writer.close();await writer.wait_closed()
        await wait_for(lambda:not controller.running)
        print('REACTION_PIPELINE_OK: tuned LEFT/RIGHT, configure ACK before START, MCU status, STOP, GCS disconnect; NO USB')
    finally:
        task.cancel();backend_task.cancel()
        await asyncio.gather(task,backend_task,return_exceptions=True)
        writer.close();backend.close()

with socket.socket() as probe:probe.bind(('0.0.0.0',7443))
for app,filename in [('loonar_ground_link','lnr_ground.so'),('loonar_vehicle_adapter','lnr_vehicle.so')]:
    shutil.copy2(ROOT/f'build/gcs-test/cFS/build-native_std/native/default_cpu1/apps/{app}/{filename}',CPU/'cf'/filename)
with tempfile.TemporaryDirectory(prefix='loonar-reaction-test-') as tmp:
    work=Path(tmp);children=[];logs=[]
    env=dict(os.environ,LOONAR_GATEWAY_SOCKET=str(work/'gateway/cfs.sock'),
        LOONAR_PAYLOAD_PCA_SOCKET=str(work/'NO_PAYLOAD.sock'),
        LOONAR_MCU_HEALTH_SOCKET=str(work/'NO_MCU.sock'),LOONAR_LED_SOCKET=str(work/'NO_LED.sock'))
    try:
        for name,cmd,cwd in [('gateway',[GATEWAY,'--runtime-dir',str(work/'gateway')],None),('cfs',[str(CPU/'core-cpu1')],CPU)]:
            log=(work/(name+'.log')).open('w');logs.append(log)
            children.append(subprocess.Popen(cmd,cwd=cwd,env=env,stdout=log,stderr=log))
        asyncio.run(exercise(work,children))
    except Exception:
        for log in logs:log.flush()
        print((work/'cfs.log').read_text()[-1800:]);raise
    finally:
        for child in reversed(children):
            child.terminate()
            try:child.wait(timeout=10)
            except subprocess.TimeoutExpired:child.kill();child.wait()
        for log in logs:log.close()
