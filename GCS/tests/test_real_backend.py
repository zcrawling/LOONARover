import struct
import unittest

from backend.real_app import GroundLinkConnection, RealState, HEADER


class Writer:
    def __init__(self): self.data = []
    def write(self, data): self.data.append(data)
    async def drain(self): pass


class RealBackendTests(unittest.IsolatedAsyncioTestCase):
    async def test_flip_reverses_web_and_controller_motion_and_restores(self):
        state = RealState('test')
        state.connection = 'CONNECTED'
        link = GroundLinkConnection('test', 7443, state)
        link.writer = Writer()
        for flipped in (False, True, False):
            if state.flipped != flipped:
                before = len(link.writer.data)
                self.assertEqual((await link.toggle_flip())['flipped'], flipped)
                self.assertEqual(len(link.writer.data), before)
            self.assertEqual(state.snapshot()['flipped'], flipped)
            sign = -1 if flipped else 1
            for name, v, w in [('FORWARD', .2, 0), ('REVERSE', -.2, 0),
                               ('LEFT', 0, .6), ('RIGHT', 0, -.6)]:
                self.assertTrue((await link.command(name, .2, .6))['ok'])
                self.assertEqual(struct.unpack('<dd', link.writer.data[-1][HEADER.size:]),
                                 (sign*v, sign*w))
            self.assertTrue((await link.command('MANUAL', linear_mps=.1, angular_radps=-.4))['ok'])
            self.assertEqual(struct.unpack('<dd', link.writer.data[-1][HEADER.size:]),
                             (sign*.1, sign*-.4))
            await link.command('MANUAL', linear_mps=0, angular_radps=0)
            self.assertEqual(struct.unpack('<dd', link.writer.data[-1][HEADER.size:]), (0, 0))
            for name in ('STOP', 'AUTO'):
                await link.command(name)
                self.assertEqual(link.writer.data[-1][HEADER.size:], b'')

    async def test_flip_works_offline_without_sending_commands(self):
        state = RealState('test')
        link = GroundLinkConnection('test', 7443, state)
        self.assertTrue((await link.toggle_flip())['flipped'])
        self.assertFalse((await link.toggle_flip())['flipped'])
        self.assertEqual(state.tx, 0)

    async def test_reaction_tuning_is_validated_and_packed(self):
        from mcu_v2.reaction_wheel import Settings
        state = RealState('test'); state.connection = 'CONNECTED'
        link = GroundLinkConnection('test',7443,state); link.writer = Writer()
        for name,side in [('REACTION_LEFT',1),('REACTION_RIGHT',2)]:
            result = await link.command(name, reaction_settings={'left_first_offset':30})
            self.assertTrue(result['ok'])
            raw = link.writer.data[-1]
            self.assertEqual(HEADER.unpack_from(raw)[2],5)
            self.assertEqual(struct.unpack_from('<HH',raw,HEADER.size+8),(side,40))
            self.assertEqual(raw[HEADER.size+12:],Settings(left_first_offset=30).encode())
        count = len(link.writer.data)
        self.assertFalse((await link.command('REACTION_LEFT',reaction_settings={'servo_left':799}))['ok'])
        self.assertEqual(len(link.writer.data),count)
        self.assertTrue((await link.command('STOP'))['ok'])
    async def test_stop_auto_and_safe_manual_frames(self):
        state = RealState("rover.test")
        state.connection = "CONNECTED"
        connection = GroundLinkConnection("rover.test", 7443, state)
        writer = Writer()
        connection.writer = writer
        for command, expected_type, expected_payload in (
            ("STOP", 0x0001, b""),
            ("MANUAL", 0x0002, struct.pack("<dd", 0.0, 0.0)),
            ("AUTO", 0x0003, b""),
        ):
            result = await connection.command(command)
            self.assertTrue(result["ok"])
            magic, version, frame_type, sequence, length = HEADER.unpack_from(writer.data[-1])
            self.assertEqual((magic, version, frame_type), (b"LNK1", 1, expected_type))
            self.assertGreater(sequence, 0)
            self.assertEqual(writer.data[-1][HEADER.size:], expected_payload)
            self.assertEqual(length, len(expected_payload))

    async def test_payload_start_stop_opcodes(self):
        state = RealState("rover.test")
        state.connection = "CONNECTED"
        connection = GroundLinkConnection("rover.test", 7443, state)
        writer = Writer()
        connection.writer = writer
        for command, opcode in (("PAYLOAD_START", 1), ("PAYLOAD_STOP", 2)):
            result = await connection.command(command)
            self.assertTrue(result["ok"])
            header = HEADER.unpack_from(writer.data[-1])
            request_id, actual_opcode, parameter_length = struct.unpack(
                "<QHH", writer.data[-1][HEADER.size:])
            self.assertEqual(header[2], 0x0004)
            self.assertEqual((actual_opcode, parameter_length), (opcode, 0))
            self.assertTrue(0 <= request_id < 2**64)
        self.assertFalse((await connection.command("PAYLOAD"))["ok"])
        self.assertFalse((await connection.command("REACTION"))["ok"])

    async def test_web_keyboard_motion_frames(self):
        state = RealState("rover.test")
        state.connection = "CONNECTED"
        connection = GroundLinkConnection("rover.test", 7443, state,
            manual_control={"linear_speed_mps": 0.1, "angular_speed_radps": 0.5})
        writer = Writer()
        connection.writer = writer
        expected = {
            "FORWARD": (0.1, 0.0), "LEFT": (0.0, 0.5),
            "REVERSE": (-0.1, 0.0), "RIGHT": (0.0, -0.5),
        }
        for command, values in expected.items():
            self.assertTrue((await connection.command(command))["ok"])
            header = HEADER.unpack_from(writer.data[-1])
            self.assertEqual(header[2], 0x0002)
            self.assertEqual(struct.unpack("<dd", writer.data[-1][HEADER.size:]), values)

    async def test_adjustable_linear_speed(self):
        state = RealState("rover.test")
        state.connection = "CONNECTED"
        connection = GroundLinkConnection("rover.test", 7443, state)
        writer = Writer()
        connection.writer = writer
        self.assertTrue((await connection.command("FORWARD", 0.37))["ok"])
        self.assertEqual(struct.unpack("<dd", writer.data[-1][HEADER.size:]), (0.37, 0.0))
        self.assertTrue((await connection.command("FORWARD", 1.01))["ok"])
        self.assertEqual(struct.unpack("<dd", writer.data[-1][HEADER.size:]), (0.4, 0.0))

    async def test_adjustable_angular_speed(self):
        state = RealState("rover.test")
        state.connection = "CONNECTED"
        connection = GroundLinkConnection("rover.test", 7443, state)
        writer = Writer()
        connection.writer = writer
        for name, expected in (("LEFT", (0.0, 0.37)), ("RIGHT", (0.0, -0.37)),
                               ("MANUAL", (0.0, 0.0)), ("FORWARD", (0.1, 0.0))):
            self.assertTrue((await connection.command(name, angular_speed_radps=0.37))["ok"])
            self.assertEqual(HEADER.unpack_from(writer.data[-1])[2], 0x0002)
            self.assertEqual(struct.unpack("<dd", writer.data[-1][HEADER.size:]), expected)
        count = len(writer.data)
        for invalid in (True, "0.3", float('nan'), float('inf')):
            self.assertFalse((await connection.command("LEFT", angular_speed_radps=invalid))["ok"])
        self.assertEqual(len(writer.data), count)

    def test_real_telemetry_updates_web_snapshot(self):
        state = RealState("192.0.2.10")
        connection = GroundLinkConnection("192.0.2.10", 7443, state)
        connection.handle(0x8002, struct.pack("<BBBBdd", 3, 3, 1, 0, 0.0, 0.0))
        connection.handle(0x8003, struct.pack("<QI10d", 123, 0x1D, 12.4, 0.0,
                          1.0, 2.0, 0.3, 0.1, 0.2, 0.01, 0.02, 0.03))
        snapshot = state.snapshot()
        self.assertEqual(snapshot["source"], "REAL ROVER / 192.0.2.10")
        self.assertEqual(snapshot["status"]["mode"], "STOP")
        self.assertEqual(snapshot["status"]["values"]["배터리 전압 (V)"], 12.4)
        self.assertIsNone(snapshot["status"]["values"]["배터리 잔량 (%)"])

    def test_payload_pca_event_updates_snapshot(self):
        state = RealState("rover.test")
        connection = GroundLinkConnection("rover.test", 7443, state)
        def event(text):
            source = b"payload-pca"
            encoded = text.encode()
            return struct.pack("<QBIBH", 1, 0, 0x5001, len(source), len(encoded)) + source + encoded
        connection.handle(0x8006, event("STATE,7,RUNNING,station_02"))
        connection.handle(0x8006, event("STATE,8,STOPPING,station_02"))
        connection.handle(0x8006, event(
            "PCA,2,16.599285,23.949991,22.623278,2.013446,114.069168,114.069168,1,DEMO_ONLY,DEMO_ONLY_260927"))
        connection.handle(0x8006, event("STATE,8,IDLE,station_02_complete"))
        snapshot = state.snapshot()
        self.assertEqual(snapshot["status"]["payload"]["state"], "IDLE")
        self.assertEqual(snapshot["status"]["payload"]["station"], 2)
        self.assertEqual(snapshot["payload_sample"]["request_id"], "8")
        self.assertEqual(snapshot["payload_sample"]["values"]["PCA candidate"]["value"], 1)




class FlyLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_auto_start_stop_order_and_offline_cleanup(self):
        from unittest.mock import AsyncMock
        state=RealState('test');state.connection='CONNECTED'
        link=GroundLinkConnection('test',7443,state);link.writer=Writer()
        link.fly=AsyncMock()
        async def start(): self.assertFalse(link.writer.data)
        link.fly.start.side_effect=start
        self.assertTrue((await link.command('AUTO'))['ok'])
        async def stop(): self.assertEqual(HEADER.unpack_from(link.writer.data[-1])[2],1)
        link.fly.stop.side_effect=stop
        self.assertTrue((await link.command('STOP'))['ok'])
        state.connection='RECONNECTING'
        self.assertFalse((await link.command('STOP'))['ok'])
        self.assertEqual(link.fly.stop.await_count,2)

    async def test_failed_terminal_start_does_not_send_auto(self):
        from unittest.mock import AsyncMock
        state=RealState('test');state.connection='CONNECTED'
        link=GroundLinkConnection('test',7443,state);link.writer=Writer()
        link.fly=AsyncMock();link.fly.start.side_effect=RuntimeError('missing terminal')
        self.assertFalse((await link.command('AUTO'))['ok'])
        self.assertFalse(link.writer.data)


if __name__ == "__main__": unittest.main()
