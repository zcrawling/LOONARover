"""Best-effort status files, written off the serial/control thread."""
import json
import logging
import os
from pathlib import Path
import threading
import time


class StatusPublisher:
    def __init__(self, role, directory=None):
        self.path = Path(directory or f'/tmp/loonar-monitor-{os.getuid()}') / f'{role}.json'
        self.value = {'role': role, 'online': False,
                      'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True, name=f'{role}-monitor')

    def start(self):
        self.thread.start()
        return self

    def update(self, **values):
        self.value = dict(self.value, **values, updated_mono=time.monotonic(),
                          updated_ns=time.time_ns(), pid=os.getpid())

    def write(self):
        try:
            self.path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            temporary = self.path.with_suffix(f'.{os.getpid()}.tmp')
            temporary.write_text(json.dumps(self.value, allow_nan=False))
            temporary.chmod(0o644)  # Read-only telemetry, including root-owned services.
            temporary.replace(self.path)
        except (OSError, ValueError, TypeError):
            logging.debug('Monitor snapshot unavailable', exc_info=True)

    def run(self):
        while not self.stop.wait(1):
            self.write()
        self.write()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2)
