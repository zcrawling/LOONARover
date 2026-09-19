import asyncio
import unittest
from backend.config import load
from backend.connection import Connection
from backend.state import State
from mock.rover import MockRover


async def eventually(predicate, timeout=3):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.config = load()
        self.config['heartbeat'] = {'interval': 0.05, 'degraded_after': 0.2, 'disconnect_after': 0.5}
        self.config['network']['reconnect_delays'] = [0.05]
        self.config['command']['payload_receipt_timeout'] = 0.15
        self.config['mock'].update(status_interval=0.05, sample_interval=0.03, payload_duration=10)
        self.rover = MockRover(self.config)
        self.server = await asyncio.start_server(self.rover.client, '127.0.0.1', 0)
        self.config['network']['port'] = self.server.sockets[0].getsockname()[1]
        self.state = State(self.config)
        self.connection = Connection(self.config, self.state)
        self.task = asyncio.create_task(self.connection.run())
        await eventually(lambda: self.state.connection == 'CONNECTED')

    async def asyncTearDown(self):
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)
        self.server.close()
        await self.server.wait_closed()
        await self.rover.close()
        await asyncio.sleep(0.05)

    async def test_payload_stop_full_duplex_and_modes(self):
        for name in ('MANUAL', 'AUTO'):
            result = await self.connection.command(name)
            rid = result['request_id']
            await eventually(lambda: self.state.pending[rid]['state'] == 'Completed')
            await eventually(lambda: self.state.status['mode'] == name)
        result = await self.connection.command('PAYLOAD')
        rid = result['request_id']
        await eventually(lambda: self.state.pending[rid]['state'] == 'Received' and self.state.sample is not None)
        old_pong = self.connection.last_pong
        await eventually(lambda: self.connection.last_pong > old_pong)
        stop = await self.connection.command('STOP')
        await eventually(lambda: self.state.pending[stop['request_id']]['state'] == 'Completed')
        self.assertEqual(self.state.pending[rid]['state'], 'Aborted')
        await eventually(lambda: self.state.status['mode'] == 'STOP')
        self.assertTrue(self.state.snapshot()['sample_stale'])

    async def test_receipt_timeout_and_late_response(self):
        self.config['mock']['receipt_delay'] = 0.35
        result = await self.connection.command('PAYLOAD')
        rid = result['request_id']
        await eventually(lambda: self.state.pending[rid]['state'] == 'Result Unknown')
        self.assertIsNotNone(self.state.sample)  # Data does not masquerade as receipt.
        await eventually(lambda: self.state.pending[rid]['state'] == 'Received')
        self.assertEqual(len(self.rover.command_history), 1)

    async def test_reconnect_payload_continues_no_replay(self):
        result = await self.connection.command('PAYLOAD')
        rid = result['request_id']
        await eventually(lambda: self.state.sample is not None)
        old_sample = self.state.sample['sample']
        generation = self.connection.generation
        self.rover.writer.close()
        await eventually(lambda: self.connection.generation > generation and self.state.connection == 'CONNECTED')
        await eventually(lambda: self.state.sample['sample'] > old_sample)
        self.assertEqual(self.state.status['payload']['request_id'], rid)
        self.assertEqual(len(self.rover.command_history), 1)
        self.assertGreaterEqual(self.state.gaps, 1)

    async def test_status_without_pong_still_disconnects(self):
        self.config['mock']['send_pong'] = False
        await eventually(lambda: self.state.connection == 'DEGRADED')
        self.assertLess(self.state.snapshot()['last_rx_age'], 0.2)
        result = await self.connection.command('STOP')
        self.assertIn('Not Sent', result['text'])
        count = len(self.rover.command_history)
        await eventually(lambda: any('Heartbeat PONG timeout' in e['text'] for e in self.state.events))
        self.config['mock']['send_pong'] = True
        await eventually(lambda: self.state.connection == 'CONNECTED')
        self.assertEqual(len(self.rover.command_history), count)

    async def test_bad_frame_triggers_reconnect(self):
        generation = self.connection.generation
        self.rover.writer.write(b'LNK1\x00\x00\x00\x01x')
        await self.rover.writer.drain()
        await eventually(lambda: self.connection.generation > generation and self.state.connection == 'CONNECTED')
        self.assertTrue(any('Wrong magic' in e['text'] for e in self.state.events))

    async def test_received_does_not_timeout_during_long_measurement(self):
        result = await self.connection.command('PAYLOAD')
        rid = result['request_id']
        await eventually(lambda: self.state.pending[rid]['state'] == 'Received')
        await asyncio.sleep(0.3)
        self.assertEqual(self.state.pending[rid]['state'], 'Received')
        self.assertFalse(any('Command Result Unknown' in e['text'] for e in self.state.events))


if __name__ == '__main__':
    unittest.main()
