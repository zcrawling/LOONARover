"""Interactive keyboard control for a real GroundLink v1 rover."""

import argparse
import json
import os
import select
import socket
import struct
import sys
import termios
import tty

from backend.config import DEFAULT_CONFIG, load_manual_control
from .groundlink_monitor import FrameParser, ProtocolError, TYPE_NAMES, decode_payload


HEADER = struct.Struct("<4sHHII")
KEY_SEQUENCES = {
    b"\x1b[5~": "PAGE_UP",
    b"\x1b[H": "HOME",
    b"\x1bOH": "HOME",
    b"\x1b[1~": "HOME",
    b"\x1b[6~": "PAGE_DOWN",
    b"\x1b[F": "END",
    b"\x1bOF": "END",
    b"\x1b[4~": "END",
    b" ": "SPACE",
    b"q": "QUIT",
    b"Q": "QUIT",
}


def encode_command(frame_type, sequence, payload=b""):
    return HEADER.pack(b"LNK1", 1, frame_type, sequence, len(payload)) + payload


def command_for_key(key, config):
    linear = config["linear_speed_mps"]
    angular = config["angular_speed_radps"]
    if key == config["forward_key"]:
        return "MANUAL 전진", encode_command(0x0002, 0, struct.pack("<dd", linear, 0.0))
    if key == config["left_key"]:
        return "MANUAL 좌회전", encode_command(0x0002, 0, struct.pack("<dd", 0.0, angular))
    if key == config["reverse_key"]:
        return "MANUAL 후진", encode_command(0x0002, 0, struct.pack("<dd", -linear, 0.0))
    if key == config["right_key"]:
        return "MANUAL 우회전", encode_command(0x0002, 0, struct.pack("<dd", 0.0, -angular))
    if key == config["stop_key"]:
        return "STOP", encode_command(0x0001, 0)
    return None


def with_sequence(frame, sequence):
    magic, version, frame_type, _, length = HEADER.unpack_from(frame)
    return HEADER.pack(magic, version, frame_type, sequence, length) + frame[HEADER.size:]


def read_key(fd):
    data = os.read(fd, 1)
    if data != b"\x1b":
        return KEY_SEQUENCES.get(data)
    # Terminal escape sequences can arrive a byte at a time.
    while len(data) < 8:
        readable, _, _ = select.select([fd], [], [], 0.03)
        if not readable:
            break
        data += os.read(fd, 1)
        if data in KEY_SEQUENCES:
            return KEY_SEQUENCES[data]
    return KEY_SEQUENCES.get(data)


def run(host, port, timeout, config):
    if not sys.stdin.isatty():
        raise RuntimeError("키보드 입력이 가능한 터미널에서 실행해야 합니다")
    print(f"[연결 시도] {host}:{port}")
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(None)
        parser = FrameParser()
        sequence = 0
        fd = sys.stdin.fileno()
        previous = termios.tcgetattr(fd)
        print("[연결 성공]")
        print("Page Up 전진 | Home 좌회전 | Page Down 후진 | End 우회전")
        print("Space STOP | Q 종료 (종료 전에 Space로 정지하세요)")
        try:
            tty.setraw(fd)
            while True:
                readable, _, _ = select.select([fd, sock], [], [])
                if sock in readable:
                    data = sock.recv(4096)
                    if not data:
                        raise ConnectionError("로버가 연결을 종료함")
                    for frame_type, received_sequence, payload in parser.feed(data):
                        decoded = decode_payload(frame_type, payload)
                        if frame_type == 0x8001:
                            print("\r" + json.dumps({"type": TYPE_NAMES[frame_type],
                                  "sequence": received_sequence, **decoded}, ensure_ascii=False))
                if fd in readable:
                    key = read_key(fd)
                    if key == "QUIT":
                        print("\r[종료] Q는 STOP이 아닙니다.")
                        return
                    command = command_for_key(key, config) if key else None
                    if command:
                        name, frame = command
                        sequence = 1 if sequence >= 0xFFFFFFFF else sequence + 1
                        sock.sendall(with_sequence(frame, sequence))
                        print(f"\r[전송 #{sequence}] {name}")
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, previous)


def main():
    parser = argparse.ArgumentParser(description="실제 로버 GroundLink 키보드 수동 조종")
    parser.add_argument("host", help="로버 IP 주소")
    parser.add_argument("--port", type=int, default=7443)
    parser.add_argument("--connect-timeout", type=float, default=3.0)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port는 1~65535여야 합니다")
    try:
        run(args.host, args.port, args.connect_timeout, load_manual_control(args.config))
    except KeyboardInterrupt:
        print("\n[종료] Ctrl+C는 STOP이 아닙니다.")
    except (OSError, ProtocolError, RuntimeError, ValueError, KeyError) as exc:
        parser.exit(1, f"조종기 오류: {exc}\n")


if __name__ == "__main__":
    main()
