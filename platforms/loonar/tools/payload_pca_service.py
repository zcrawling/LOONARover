#!/usr/bin/env python3
"""Payload ASCII v1 USB owner, recorder and cFS socket bridge."""
import argparse
from collections import OrderedDict
import math
import os
import secrets
import selectors
import signal
import socket
import struct
import time
from pathlib import Path
try:
    import termios
    import fcntl
except ImportError:
    termios = None

COMMAND = struct.Struct("<QHH")
START, STOP = 1, 2
STATES = {"IDLE", "INITIALIZING", "STARTING", "MEASURING", "STOPPING"}

class Service:
    def __init__(self, socket_path, device, log_dir):
        self.socket_path = Path(socket_path)
        self.device = device
        self.log_dir = Path(log_dir)
        self.selector = selectors.DefaultSelector()
        self.clients = set()
        self.serial_fd = self.log_file = self.listener = None
        self.serial_buffer = bytearray()
        self.request_id = 0
        self.pending = {}  # MCU nonce -> (GCS request, operation, deadline)
        self.requests = OrderedDict()
        self.polls = {}
        self.next_poll = self.next_open = self.next_health = 0
        self.last_health = None
        self.health = None
        self.identity = None
        self.completed_station = None
        self.last_state_event = None
        self.result = None
        self.running = False
        self.active_station = None
        self.log_error = False

    def broadcast(self, text):
        payload = text.encode("ascii")
        if len(payload) > 127:
            payload = b"ERROR,0,TRANSPORT,event_too_long"
        for client in list(self.clients):
            try:
                if client.send(payload) != len(payload): self.drop(client)
            except OSError:
                self.drop(client)

    def drop(self, client):
        try: self.selector.unregister(client)
        except (KeyError, ValueError): pass
        self.clients.discard(client)
        client.close()

    def open_serial(self):
        fd = os.open(self.device, os.O_RDWR | os.O_NONBLOCK | os.O_NOCTTY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            attrs = termios.tcgetattr(fd)
            attrs[0] = attrs[0] & ~(termios.IGNBRK | termios.BRKINT | termios.PARMRK | termios.ISTRIP | termios.INLCR | termios.IGNCR | termios.ICRNL | termios.IXON)
            attrs[1] = attrs[1] & ~termios.OPOST
            attrs[2] = attrs[2] & ~(termios.CSIZE | termios.PARENB)
            attrs[2] = attrs[2] | termios.CS8 | termios.CLOCAL | termios.CREAD
            attrs[3] = attrs[3] & ~(termios.ECHO | termios.ECHONL | termios.ICANON | termios.ISIG | termios.IEXTEN)
            attrs[4] = termios.B115200
            attrs[5] = termios.B115200
            termios.tcsetattr(fd, termios.TCSANOW, attrs)
            self.selector.register(fd, selectors.EVENT_READ, "serial")
            self.serial_fd = fd
        except Exception:
            os.close(fd)
            raise

    def close_serial(self):
        if self.serial_fd is not None:
            self.selector.unregister(self.serial_fd)
            os.close(self.serial_fd)
            self.serial_fd = None

    def close_capture(self):
        if self.log_file:
            try: self.log_file.close()
            except OSError: pass
            self.log_file = None

    def open_capture(self):
        if self.log_file or self.log_error: return
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = (self.log_dir / f"payload-pca-{time.time_ns()}.csv").open("x", encoding="ascii")

    def record(self, line):
        if not self.log_file: return
        try:
            self.log_file.write(line + "\n")
            self.log_file.flush()
        except OSError:
            self.log_error = True
            self.close_capture()
            self.broadcast(f"ERROR,{self.request_id},RECORD,write_failed")

    def read_serial(self): return os.read(self.serial_fd, 4096)

    def send_serial(self, command):
        data = (command + "\n").encode("ascii")
        if os.write(self.serial_fd, data) != len(data): raise OSError("short_write")

    def online(self):
        return self.last_health is not None and time.monotonic()-self.last_health < 3

    def emit_health(self):
        h = self.health
        if h:
            age = min(4294967295, int((time.monotonic()-self.last_health)*1000)) if self.last_health else 4294967295
            self.broadcast(f"HEALTH,1,{int(self.online())},{h['boot']},{h['state']},{h['station']},{h['mask']},{age},{h['sample_age']},{h['seq']},{h['uid']}")
        else:
            self.broadcast("HEALTH,1,0,0,UNKNOWN,0,0,4294967295,4294967295,0,0000000000000000")

    def state_event(self, request, state, detail):
        event = f"STATE,{request},{state},{detail}"
        if event != self.last_state_event:
            self.broadcast(event)
            self.last_state_event = event

    def fail_capture(self, request_id, detail):
        self.broadcast(f"ERROR,{request_id},STATION,{detail}")
        self.state_event(request_id,"ERROR",detail)

    def disconnect(self, reason):
        for request, op, _ in self.pending.values():
            self.fail_capture(request, f"{op}:result_unknown")
            self.requests[request] = (op, f"ERROR,{request},{op},result_unknown")
        self.pending.clear()
        self.close_capture()
        self.close_serial()
        self.serial_buffer.clear()
        self.polls.clear()
        self.last_health = None
        self.next_open = time.monotonic()+1
        self.last_state_event = None
        self.emit_health()

    def issue(self, request, op):
        if request in self.requests:
            previous_op, previous_reply = self.requests[request]
            if previous_op != op: self.broadcast(f"ERROR,{request},COMMAND,request_conflict")
            else: self.broadcast(previous_reply)
            return
        if not self.online():
            self.broadcast(f"ERROR,{request},{op},mcu_offline"); return
        if op == "START" and (self.health['state'] != "IDLE" or self.pending):
            self.broadcast(f"ERROR,{request},START,busy"); return
        if op == "STOP" and any(item[1] == "STOP" for item in self.pending.values()):
            self.broadcast(f"ERROR,{request},STOP,busy"); return
        self.request_id = request
        if op == "START":
            self.log_error = False
            try: self.open_capture()
            except OSError:
                self.log_error = True
                self.broadcast(f"ERROR,{request},RECORD,open_failed")
        nonce = str(secrets.randbits(64))
        self.pending[nonce] = (request,op,time.monotonic()+20)
        reply = f"STATE,{request},{'STARTING' if op == 'START' else 'STOPPING'},requested"
        self.requests[request] = (op,reply)
        while len(self.requests)>64: self.requests.popitem(last=False)
        self.result = None
        try: self.send_serial(f"CMD,{nonce},{op}")
        except OSError:
            self.disconnect("write_failed"); return
        self.broadcast(reply)

    def start(self, request_id): self.issue(request_id,"START")
    def stop(self, request_id): self.issue(request_id,"STOP")

    def client_event(self, client):
        try: data = client.recv(256)
        except BlockingIOError: return
        except OSError: self.drop(client); return
        if not data: self.drop(client); return
        if len(data) != COMMAND.size:
            self.broadcast("ERROR,0,COMMAND,bad_length"); return
        request, opcode, length = COMMAND.unpack(data)
        if length or opcode not in (START,STOP):
            self.broadcast(f"ERROR,{request},COMMAND,bad_parameters"); return
        self.issue(request,"START" if opcode == START else "STOP")

    def parse_health(self, f):
        if len(f)!=12 or f[1]!='1' or f[2] not in self.polls: return
        if time.monotonic()-self.polls.pop(f[2])>3: return
        if len(f[3])!=16 or f[5] not in STATES or f[11]!='payload-1': raise ValueError("health_format")
        int(f[3],16)
        boot,station,uptime,mask,sample_age,seq = map(int,(f[4],f[6],f[7],f[8],f[9],f[10]))
        if not all(0<=x<=4294967295 for x in (boot,station,uptime,sample_age,seq)) or not 0<=mask<=7:
            raise ValueError("health_range")
        identity = (f[3],boot)
        first = self.last_health is None
        if self.identity is not None and identity!=self.identity:
            for request,op,_ in self.pending.values(): self.fail_capture(request,f"{op}:mcu_reboot")
            self.pending.clear(); self.close_capture(); self.result=None
            self.completed_station = None
            first = True
        self.identity = identity
        self.health=dict(uid=f[3],boot=boot,state=f[5],station=station,mask=mask,sample_age=sample_age,seq=seq)
        self.last_health=time.monotonic()
        self.running=f[5] in {"STARTING","MEASURING","STOPPING"}
        self.active_station=station if self.running else None
        if self.running:
            try: self.open_capture()
            except OSError:
                if not self.log_error: self.broadcast("ERROR,0,RECORD,open_failed")
                self.log_error=True
        if first or not self.pending:
            state={"MEASURING":"RUNNING","INITIALIZING":"STARTING"}.get(f[5],f[5])
            shown_station = self.completed_station if state == "IDLE" and self.completed_station else station
            self.state_event(self.request_id,state,f"station_{shown_station:02d}")
        if first:
            nonce=str(secrets.randbits(64))
            self.pending[nonce]=(0,"RESULT",time.monotonic()+3)
            self.result=None
            self.send_serial(f"CMD,{nonce},RESULT")
        self.emit_health()

    def parse_result(self, f):
        if len(f)!=16 or int(f[2])<1: raise ValueError("pca_fields")
        for x in f[2:8]:
            if not 0<=int(x)<=4294967295: raise ValueError("pca_integer")
        if f[7] not in ('0','1') or f[14] not in ('0','1'): raise ValueError("pca_flags")
        nums=[float(x) for x in f[8:14]]
        if any(math.isinf(x) for x in nums) or (f[7]=='1' and not all(math.isfinite(x) for x in nums)):
            raise ValueError("pca_numbers")
        if len(f[1])>32 or len(f[15])>24: raise ValueError("pca_text")
        # Fit bounded EVENT using scientific notation, never cut a record.
        summary=','.join(['PCA',f[2]]+[format(x,'.3g') for x in nums]+[f[14],f[15],f[1]])
        if len(summary)>127: raise ValueError("pca_event_too_long")
        self.result=(int(f[2]),summary)

    def handle_line(self, line):
        f=line.split(',')
        if f[0]=='HEALTH': self.parse_health(f); return
        if f[0]=='PCA':
            self.parse_result(f)
            if self.log_file is None and any(v[1] == 'RESULT' for v in self.pending.values()):
                try:
                    self.open_capture()
                    self.record(line)
                except OSError:
                    self.log_error = True
                    self.broadcast("ERROR,0,RECORD,recovery_write_failed")
            return
        if f[0] not in ('DONE','ERROR') or len(f)<3 or f[1] not in self.pending: return
        request,op,_=self.pending[f[1]]
        if f[0]=='ERROR':
            del self.pending[f[1]]
            if op=='RESULT' and f[2]=='no_result': return
            reply=f"ERROR,{request},{op},{f[2]}"
            self.requests[request]=(op,reply)
            self.broadcast(reply)
            return
        if len(f)!=4 or f[2]!=op: raise ValueError("done_mismatch")
        station=int(f[3])
        if op in ('STOP','RESULT') and station:
            if not self.result or self.result[0]!=station: raise ValueError("missing_pca")
            if op == "RESULT" and not self.running:
                self.completed_station = station
                self.state_event(self.request_id,"IDLE",f"station_{station:02d}")
            self.broadcast(self.result[1])
        del self.pending[f[1]]
        if op=='RESULT':
            if not self.running: self.close_capture()
            return
        state='RUNNING' if op=='START' else 'IDLE'
        reply=f"STATE,{request},{state},station_{station:02d}" + ('_complete' if op=='STOP' else '')
        self.requests[request]=(op,reply)
        self.broadcast(reply)
        self.running = op == 'START'
        if self.health: self.health['state'] = 'MEASURING' if self.running else 'IDLE'
        if op=='STOP':
            self.completed_station = station or None
            self.close_capture()

    def serial_event(self):
        try: data=self.read_serial()
        except BlockingIOError: return
        except OSError: self.disconnect("read_failed"); return
        if not data: self.disconnect("eof"); return
        self.serial_buffer.extend(data)
        if len(self.serial_buffer)>65536: self.disconnect("line_overflow"); return
        while b'\n' in self.serial_buffer:
            raw,_,remaining=self.serial_buffer.partition(b'\n'); self.serial_buffer=bytearray(remaining)
            if len(raw)>512: self.disconnect("line_overflow"); return
            try:
                line=raw.rstrip(b'\r').decode('ascii')
                self.record(line)
                self.handle_line(line)
            except (ValueError,UnicodeError):
                self.broadcast("ERROR,0,PROTOCOL,malformed_response")
            except OSError:
                self.disconnect("write_failed"); return

    def check_deadline(self):
        now=time.monotonic()
        if self.serial_fd is None and now>=self.next_open:
            self.next_open=now+1
            try: self.open_serial(); self.next_poll=0
            except OSError: pass
        if self.serial_fd is not None:
            if self.last_health is not None and now-self.last_health>=3:
                self.disconnect("health_timeout")
            elif now>=self.next_poll:
                nonce=str(secrets.randbits(64)); self.next_poll=now+1
                self.polls={k:v for k,v in self.polls.items() if now-v<3}
                self.polls[nonce]=now
                try: self.send_serial(f"STATUS,{nonce}")
                except OSError: self.disconnect("poll_failed")
        for nonce,(request,op,deadline) in list(self.pending.items()):
            if now>=deadline:
                del self.pending[nonce]
                self.fail_capture(request,f"{op}:result_unknown")
                self.requests[request]=(op,f"ERROR,{request},{op},result_unknown")
        if now>=self.next_health:
            self.next_health=now+1; self.emit_health()

    def run(self):
        self.socket_path.parent.mkdir(parents=True,exist_ok=True)
        # flock is released on exit; a second owner must not unlink a live socket.
        lock=open(str(self.socket_path)+'.lock','a')
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.socket_path.unlink(missing_ok=True)
        self.listener=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET)
        self.listener.bind(str(self.socket_path)); os.chmod(self.socket_path,0o660)
        self.listener.listen(4); self.listener.setblocking(False)
        self.selector.register(self.listener,selectors.EVENT_READ,'listen')
        try:
            while True:
                self.check_deadline()
                for key,_ in self.selector.select(.1):
                    if key.data=='listen':
                        client,_=self.listener.accept(); client.setblocking(False)
                        self.clients.add(client); self.selector.register(client,selectors.EVENT_READ,'client')
                        self.emit_health()
                    elif key.data=='client': self.client_event(key.fileobj)
                    else: self.serial_event()
        finally:
            self.close_capture(); self.close_serial()
            for client in list(self.clients): self.drop(client)
            self.listener.close(); self.selector.close()
            self.socket_path.unlink(missing_ok=True); lock.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--socket',default=os.getenv('PAYLOAD_PCA_SOCKET','/run/loonar/payload-pca.sock'))
    p.add_argument('--device',default=os.getenv('PAYLOAD_DEVICE'),required=os.getenv('PAYLOAD_DEVICE') is None)
    p.add_argument('--log-dir',default=os.getenv('PAYLOAD_LOG_DIR','/var/lib/loonar/payload'))
    args=p.parse_args()
    def shutdown(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, shutdown)
    try:
        Service(args.socket,args.device,args.log_dir).run()
    except KeyboardInterrupt:
        pass

if __name__=='__main__': main()
