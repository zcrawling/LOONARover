"""Exposure requests use the existing SSH credentials and selected rover host."""
import asyncio
import json
import os
from pathlib import Path
from cli.hardware_monitor import ssh_command


async def control(host, request):
    query = {key: request[key] for key in ('operation', 'value') if key in request}
    source = ('query = ' + repr(query) + '\n' + Path(__file__).with_name('camera_remote.py').read_text()).encode()
    command, env = ssh_command(host, os.environ.get('LOONAR_SSH_USER', 'loonar'))
    process = None
    try:
        process = await asyncio.create_subprocess_exec(*command, env=env,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, _ = await asyncio.wait_for(process.communicate(source), 7)
        if process.returncode:
            raise OSError('Pi SSH 연결 실패: 주소·SSH 계정 또는 암호를 확인하세요')
        result = json.loads(stdout)
        if not isinstance(result, dict) or not isinstance(result.get('ok'), bool):
            raise ValueError('카메라 응답 형식 오류')
        return result
    except (OSError, ValueError, asyncio.TimeoutError) as error:
        return {'ok': False, 'text': f'노출 조절 실패: {error or "Pi 응답 시간 초과"}'}
    finally:
        if process is not None and process.returncode is None:
            process.kill()
            await process.wait()
