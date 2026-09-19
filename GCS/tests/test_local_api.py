import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import app
from backend.config import ROOT, load
from cli import common
from cli.monitor import render
from mock.rover import MockRover


class LocalApiTest(unittest.IsolatedAsyncioTestCase):
    async def test_backend_terminal_interface(self):
        c = load()
        c['heartbeat'] = {'interval': 0.05, 'degraded_after': 0.3, 'disconnect_after': 0.6}
        c['mock']['status_interval'] = 0.05
        rover = MockRover(c)
        server = await asyncio.start_server(rover.client, '127.0.0.1', 0)
        c['network']['port'] = server.sockets[0].getsockname()[1]
        runtime = ROOT / '.runtime'
        runtime.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=runtime) as directory:
            path = Path(directory) / 'b.sock'
            with patch.object(app, 'LOCAL_SOCKET', path), patch.object(common, 'LOCAL_SOCKET', path):
                task = asyncio.create_task(app.serve(c))
                try:
                    async with asyncio.timeout(3):
                        while not path.exists():
                            await asyncio.sleep(0.01)
                        while True:
                            snapshot = await asyncio.to_thread(common.request, {'action': 'state'})
                            if snapshot['connection'] == 'CONNECTED':
                                break
                            await asyncio.sleep(0.01)
                        response = await asyncio.to_thread(common.request, {'action': 'command', 'command': 'MANUAL'})
                        self.assertTrue(response['ok'])
                        while True:
                            snapshot = await asyncio.to_thread(common.request, {'action': 'state'})
                            if any(e['text'] == '"MANUAL" Completed' for e in snapshot['events']):
                                break
                            await asyncio.sleep(0.01)
                    display = render(snapshot)
                    self.assertIn('MOCK / 예시 데이터', display)
                    self.assertIn('MANUAL', display)
                    unsupported = await asyncio.to_thread(common.request, {'action': 'command', 'command': 'VIDEO_STOP'})
                    self.assertIn('NOT_SUPPORTED', unsupported['text'])
                    self.assertEqual(len(rover.command_history), 1)
                finally:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                    server.close()
                    await server.wait_closed()
                    await rover.close()
                    await asyncio.sleep(0.05)
                self.assertFalse(path.exists())


if __name__ == '__main__':
    unittest.main()
