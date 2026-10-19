"""Share the existing Pi hardware UDP feed between the web UI and status terminal.

Only one local reader owns UDP 6101. Other readers use its latest atomic cache;
SO_REUSEPORT would divide packets between readers instead of duplicating them.
"""
import json
import os
from pathlib import Path
import socket
import time

from backend.config import ROOT
from cli.status_udp import decode


class HardwareStatus:
    def __init__(self, host, bind='0.0.0.0', port=6101, cache=None):
        self.host, self.bind, self.port = host, bind, port
        self.cache = Path(cache) if cache else ROOT / '.runtime' / 'hardware-status.json'
        self.sock = None
        self.packet = None
        self.received = 0
        self.session = None
        self.sequence = 0
        self.gaps = 0
        self.next_bind = 0
        self.boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()

    def close(self):
        if self.sock:
            self.sock.close()
            self.sock = None

    def poll(self):
        now = time.monotonic()
        if self.sock is None and now >= self.next_bind:
            self.next_bind = now + 2
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.bind((self.bind, self.port))
                sock.setblocking(False)
                self.sock = sock
            except OSError:
                sock.close()
        updated = False
        if self.sock:
            for _ in range(64):
                try:
                    raw, peer = self.sock.recvfrom(32769)
                except BlockingIOError:
                    break
                except OSError:
                    self.close()
                    break
                try:
                    packet = decode(raw, peer, self.host)
                    if packet['kind'] != 'hardware':
                        continue
                    session = (packet.get('pi_boot_id'), packet.get('publisher_session'))
                    if session == self.session and packet['seq'] <= self.sequence:
                        continue
                    if session == self.session:
                        self.gaps += max(0, packet['seq'] - self.sequence - 1)
                    self.packet, self.received = packet, now
                    self.session, self.sequence = session, packet['seq']
                    updated = True
                except (ValueError, TypeError, KeyError, AttributeError):
                    continue
        if updated:
            self._save()
        elif self.packet is None or self.sock is None:
            self._load()
        return self.packet, now - self.received, self.gaps

    def snapshot(self):
        packet, age, _ = self.poll()
        return {'data': packet['data'] if packet and 0 <= age <= 4 else None,
                'age_s': round(age, 3) if packet else None,
                'sequence': packet['seq'] if packet else None}

    def _save(self):
        temporary = self.cache.with_suffix(f'.{os.getpid()}.tmp')
        try:
            self.cache.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps(dict(packet=self.packet, received=self.received,
                                                 boot=self.boot, gaps=self.gaps)))
            temporary.replace(self.cache)
        except OSError:
            pass  # Cache failure must never interrupt commands or UDP reception.
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def _load(self):
        try:
            cached = json.loads(self.cache.read_text())
            if cached['boot'] != self.boot:
                return
            packet = decode(json.dumps(cached['packet']).encode(), (self.host, 0), self.host)
            received = float(cached['received'])
            if packet['kind'] != 'hardware' or not 0 <= time.monotonic() - received <= 4:
                return
            self.packet, self.received, self.gaps = packet, received, int(cached['gaps'])
            self.sequence = packet['seq']
            self.session = (packet.get('pi_boot_id'), packet.get('publisher_session'))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            pass
