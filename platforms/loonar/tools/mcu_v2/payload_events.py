"""Tail the durable Payload lifecycle journal without owning the USB port."""
import json
from pathlib import Path

TOPIC = '/payload/sequence_events'


class EventTail:
    def __init__(self, path):
        self.path = Path(path)
        self.offset = 0

    def read(self):
        try:
            stream = self.path.open('rb')
        except FileNotFoundError:
            return []
        events = []
        with stream:
            stream.seek(self.offset)
            for _ in range(100):
                line = stream.readline(65536)
                if not line.endswith(b'\n'):
                    break
                self.offset = stream.tell()
                meta = json.loads(line)
                if meta.get('schema') == 1 and type(meta.get('stamp_ns')) is int:
                    events.append(meta)
        return events
