#!/usr/bin/env python3
"""End-to-end test against real cFS; build with run_gcs_test.sh --build-only first."""
import os
from pathlib import Path
import select
import socket
import struct
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
HEADER = struct.Struct('<4sHHII')


def frame(sock):
    def exact(size):
        result = b''
        while len(result) < size:
            part = sock.recv(size - len(result))
            assert part, 'unexpected disconnect'
            result += part
        return result
    magic, version, kind, seq, size = HEADER.unpack(exact(16))
    assert magic == b'LNK1' and version == 1 and size <= 512
    return kind, seq, exact(size)


def main():
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.bind(('127.0.0.1', 0))
    udp.settimeout(5)
    video_port = udp.getsockname()[1]
    runner = subprocess.Popen([str(ROOT / 'tools/run_gcs_test.sh'), '--skip-build',
                               '--gcs-ip', '127.0.0.1', '--video', 'test',
                               '--video-port', str(video_port)], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT)
    try:
        output = b''
        deadline = time.monotonic() + 40
        while b'Ctrl+C stops all test processes.' not in output:
            assert time.monotonic() < deadline, output.decode()
            assert runner.poll() is None, output.decode()
            if select.select([runner.stdout], [], [], .2)[0]:
                output += os.read(runner.stdout.fileno(), 4096)
        print(output.decode())
        with socket.create_connection(('127.0.0.1', 7443), timeout=5) as tcp:
            # One connection sends all five commands and explicit final STOP.
            commands = [(1, b'', 3, 0), (2, struct.pack('<dd', .25, -.1), 2, 0),
                        (3, b'', 1, 0), (4, struct.pack('<QHH', 100, 0, 0), 4, 0),
                        (5, struct.pack('<QHH', 101, 0, 0), 5, 3), (1, b'', 3, 0)]
            for seq, (kind, payload, mode, result) in enumerate(commands, 1):
                raw = HEADER.pack(b'LNK1', 1, kind, seq, len(payload)) + payload
                # Exercise TCP header fragmentation too.
                tcp.sendall(raw[:7])
                tcp.sendall(raw[7:])
                deadline = time.monotonic() + 5
                while True:
                    assert time.monotonic() < deadline, f'command {kind} timed out'
                    received, _, data = frame(tcp)
                    if received == 0x8001 and struct.unpack_from('<I', data)[0] == seq:
                        actual = struct.unpack('<IHBBBB', data)
                        assert actual == (seq, kind, 1, 1, mode, result), actual
                        print(f'PASS command={kind} sequence={seq} mode={mode} result={result}')
                        break
            deadline = time.monotonic() + 5
            while True:
                assert time.monotonic() < deadline, 'vehicle telemetry timed out'
                kind, _, data = frame(tcp)
                if kind == 0x8003:
                    flags, voltage = struct.unpack_from('<Id', data, 8)
                    assert len(data) == 92 and flags == 1 and voltage == 11.7
                    print('PASS synthetic VehicleStatus 11.7 V, only voltage valid')
                    break
        packet = udp.recv(65535)
        assert len(packet) % 188 == 0 and all(packet[i] == 0x47 for i in range(0, len(packet), 188))
        print(f'PASS UDP MPEG-TS video: {len(packet)} bytes')
        duplicate = subprocess.run([str(ROOT / 'tools/run_gcs_test.sh'), '--skip-build'],
                                   capture_output=True, text=True)
        assert duplicate.returncode == 1 and 'already running' in duplicate.stderr
        print('PASS duplicate start rejected')
    finally:
        runner.terminate()
        try:
            runner.wait(timeout=15)
        except subprocess.TimeoutExpired:
            runner.kill()
            runner.wait()
        udp.close()
    with socket.socket() as probe:
        assert probe.connect_ex(('127.0.0.1', 7443)) != 0, 'cFS left running after stop'
    print('PASS cleanup: TCP 7443 closed')


if __name__ == '__main__':
    main()
