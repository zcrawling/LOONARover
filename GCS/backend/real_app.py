"""Real GroundLink backend exposed through the existing local Unix API."""

import argparse
import asyncio
import fcntl
import json
import math
import os
import struct
import time
from collections import OrderedDict, deque
from datetime import datetime, timezone

from backend.config import DEFAULT_CONFIG, LOCAL_SOCKET, load_manual_control
from cli.groundlink_monitor import FrameParser, ProtocolError, decode_payload


HEADER = struct.Struct("<4sHHII")
COMMAND_TYPES = {"STOP": 0x0001, "MANUAL": 0x0002, "AUTO": 0x0003}
MOTION_NAMES = {"FORWARD", "LEFT", "REVERSE", "RIGHT"}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RealState:
    def __init__(self, host, event_limit=100, stale_after=5.0, manual_control=None):
        self.host = host
        self.event_limit = event_limit
        self.stale_after = stale_after
        self.connection = "RECONNECTING"
        self.error = None
        self.last_rx = None
        self.last_status = None
        self.rx = 0
        self.tx = 0
        self.gaps = 0
        self.sequence = 0
        self.mode = "—"
        self.values = {}
        self.value_sources = {}
        self.payload = {"state": "—", "request_id": None}
        self.pending = OrderedDict()
        self.events = deque(maxlen=event_limit)
        self.event_sequence = 0
        self.manual_control = dict(manual_control or {})
        self.mcu = {}

    def event(self, text, request_id=None):
        self.event_sequence += 1
        self.events.append({"id": self.event_sequence, "time": now(), "text": text,
                            "request_id": request_id})

    def snapshot(self):
        t = time.monotonic()
        age = lambda stamp: None if stamp is None else round(t - stamp, 2)
        active = self.connection == "CONNECTED"
        return {
            "source": f"REAL ROVER / {self.host}",
            "connection": self.connection,
            "error": self.error,
            "status": {"mode": self.mode, "values": dict(self.values), "value_sources": dict(self.value_sources), "payload": dict(self.payload)},
            "payload_sample": None,
            "status_age": age(self.last_status),
            "sample_age": None,
            "last_rx_age": age(self.last_rx),
            "status_stale": not active or self.last_status is None or t - self.last_status > self.stale_after,
            "sample_stale": True,
            "rx_messages": self.rx,
            "tx_messages": self.tx,
            "data_gaps": self.gaps,
            "requests": list(self.pending.values()),
            "events": list(self.events),
            "manual_control": dict(self.manual_control),
            "mcu": {role: dict(values) for role, values in self.mcu.items()},
        }


class GroundLinkConnection:
    def __init__(self, host, port, state, connect_timeout=3.0, manual_control=None):
        self.host, self.port = host, port
        self.state = state
        self.connect_timeout = connect_timeout
        self.writer = None
        self.write_lock = asyncio.Lock()
        self.manual_control = manual_control or {"linear_speed_mps": 0.1, "angular_speed_radps": 0.1}

    def next_sequence(self):
        self.state.sequence = 1 if self.state.sequence >= 0xFFFFFFFF else self.state.sequence + 1
        return self.state.sequence

    async def command(self, name, linear_speed_mps=None):
        name = name.upper()
        if name in {"PAYLOAD", "REACTION"}:
            return {"ok": False, "text": f'"{name}" Not Sent — opcode 명세가 필요합니다.'}
        if name not in COMMAND_TYPES and name not in MOTION_NAMES:
            return {"ok": False, "text": f'"{name}" NOT_SUPPORTED'}
        if linear_speed_mps is not None and (
                type(linear_speed_mps) not in (int, float)
                or not math.isfinite(linear_speed_mps)
                or not 0.01 <= linear_speed_mps <= 1.0):
            return {"ok": False, "text": "선속도는 0.01~1.00 m/s여야 합니다."}
        if self.state.connection != "CONNECTED" or self.writer is None:
            return {"ok": False, "text": f'"{name}" Not Sent — 실제 로버 TCP 연결 없음'}
        sequence = self.next_sequence()
        linear = (float(linear_speed_mps) if linear_speed_mps is not None
                  else self.manual_control["linear_speed_mps"])
        angular = self.manual_control["angular_speed_radps"]
        motions = {
            "FORWARD": (linear, 0.0), "LEFT": (0.0, angular),
            "REVERSE": (-linear, 0.0), "RIGHT": (0.0, -angular),
        }
        wire_name = "MANUAL" if name in MOTION_NAMES else name
        payload = struct.pack("<dd", *motions[name]) if name in motions else (
            struct.pack("<dd", 0.0, 0.0) if name == "MANUAL" else b"")
        frame = HEADER.pack(b"LNK1", 1, COMMAND_TYPES[wire_name], sequence, len(payload)) + payload
        request_id = str(sequence)
        entry = {"request_id": request_id, "command": name, "state": "Pending",
                 "sent_at": time.monotonic()}
        self.state.pending[request_id] = entry
        while len(self.state.pending) > self.state.event_limit:
            self.state.pending.popitem(last=False)
        self.state.event(f'"{name}" Sent', request_id)
        try:
            async with self.write_lock:
                writer = self.writer
                if writer is None:
                    raise ConnectionError("연결 변경")
                writer.write(frame)
                await asyncio.wait_for(writer.drain(), 3.0)
            self.state.tx += 1
            return {"ok": True, "request_id": request_id, "text": f'"{name}" Sent'}
        except (OSError, ConnectionError, asyncio.TimeoutError):
            entry["state"] = "Result Unknown"
            self.state.event(f'"{name}" Result Unknown — 전송 중 연결 오류', request_id)
            return {"ok": False, "request_id": request_id,
                    "text": "전송 결과 확인 불가; 자동 재전송하지 않습니다"}

    def handle(self, frame_type, payload):
        data = decode_payload(frame_type, payload)
        t = time.monotonic()
        self.state.rx += 1
        self.state.last_rx = t
        if frame_type == 0x8001:
            request_id = str(data["ground_sequence"])
            entry = self.state.pending.get(request_id)
            result = data["result"]
            if entry:
                entry["cfs_received"] = data["cfs_received"]
                entry["adapter_forwarded"] = data["adapter_forwarded"]
                entry["state"] = ("Forwarded" if data["adapter_forwarded"] else "Received") if result == "OK" else result
                self.state.event(f'"{entry["command"]}" {entry["state"]}', request_id)
            else:
                self.state.event(f"연결되지 않은 명령 결과 #{request_id}: {result}", request_id)
            self.state.mode = data["mode"]
        elif frame_type == 0x8002:
            self.state.mode = data["mode"]
            self.state.values["마지막 명령 출처"] = data["last_source"]
            self.state.values["마지막 선속도 (m/s)"] = data["last_linear_mps"]
            self.state.values["마지막 각속도 (rad/s)"] = data["last_angular_radps"]
            self.state.last_status = t
        elif frame_type == 0x8003:
            mapping = {
                "battery_voltage": "배터리 전압 (V)", "battery_percent": "배터리 잔량 (%)",
                "odom_x": "Odometry X (m)", "odom_y": "Odometry Y (m)",
                "odom_yaw": "Odometry Yaw (rad)", "linear_mps": "선속도 (m/s)",
                "angular_radps": "각속도 (rad/s)", "imu_roll": "IMU Roll (rad)",
                "imu_pitch": "IMU Pitch (rad)", "imu_yaw": "IMU Yaw (rad)",
            }
            for source, label in mapping.items():
                self.state.values[label] = data[source]
                self.state.value_sources[label] = "VEHICLE"
            self.state.last_status = t
        elif frame_type == 0x8004:
            self.state.values["MCU 온도 (°C)"] = data["temperature_c"]
            self.state.values["MCU 상태"] = data["state"]
            self.state.values["MCU RX 오류"] = data["rx_errors"]
            self.state.last_status = t
        elif frame_type == 0x8005:
            for device in data["devices"]:
                self.state.values[f"{device['name']} 연결"] = device["state"]
            self.state.last_status = t
        elif frame_type == 0x8006:
            self.state.event(f"[{data['source']}] {data['text']}")
        elif frame_type == 0x8007:
            self.state.mcu[data["role"]] = data
            name = "Control" if data["role"] == "control" else "Payload"
            values = self.state.values
            values[f"{name} MCU 연결"] = "ONLINE" if data["online"] else "OFFLINE"
            values[f"{name} MCU UID"] = data["uid"] if int(data["uid"], 16) else None
            values[f"{name} MCU 온도 (°C)"] = data["temperature_c"] if data["online"] else None
            values[f"{name} health 경과 (ms)"] = data["health_age_ms"] if data["health_age_ms"] != 0xFFFFFFFF else None
            values[f"{name} inhibit"] = f"0x{data['inhibit']:08x}" if data["online"] else None
            values[f"{name} RX 오류"] = data["rx_errors"] if data["online"] else None
            values[f"{name} 표본 누락"] = data["sample_drops"] if data["online"] else None
            if data["role"] == "control":
                values["Control driver ACK 경과 (ms)"] = data["driver_ack_age_ms"] if data["online"] else None
            self.state.last_status = t

    async def connected(self, reader, writer):
        self.writer = writer
        self.state.connection = "CONNECTED"
        self.state.error = None
        self.state.event(f"TCP CONNECTED — {self.host}:{self.port}")
        parser = FrameParser()
        while True:
            chunk = await reader.read(4096)
            if not chunk:
                raise ConnectionError("로버가 연결을 종료함")
            for frame_type, _, payload in parser.feed(chunk):
                self.handle(frame_type, payload)

    async def run(self):
        delays = (1, 2, 4, 8, 10)
        attempt = 0
        while True:
            try:
                self.state.connection = "RECONNECTING"
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port), self.connect_timeout)
                attempt = 0
                await self.connected(reader, writer)
            except (OSError, ConnectionError, ProtocolError, asyncio.TimeoutError) as exc:
                self.state.error = str(exc) or type(exc).__name__
            finally:
                if self.writer is not None:
                    writer, self.writer = self.writer, None
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except OSError:
                        pass
                if self.state.last_rx is not None:
                    self.state.gaps += 1
                for entry in self.state.pending.values():
                    if entry["state"] == "Pending":
                        entry["state"] = "Result Unknown"
                self.state.connection = "RECONNECTING"
                self.state.event(f"TCP RECONNECTING — {self.state.error}")
            delay = delays[min(attempt, len(delays) - 1)]
            attempt += 1
            await asyncio.sleep(delay)


async def serve(host, port, config_path=DEFAULT_CONFIG, local_socket=LOCAL_SOCKET):
    manual = load_manual_control(config_path)
    state = RealState(host, manual_control=manual)
    connection = GroundLinkConnection(host, port, state, manual_control=manual)
    local_socket.parent.mkdir(mode=0o700, exist_ok=True)
    lock = open(local_socket.parent / "backend.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        lock.close()
        raise RuntimeError("GCS backend is already running") from exc
    local_socket.unlink(missing_ok=True)

    async def client(reader, writer):
        try:
            request = json.loads(await asyncio.wait_for(reader.readline(), 5))
            if request.get("action") == "state":
                response = state.snapshot()
            elif request.get("action") == "command" and isinstance(request.get("command"), str):
                response = await connection.command(
                    request["command"], request.get("linear_speed_mps"))
            else:
                response = {"ok": False, "text": "Unknown local request"}
            writer.write(json.dumps(response, ensure_ascii=False).encode() + b"\n")
            await asyncio.wait_for(writer.drain(), 5)
        except (ValueError, OSError, asyncio.TimeoutError, AttributeError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    server = await asyncio.start_unix_server(client, path=str(local_socket), limit=8192)
    os.chmod(local_socket, 0o600)
    task = asyncio.create_task(connection.run())
    print(f"GCS backend | REAL ROVER | {host}:{port}", flush=True)
    print(f"Local API: {local_socket}", flush=True)
    try:
        async with server:
            await server.serve_forever()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        local_socket.unlink(missing_ok=True)
        lock.close()


def main():
    parser = argparse.ArgumentParser(description="실제 GroundLink 웹 UI 백엔드")
    parser.add_argument("--host", required=True, help="로버 IP 주소")
    parser.add_argument("--port", type=int, default=7443)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args()
    try:
        asyncio.run(serve(args.host, args.port, args.config))
    except KeyboardInterrupt:
        pass
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        parser.exit(1, f"실제 백엔드 시작 실패: {exc}\n")


if __name__ == "__main__":
    main()
