"""Executed over SSH on the selected Pi; only contacts the camera's local socket."""
import json
from pathlib import Path
import socket
import tempfile

try:
    with tempfile.TemporaryDirectory(prefix='loonar-camera-') as directory:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
            client.bind(directory+'/reply.sock')
            client.settimeout(2)
            client.connect(str(Path.home()/'.cache/loonar/camera-control.sock'))
            client.send(json.dumps(query).encode())
            result=json.loads(client.recv(4096))
except FileNotFoundError:
    result={'ok': False, 'text': '카메라 제어 소켓 없음: Pi에 새 코드를 배포하고 영상 프로세스를 재시작하세요'}
except (OSError, ValueError) as error:
    result={'ok': False, 'text': f'카메라 제어 응답 실패: {error}'}
print(json.dumps(result, ensure_ascii=False))
