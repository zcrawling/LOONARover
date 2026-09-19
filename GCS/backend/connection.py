import asyncio
import socket
import time
import uuid

from .protocol import COMMANDS, encode, read_message


class Connection:
    def __init__(self, config, state):
        self.config, self.state = config, state
        self.writer = None
        self.lock = asyncio.Lock()
        self.pings = {}
        self.last_pong = None
        self.started = None
        self.got_status = False
        self.sequence = 0
        self.generation = 0

    def socket_options(self, sock):
        c = self.config["tcp"]
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, int(c["keepalive"]))
        for name, key in (("TCP_KEEPIDLE", "keepidle"), ("TCP_KEEPINTVL", "keepinterval"), ("TCP_KEEPCNT", "keepcount"), ("TCP_USER_TIMEOUT", "user_timeout_ms")):
            if hasattr(socket, name) and (c["keepalive"] or key == "user_timeout_ms"):
                try:
                    sock.setsockopt(socket.IPPROTO_TCP, getattr(socket, name), c[key])
                except OSError as exc:
                    self.state.event(f"Socket option {name} unavailable: {exc}")

    async def send(self, message, generation):
        async with self.lock:
            if self.writer is None or self.generation != generation:
                raise ConnectionError("Connection changed")
            self.writer.write(encode(message))
            await asyncio.wait_for(self.writer.drain(), self.config["network"]["write_timeout"])
            self.state.tx += 1

    async def command(self, name):
        name = name.upper()
        if name not in COMMANDS:
            return {"ok": False, "text": f'{name}: NOT_SUPPORTED (인터페이스 TBD)'}
        if self.state.connection != "CONNECTED" or self.writer is None:
            return {"ok": False, "text": f'"{name}" Not Sent — TCP 연결 확인 불가'}
        request_id = uuid.uuid4().hex
        if len(self.state.pending) >= 200:
            removable = next((k for k,v in self.state.pending.items() if v["state"] != "Pending"), None)
            if removable is None:
                return {"ok": False, "text": "요청 처리 중: 잠시 후 다시 시도하세요"}
            del self.state.pending[removable]
        entry = {"request_id": request_id, "command": name, "state": "Pending", "sent_at": time.monotonic()}
        self.state.pending[request_id] = entry
        self.state.event(f'"{name}" Sent', request_id)
        try:
            await self.send({"kind": "command", "command": name, "request_id": request_id}, self.generation)
        except (OSError, asyncio.TimeoutError):
            entry["state"] = "Result Unknown"
            self.state.event(f'"{name}" Result Unknown — 전송 중 연결 오류', request_id)
            if self.writer:
                self.writer.close()
            return {"ok": False, "request_id": request_id, "text": "전송 결과 확인 불가; 자동 재전송하지 않습니다"}
        return {"ok": True, "request_id": request_id, "text": f'"{name}" Sent'}

    async def receive(self, reader):
        while True:
            m = await read_message(reader)
            t = time.monotonic()
            self.state.rx += 1
            self.state.last_rx = t
            kind = m["kind"]
            if kind == "pong":
                sent = self.pings.pop(m["sequence"], None)
                if sent is not None:
                    self.last_pong = t
                    if self.got_status and self.state.connection != "CONNECTED":
                        self.state.connection = "CONNECTED"
                        self.state.event("TCP CONNECTED — PONG 및 현재 상태 확인")
            elif kind == "status":
                self.state.status = m
                self.state.last_status = t
                self.got_status = True
                if self.last_pong and t-self.last_pong < self.config["heartbeat"]["degraded_after"]:
                    if self.state.connection != "CONNECTED":
                        self.state.connection = "CONNECTED"
                        self.state.event("TCP CONNECTED — 현재 상태 복구")
            elif kind == "payload":
                self.state.sample = m
                self.state.last_sample = t
            elif kind == "result":
                entry = self.state.pending.get(m["request_id"])
                if entry is None or entry["command"] != m["command"]:
                    self.state.event("연결되지 않은 명령 결과 수신", m["request_id"])
                    continue
                result = m["result"]
                if entry["state"] in {"Completed", "Ended", "Failed", "Aborted", "Rejected"}:
                    continue
                entry["state"] = result
                text = f'"{m["command"]}" {result}'
                if m.get("error"):
                    text += f' — {m["error"]}'
                self.state.event(text, m["request_id"])
            else:
                raise ValueError(f"Unexpected rover message: {kind}")

    async def heartbeat(self):
        h = self.config["heartbeat"]
        next_ping = 0
        while True:
            t = time.monotonic()
            # Only matching PONG proves the outbound application path works.
            age = t - (self.last_pong or self.started)
            if age >= h["disconnect_after"]:
                raise TimeoutError("Heartbeat PONG timeout")
            if not self.got_status and t-self.started >= h["disconnect_after"]:
                raise TimeoutError("Initial status timeout")
            if age >= h["degraded_after"] and self.state.connection != "DEGRADED":
                self.state.connection = "DEGRADED"
                self.state.event("TCP DEGRADED — PONG 지연")
            for entry in self.state.pending.values():
                if entry["command"] == "PAYLOAD" and entry["state"] == "Pending" and t-entry["sent_at"] >= self.config["command"]["payload_receipt_timeout"]:
                    entry["state"] = "Result Unknown"
                    seconds = self.config["command"]["payload_receipt_timeout"]
                    self.state.event(f'"PAYLOAD" Command Result Unknown — {seconds:g}초 동안 명령 수신 확인을 받지 못했습니다.', entry["request_id"])
            if t >= next_ping:
                self.sequence += 1
                self.pings[self.sequence] = t
                self.pings = {k:v for k,v in self.pings.items() if t-v < h["disconnect_after"]}
                await self.send({"kind": "ping", "sequence": self.sequence}, self.generation)
                next_ping = t + h["interval"]
            await asyncio.sleep(min(0.1, h["interval"]))

    async def run(self):
        n = self.config["network"]
        attempt = 0
        while True:
            tasks = []
            self.last_pong = None
            self.got_status = False
            try:
                reader, writer = await asyncio.wait_for(asyncio.open_connection(n["host"], n["port"]), n["connect_timeout"])
                self.writer = writer
                self.generation += 1
                self.socket_options(writer.get_extra_info("socket"))
                self.started = time.monotonic()
                self.last_pong = None
                self.pings.clear()
                self.got_status = False
                self.state.connection = "SYNCING"
                self.state.error = None
                self.state.event("TCP 연결됨 — PONG 및 상태 확인 중 (MOCK)")
                tasks = [asyncio.create_task(self.receive(reader)), asyncio.create_task(self.heartbeat())]
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
                for task in done:
                    task.result()
            except (OSError, EOFError, ValueError, asyncio.IncompleteReadError) as exc:
                self.state.error = str(exc) or type(exc).__name__
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                if self.writer is not None:
                    writer, self.writer = self.writer, None
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except OSError:
                        pass
                self.generation += 1
                if self.got_status:
                    self.state.gaps += 1
                for entry in self.state.pending.values():
                    if entry["state"] == "Pending":
                        entry["state"] = "Result Unknown"
                        self.state.event(f'"{entry["command"]}" Result Unknown — 연결 단절', entry["request_id"])
                self.state.connection = "RECONNECTING"
            self.state.event(f"TCP RECONNECTING — {self.state.error}")
            if self.last_pong is not None:
                attempt = 0
            delay = n["reconnect_delays"][min(attempt, len(n["reconnect_delays"])-1)]
            attempt += 1
            await asyncio.sleep(delay)
