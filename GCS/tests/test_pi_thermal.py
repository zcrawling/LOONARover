import asyncio
import importlib.util
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from backend.pi_thermal import receive
from backend.real_app import RealState

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('thermal_sensor', ROOT/'platforms/loonar/ros2/terrain_navigation/runtime/thermal_sensor.py')
sensor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sensor)


class ThermalTests(unittest.IsolatedAsyncioTestCase):
    def test_sysfs_conversion_and_unavailable_sensor(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'temp'
            self.assertIsNone(sensor.read_temperature(path))
            path.write_text('52750\n')
            self.assertEqual(sensor.read_temperature(path), 52.75)
            for value in ('nan', 'garbage', '900000'):
                path.write_text(value)
                self.assertIsNone(sensor.read_temperature(path))

    async def test_stream_to_snapshot_and_disconnect(self):
        state = RealState('127.0.0.1')
        clients = []
        async def stream(reader, writer):
            clients.append(asyncio.current_task())
            await sensor.stream(reader, writer)
        with patch.object(sensor, 'read_temperature', return_value=48.125):
            server = await asyncio.start_server(stream, '127.0.0.1', 0)
            receiver = asyncio.create_task(receive(state, '127.0.0.1', server.sockets[0].getsockname()[1]))
            try:
                async with asyncio.timeout(3):
                    while state.pi_temperature is None:
                        await asyncio.sleep(.01)
                self.assertEqual(state.snapshot()['pi_temperature']['celsius'], 48.125)
                state.pi_temperature_at = time.monotonic()-4
                self.assertIsNone(state.snapshot()['pi_temperature']['celsius'])
            finally:
                receiver.cancel()
                await asyncio.gather(receiver, return_exceptions=True)
                for task in clients: task.cancel()
                await asyncio.gather(*clients, return_exceptions=True)
                server.close()
                await server.wait_closed()
            self.assertIsNone(state.snapshot()['pi_temperature']['celsius'])
