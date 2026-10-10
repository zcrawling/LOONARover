"""Separate disk writer for MCU/gateway: bounded memory enqueue on producers.

Only small control records use this path. Images retain their existing journal.
Overflow is counted and a missing final status is a recording integrity failure.
"""
import argparse
import atexit
import json
import os
from pathlib import Path
import signal
import socket
import struct
import queue
import threading
import time

HEADER = struct.Struct('<IQ')
clients = {}


class Client:
    def __init__(self, session, source):
        self.session, self.source = session, source
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.address = str(Path(session)/'control-journal.sock')
        self.sequence = self.dropped = 0
        self.sent = 0
        self.closed = False
        self.pending = queue.Queue(maxsize=4096)
        self.abort = threading.Event()
        self.socket.settimeout(.2)
        self.sender = threading.Thread(target=self.send_pending,daemon=True)
        self.sender.start()

    def send_pending(self):
        while not self.abort.is_set():
            try: packet=self.pending.get(timeout=.05)
            except queue.Empty: continue
            try:
                while not self.abort.is_set():
                    try:
                        self.socket.sendto(packet,self.address)
                        self.sent += 1
                        break
                    except OSError:
                        self.abort.wait(.01)
            finally:
                self.pending.task_done()

    def emit(self, event, data, fields):
        self.sequence += 1
        meta = dict(fields, source=self.source, event=event, seq=self.sequence,
                    producer_pid=os.getpid(), stamp_ns=time.time_ns(),
                    monotonic_ns=time.monotonic_ns(), journal_dropped=self.dropped)
        raw = json.dumps(meta,allow_nan=False,separators=(',',':')).encode()
        packet = HEADER.pack(len(raw),len(data))+raw+data
        try:
            self.pending.put_nowait(packet)
        except queue.Full:
            self.dropped += 1
            return False
        return True

    def close(self):
        if self.closed:
            return
        self.closed=True
        # Only on producer shutdown, after MCU STOP: drain the sender and send
        # final counts. The sender thread does IPC only; all disk IO is remote
        # in the writer process. The live control loop only does put_nowait.
        deadline=time.monotonic()+5
        while self.pending.unfinished_tasks and time.monotonic()<deadline:
            time.sleep(.01)
        self.abort.set(); self.sender.join(timeout=1)
        message=json.dumps(dict(source=self.source,producer_pid=os.getpid(),
            final=True,attempted=self.sequence,dropped=self.sequence-self.sent)).encode()
        self.socket.settimeout(2)
        try:
            self.socket.sendto(HEADER.pack(len(message),0)+message,self.address)
        except OSError:
            pass  # Writer's missing-final marker makes verification fail.
        self.socket.close()


def emit(session,source,event,data,fields):
    key=(session,source,os.getpid())
    if key not in clients:
        clients[key]=Client(session,source)
    return clients[key].emit(event,data,fields)


def close_clients():
    for client in clients.values():
        client.close()
    clients.clear()


atexit.register(close_clients)


def serve(session):
    sock=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,4*1024*1024)
    address=session/'control-journal.sock'
    sock.bind(str(address)); sock.settimeout(.2)
    streams,stats={},{}
    last_flush=time.monotonic()
    stopping=False
    def stop(*_):
        nonlocal stopping
        stopping=True
    for sig in (signal.SIGINT,signal.SIGTERM): signal.signal(sig,stop)
    (session/'control-journal.ready').touch()
    def save(name):
        path=session/'raw'/(name+'.transport.json')
        temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps(stats[name],indent=2)+'\n');temporary.replace(path)
    def flush_pending():
        nonlocal last_flush
        for stream in streams.values(): stream.flush()
        last_flush=time.monotonic()
    try:
        while True:
            if time.monotonic()-last_flush>=.1:
                flush_pending()
            try: packet=sock.recv(65536)
            except socket.timeout:
                flush_pending()
                if stopping: break
                continue
            if len(packet)<HEADER.size: raise ValueError('short control journal datagram')
            nmeta,ndata=HEADER.unpack_from(packet)
            if len(packet)!=HEADER.size+nmeta+ndata: raise ValueError('invalid control journal datagram length')
            meta=json.loads(packet[HEADER.size:HEADER.size+nmeta])
            source=meta['source']; pid=meta['producer_pid']
            if source not in ('mcu','gateway') or type(pid) is not int or pid<=0:
                raise ValueError('invalid control journal source')
            name=f'{source}-{pid}'
            if name not in stats:
                stats[name]=dict(received=0,dropped=0,closed=False,last_sequence=0)
                save(name)
            status=stats[name]
            if meta.get('final'):
                if name in streams: streams[name].flush()
                status.update(closed=True,attempted=meta['attempted'],dropped=meta['dropped'])
                save(name)
                continue
            if name not in streams: streams[name]=open(session/'raw'/(name+'.journal'),'ab',buffering=256*1024)
            streams[name].write(packet)
            # Bounded latency for the live importer; batching avoids per-record
            # system calls, while source metadata preserves acquisition time.
            if status['received']%64==0: streams[name].flush()
            status.update(received=status['received']+1,last_sequence=meta['seq'],dropped=meta['journal_dropped'])
            if status['received']%256==0: save(name)
    finally:
        for stream in streams.values(): stream.close()
        for name in stats: save(name)
        sock.close();address.unlink(missing_ok=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('session',type=Path)
    serve(parser.parse_args().session)
