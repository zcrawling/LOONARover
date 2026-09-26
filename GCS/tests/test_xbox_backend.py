"""Signed controller motion crosses the local API and the shared GroundLink TCP."""
import asyncio
import json
from pathlib import Path
import struct
import tempfile
import unittest

from backend.real_app import serve, HEADER


class ControllerApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_api_preserves_combined_motion_on_one_tcp_connection(self):
        frames = asyncio.Queue()
        peers = []
        async def rover(reader, writer):
            peers.append(writer)
            try:
                while True:
                    header = HEADER.unpack(await reader.readexactly(16))
                    payload = await reader.readexactly(header[4])
                    await frames.put((header, payload))
            except asyncio.IncompleteReadError:
                pass
            finally:
                writer.close()
                await writer.wait_closed()
        server = await asyncio.start_server(rover, '127.0.0.1', 0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'backend.sock'
            task = asyncio.create_task(serve('127.0.0.1', server.sockets[0].getsockname()[1], local_socket=path))
            async def local(body):
                reader, writer = await asyncio.open_unix_connection(path)
                writer.write(json.dumps(body).encode() + b'\n')
                await writer.drain()
                result = json.loads(await reader.readline())
                writer.close()
                await writer.wait_closed()
                return result
            try:
                async with asyncio.timeout(5):
                    while not path.exists():
                        await asyncio.sleep(.01)
                    while (await local({'action': 'state'}))['connection'] != 'CONNECTED':
                        await asyncio.sleep(.01)
                    for command, values in [('MANUAL', (-.25, .75)), ('FORWARD', None), ('STOP', None)]:
                        body = {'action': 'command', 'command': command}
                        if values:
                            body.update(linear_mps=values[0], angular_radps=values[1])
                        self.assertTrue((await local(body))['ok'])
                        header, payload = await frames.get()
                        if command == 'STOP':
                            self.assertEqual((header[2], payload), (1, b''))
                        else:
                            self.assertEqual(header[2], 2)
                            self.assertEqual(struct.unpack('<dd', payload), values or (.1, 0))
                    self.assertEqual(len(peers), 1)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                for peer in peers:
                    peer.close()
                    await peer.wait_closed()
                server.close()
                await server.wait_closed()


if __name__ == '__main__':
    unittest.main()
