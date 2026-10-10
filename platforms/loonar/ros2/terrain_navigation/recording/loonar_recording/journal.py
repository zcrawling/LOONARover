"""Append-only acquisition journal; enabled only by LOONAR_CAPTURE_SESSION.

Each producer owns its file. Records survive DDS discovery/loss and are imported
into the same MCAP. An incomplete final record is reported, never silently skipped.
"""
import json
import os
from pathlib import Path
import struct
import time

HEADER = struct.Struct('<IQ')
_handles = {}


def emit(source, event, data=b'', **fields):
    session = os.environ.get('LOONAR_CAPTURE_SESSION')
    if not session:
        return
    if source in ('mcu','gateway') and os.environ.get('LOONAR_CAPTURE_ASYNC_CONTROL') == '1':
        from .control_journal import emit as enqueue
        return enqueue(session,source,event,data,fields)
    key = (session, source, os.getpid())
    if key not in _handles:
        folder = Path(session) / 'raw'
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f'{source}-{os.getpid()}.journal'
        _handles[key] = (open(path, 'ab', buffering=0), 0)
    stream, seq = _handles[key]
    meta = dict(event=event, source=source, seq=seq+1, stamp_ns=time.time_ns(),
                monotonic_ns=time.monotonic_ns(), **fields)
    raw = json.dumps(meta, allow_nan=False, separators=(',', ':')).encode()
    block = HEADER.pack(len(raw), len(data)) + raw + data
    view = memoryview(block)
    while view:
        count = stream.write(view)
        if not count:
            raise OSError('journal write did not progress')
        view = view[count:]
    _handles[key] = (stream, seq+1)


class Reader:
    def __init__(self, path):
        self.path = Path(path)
        self.file = self.path.open('rb')
        self.offset = 0

    def read(self):
        self.file.seek(self.offset)
        head = self.file.read(HEADER.size)
        if len(head) < HEADER.size:
            return None
        nmeta, ndata = HEADER.unpack(head)
        if not 0 < nmeta <= 65536 or ndata > 64*1024*1024:
            raise ValueError(f'corrupt journal at {self.path}:{self.offset}')
        meta, data = self.file.read(nmeta), self.file.read(ndata)
        if len(meta) != nmeta or len(data) != ndata:
            return None
        self.offset = self.file.tell()
        return json.loads(meta), data

    @property
    def remaining(self):
        return self.path.stat().st_size - self.offset

    def close(self):
        self.file.close()
