"""GCS-owned terminal/brain lifecycle. No ROS imports in the GCS backend."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import uuid

HERE=Path(__file__).resolve().parent


class BrainTerminal:
    def __init__(self, event, runtime=None, host=None):
        self.event=event
        self.host=host or os.environ.get("LOONAR_ROVER_IP", "")
        self.runtime=Path(runtime or HERE/'log/gcs')
        self.session=None
        self.process=None
        self.container=None
        self.lock=asyncio.Lock()

    async def start(self):
        async with self.lock:
            if self.process is not None and self.process.returncode is None:return
            if not shutil.which('gnome-terminal'):
                raise RuntimeError('gnome-terminal is required for the fly brain window')
            self.runtime.mkdir(parents=True,exist_ok=True)
            self.session=self.runtime/uuid.uuid4().hex
            self.session.mkdir()
            self.container='loonar-gcs-fly-'+self.session.name[:12]
            (self.session/'owner.json').write_text(json.dumps({'pid':os.getpid(),'container':self.container,'host':self.host}))
            self.process=await asyncio.create_subprocess_exec('gnome-terminal','--wait','--title=LOONAR Fly Brain',
                '--',sys.executable,str(HERE/'gcs_pc.py'),'--terminal',str(self.session))
            self.event('Fly brain 시작 요청 — 새 터미널에서 준비 중')

    async def stop(self):
        async with self.lock:
            if self.session is None:return
            (self.session/'stop').touch()
            # Let the wrapper interrupt the process group and remove its container.
            deadline = asyncio.get_running_loop().time() + 3
            while not (self.session/'exited').exists() and asyncio.get_running_loop().time() < deadline:
                if self.process is not None and self.process.returncode is not None:
                    break
                await asyncio.sleep(.05)
            # Also cover a terminal crash. Only this session's container is touched.
            if self.container:
                p = None
                try:
                    p = await asyncio.create_subprocess_exec('docker','rm','-f',self.container,
                        stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
                    await asyncio.wait_for(p.wait(),1.5)
                except (OSError,asyncio.TimeoutError):
                    if p is not None and p.returncode is None:
                        p.kill()
                        await p.wait()
                    self.event('Fly brain 컨테이너 종료 확인 실패 — Docker 상태 확인 필요')
            self.event('Fly brain 종료' if (self.session/'exited').exists() else 'Fly brain 종료 요청')
            # Do not delete the marker: a late terminal launch must see STOP.
            self.process=None;self.session=None;self.container=None

    def exited(self):
        return self.process is not None and self.process.returncode is not None


def terminal(session):
    owner=json.loads((session/'owner.json').read_text())
    container=owner['container']
    stopped=False
    def stop(*_):
        nonlocal stopped
        stopped=True
    for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP):signal.signal(sig,stop)
    def cancelled():
        if stopped or (session/'stop').exists():return True
        try:os.kill(owner['pid'],0)
        except ProcessLookupError:return True
        return False
    child = None
    try:
        if cancelled():
            return
        env = dict(os.environ,LOONAR_FLY_CONTAINER=container,LOONAR_ROVER_IP=owner.get("host", ""))
        child = subprocess.Popen(['bash',str(HERE/'run_pc.sh'),'--drive'],env=env,start_new_session=True)
        while child.poll() is None and not cancelled():
            time.sleep(.1)
    finally:
        # Kill the producer of docker run before removing its container, so a
        # delayed bootstrap cannot create a new container after STOP.
        if child is not None and child.poll() is None:
            try:
                os.killpg(child.pid,signal.SIGINT)
            except ProcessLookupError:
                pass
            try:
                child.wait(timeout=.6)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(child.pid,signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait()
        try:
            subprocess.run(['docker','rm','-f',container],stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,timeout=2)
        except (OSError,subprocess.TimeoutExpired):
            pass
        (session/'exited').touch()


if __name__=='__main__':
    if len(sys.argv)!=3 or sys.argv[1]!='--terminal':raise SystemExit('internal terminal runner')
    terminal(Path(sys.argv[2]))
