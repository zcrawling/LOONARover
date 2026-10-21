"""Own AUTO-only process groups, including descendants of ros2 launch."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def sensor_commands(params_file):
    params = str(Path(params_file).resolve())
    return {
        'sensors': [
            'ros2', 'launch', 'loonar_bringup', 'terrain.launch.py',
            'params_file:=' + params, 'publish_tf:=true', 'run_base_io:=false',
            'run_adapter:=true', 'run_stationary:=true', 'run_safety:=true',
            'run_motion:=false', 'run_navigator:=false',
            'run_perception:=false', 'run_planner:=false',
        ],
        'terrain': [sys.executable, '-m', 'loonar_fly.terrain_node',
                    '--ros-args', '--params-file', params],
    }


class AutoProcesses:
    def __init__(self, sensors, log, stop_timeout=5.0):
        self.sensors = sensors
        self.log = log
        self.stop_timeout = stop_timeout
        self.children = {}
        self.stop_at = None
        self.failed = False
        self.failure = ''

    def rearm(self):
        self.failed = False
        self.failure = ''

    @staticmethod
    def signal_group(child, sig):
        try:
            os.killpg(child.pid, sig)
        except ProcessLookupError:
            pass

    def stop(self):
        if self.children and self.stop_at is None:
            self.stop_at = time.monotonic()
            # Stop motion first; sensor processes then close their SDK/USB handles.
            for name in ('driver', *self.sensors):
                if name in self.children:
                    self.signal_group(self.children[name], signal.SIGINT)
            self.log('AUTO processes stopping')

    def fail(self, reason):
        self.failed = True
        self.failure = reason
        self.log(reason)
        self.stop()

    def spawn(self, name, command):
        self.children[name] = subprocess.Popen(command, start_new_session=True)

    def tick(self, wanted, heading):
        if not wanted:
            self.stop()
        for name, child in list(self.children.items()):
            code = child.poll()
            if code is not None:
                # A crashed launcher can leave its SDK helper/ROS children behind.
                self.signal_group(child, signal.SIGKILL)
                del self.children[name]
                if self.stop_at is None:
                    self.fail(f'AUTO {name} exited ({code}); STOP then AUTO to retry')
        if self.stop_at is not None:
            if time.monotonic() - self.stop_at >= self.stop_timeout:
                for child in self.children.values():
                    self.signal_group(child, signal.SIGKILL)
            if not self.children:
                self.stop_at = None
                self.log('AUTO processes stopped')
            # Never start a new generation while old groups are shutting down.
            return
        if not wanted or self.failed:
            return
        try:
            for name, command in self.sensors.items():
                if name not in self.children:
                    self.spawn(name, command)
            if heading is not None and 'driver' not in self.children:
                self.spawn('driver', [
                    sys.executable, '-m', 'loonar_fly.drive_node',
                    '--external-mode', '--max-speed', '0.2',
                    '--heading-target', str(heading),
                ])
                self.log(f'GCS AUTO: fly started; heading={heading}')
        except OSError as error:
            self.fail(f'AUTO start failed: {error}')

    def close(self):
        self.stop()
        while self.children:
            self.tick(False, None)
            time.sleep(.02)
