import json
import socket
from backend.config import LOCAL_SOCKET


def request(data):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(7)
        sock.connect(str(LOCAL_SOCKET))
        sock.sendall(json.dumps(data).encode() + b"\n")
        with sock.makefile("rb") as stream:
            line = stream.readline(2_000_000)
            if not line:
                raise ConnectionError("백엔드 응답 없음")
            return json.loads(line)


def safe(text):
    # Remote text must not inject terminal escape/control sequences.
    return "".join(c if c.isprintable() else " " for c in str(text))
