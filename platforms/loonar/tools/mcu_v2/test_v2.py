import json
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import unittest
from .wire import Frame, Kind, Parser, crc32c
from .buffer import ReceiveBuffer
from .config import load, geometry, driver_packet, wheel_command
from .backend import health_packet, HEALTH_HEADER, Gateway, Sink
from .link import Link


class FakeSerial:
    role = 1
    uid = 1
    bound = True

    def __init__(self, *args, **kwargs):
        self.data = b""
        self.closed = False

    def write(self, data):
        f = Parser().feed(data)[0]
        if f.kind == Kind.HELLO_REQUEST:
            payload = struct.pack("<QQIII", self.uid, self.uid, 1, 0, int(self.bound))
            response = Frame(self.role, Kind.HELLO, 1, 0, f.sequence, payload=payload)
        elif f.kind == Kind.SESSION:
            response = Frame(
                self.role,
                Kind.RESULT,
                1,
                f.session,
                f.sequence,
                payload=struct.pack("<BBHI", Kind.SESSION, 0, 0, f.sequence),
            )
        else:
            return len(data)
        self.data += response.encode()
        return len(data)

    def read(self, _):
        data = self.data
        self.data = b""
        return data

    def close(self):
        self.closed = True


class Tests(unittest.TestCase):
    def test_crc_fragment_resync(self):
        self.assertEqual(crc32c(b"123456789"), 0xE3069283)
        f = Frame(
            1,
            Kind.MOTION,
            7,
            9,
            11,
            123456,
            struct.pack("<IiiI", 42, 123456, -654321, 150),
        )
        raw = f.encode()
        p = Parser()
        out = []
        corrupt = bytearray(raw)
        corrupt[-1] ^= 1
        for byte in b"garbage" + corrupt + raw:
            out += p.feed(bytes([byte]))
        self.assertEqual(out, [f])
        self.assertGreater(p.errors, 0)
        p.feed(raw[:20])
        p.expire()
        self.assertEqual(p.feed(raw + raw), [f, f])

    def test_cpp_python_motion_wire(self):
        exe = Path(
            "build/mcu-v2-check/platforms/loonar/firmware/control/test_control_v2"
        )
        if not exe.exists():
            self.skipTest("build the CMake host tests first")
        raw = subprocess.check_output([str(exe.resolve()), "vector"], text=True).strip()
        f = Frame(
            1,
            Kind.MOTION,
            7,
            9,
            11,
            123456,
            struct.pack("<IiiI", 42, 123456, -654321, 150),
        )
        self.assertEqual(raw, f.encode().hex())

    @staticmethod
    def frame(n, boot=4):
        return Frame(1, Kind.IMU, boot, 7, n, n * 100, b"a")

    def test_ram_buffer_reorder_and_duplicates(self):
        b = ReceiveBuffer()
        b.begin(4, 1)
        self.assertTrue(b.accept(self.frame(2)))
        self.assertEqual(b.ack, 0)
        b.accept(self.frame(1))
        self.assertEqual(b.ack, 2)
        self.assertFalse(b.accept(self.frame(2)))
        self.assertEqual([b.pop().sequence, b.pop().sequence], [1, 2])
        self.assertIsNone(b.pop())

    def test_full_buffer_does_not_ack_dropped_input(self):
        b = ReceiveBuffer(2)
        b.begin(4, 1)
        b.accept(self.frame(1))
        b.accept(self.frame(2))
        self.assertFalse(b.accept(self.frame(3)))
        self.assertEqual(b.ack, 2)
        b.pop()
        self.assertTrue(b.accept(self.frame(3)))
        self.assertEqual(b.ack, 3)
        self.assertEqual(b.full, 1)

    def test_missing_sample_waits_for_retry(self):
        b = ReceiveBuffer()
        b.begin(4, 1)
        b.accept(self.frame(1))
        b.accept(self.frame(3))
        self.assertEqual(b.advance(2), 1)
        self.assertEqual(b.missing, 0)
        b.accept(self.frame(2))
        self.assertEqual(b.ack, 3)

    def test_mcu_overflow_is_reported(self):
        b = ReceiveBuffer()
        b.begin(4, 1)
        b.accept(self.frame(1))
        b.accept(self.frame(5))
        self.assertEqual(b.advance(5), 5)
        self.assertEqual(b.missing, 3)
        self.assertEqual([b.pop().sequence, b.pop().sequence], [1, 5])

    def test_reconnect_keeps_ram_and_boot_change_clears_it(self):
        b = ReceiveBuffer()
        b.begin(4, 1)
        b.accept(self.frame(1))
        b.begin(4, 2)
        self.assertEqual(len(b.ready), 1)
        self.assertEqual(b.ack, 1)
        b.begin(5, 1)
        self.assertEqual(b.ack, 0)
        self.assertFalse(b.ready)
        with self.assertRaises(ValueError):
            b.accept(self.frame(2))

    def test_registry_rejects_role_mixup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "devices.json"
            d = {
                "schema": 2,
                "devices": {
                    "control": {
                        "uid": "0000000000000001",
                        "device": "/dev/serial/by-id/a",
                        "transport": "usb",
                    },
                    "payload": {
                        "uid": "0000000000000001",
                        "device": "/dev/serial/by-id/b",
                        "transport": "usb",
                    },
                },
            }
            path.write_text(json.dumps(d))
            with self.assertRaises(ValueError):
                load(path, "control")
            d["devices"]["payload"]["uid"] = "0000000000000002"
            path.write_text(json.dumps(d))
            self.assertEqual(load(path, "control")["role_id"], 1)

    def test_driver_configuration_has_no_motion_policy(self):
        self.assertEqual(driver_packet({}), struct.pack("<IB3x", 115200, 128))
        self.assertIsNone(geometry({}))
        self.assertIsNone(
            geometry({"geometry": dict(radius_m=0, track_m=0, counts_per_rev=0)})
        )

    def test_pi_wheel_conversion_without_rate_limit(self):
        import math

        g = geometry(
            {
                "geometry": dict(
                    radius_m=0.1,
                    track_m=0.4,
                    counts_per_rev=200 * math.pi,
                    left_sign=1,
                    right_sign=-1,
                )
            }
        )
        self.assertEqual(wheel_command(g, 1, 2), (600, -1400))
        self.assertEqual(wheel_command(g, 2, 0), (2000, -2000))
        with self.assertRaises(ValueError):
            wheel_command(g, float("nan"), 0)
        with self.assertRaises(ValueError):
            wheel_command(g, 1e20, 0)

    def test_health_schema(self):
        raw = health_packet({"role_id": 2, "uid_int": 123})
        self.assertEqual(len(raw), 128)
        values = HEALTH_HEADER.unpack_from(raw)
        self.assertEqual(
            (values[0], values[1], values[2], values[7], values[8]),
            (b"MCU2", 2, 0, 123, 0xFFFFFFFF),
        )

    def test_gateway_handshake_and_no_command_refresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "backend.sock")
            server = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            server.bind(path)
            server.listen(1)
            g = Gateway(path)
            try:
                self.assertIsNone(g.latest())
                peer, _ = server.accept()
                with peer:
                    self.assertEqual(
                        peer.recv(100), struct.pack("<IHHI", 0x4C4E5247, 1, 1, 0)
                    )
                    peer.send(
                        struct.pack("<IHHIBdd", 0x4C4E5247, 1, 8, 17, 1, 0.1, 0.2)
                    )
                    self.assertEqual(g.latest(), (0.1, 0.2))
                    self.assertIsNone(g.latest())
            finally:
                g.close()
                server.close()

    def test_output_backpressure_is_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            sink = Sink(str(Path(tmp) / "missing.sock"))
            try:
                self.assertFalse(sink.send(b"a"))
                self.assertEqual(sink.dropped, 1)
            finally:
                sink.close()

    def test_identity_handshake_without_release_metadata(self):
        link = Link({"device": "fake", "role_id": 1, "uid_int": 1}, FakeSerial)
        self.assertEqual(link.boot, 1)
        self.assertNotEqual(link.session, 0)
        link.close()

        class WrongRole(FakeSerial):
            role = 2

        class WrongUID(FakeSerial):
            uid = 2

        class Unbound(FakeSerial):
            bound = False

        for port in (WrongRole, WrongUID, Unbound):
            with self.assertRaises(ValueError):
                Link({"device": "fake", "role_id": 1, "uid_int": 1}, port)


if __name__ == "__main__":
    unittest.main()
