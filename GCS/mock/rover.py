import argparse
import asyncio
import time
from backend.config import DEFAULT_CONFIG, load
from backend.protocol import encode, read_message
from backend.state import now


class MockRover:
    def __init__(self, config):
        self.config = config
        self.mode = "STOP"
        self.payload_state = "IDLE"
        self.payload_id = None
        self.sample = 0
        self.writer = None
        self.lock = asyncio.Lock()
        self.payload_task = None
        self.delayed = set()
        self.command_history = []

    async def send(self, message, expected=None):
        async with self.lock:
            w = self.writer
            if w is None or (expected is not None and w is not expected):
                return
            try:
                w.write(encode(message))
                await asyncio.wait_for(w.drain(), self.config['network']['write_timeout'])
            except (OSError, asyncio.TimeoutError):
                w.close()

    async def result(self, command, rid, result, error=None, expected=None):
        m = {"kind": "result", "command": command, "request_id": rid, "result": result}
        if error:
            m["error"] = error
        await self.send(m, expected)

    def status(self):
        return {"kind": "status", "mode": self.mode, "source": "MOCK", "time": now(),
                "payload": {"state": self.payload_state, "request_id": self.payload_id},
                "values": {"배터리 전압 (V)": 12.1, "배터리 잔량 (%)": 78,
                           "라즈베리파이 내부 온도 (°C)": 43.2, "센서 연결": "CONNECTED",
                           "MCU 연결": "CONNECTED", "Wi-Fi 연결": "SIMULATED"}}

    async def delayed_receipt(self, rid, writer):
        await asyncio.sleep(self.config["mock"]["receipt_delay"])
        await self.result("PAYLOAD", rid, "Received", expected=writer)

    async def measure(self, rid):
        started = time.monotonic()
        while time.monotonic()-started < self.config["mock"]["payload_duration"]:
            self.sample += 1
            await self.send({"kind": "payload", "request_id": rid, "sample": self.sample, "time": now(),
                             "values": {"비접촉 표면온도계": {"value": round(30+self.sample%10/10, 1), "unit": "°C", "status": "VALID"},
                                        "접촉식 표면온도계": {"value": 29.8, "unit": "°C", "status": "VALID"},
                                        "자기상센서": {"value": None, "unit": "TBD", "status": "MOCK_UNDEFINED"}}})
            await asyncio.sleep(self.config["mock"]["sample_interval"])
        self.payload_state = "Ended"
        self.mode = "STOP"
        await self.result("PAYLOAD", rid, "Ended")

    async def command(self, m):
        name, rid = m["command"], m["request_id"]
        self.command_history.append((name, rid))
        self.command_history = self.command_history[-200:]
        if name == "STOP":
            if self.payload_task and not self.payload_task.done():
                self.payload_task.cancel()
                await asyncio.gather(self.payload_task, return_exceptions=True)
                self.payload_state = "Aborted"
                await self.result("PAYLOAD", self.payload_id, "Aborted")
            self.mode = "STOP"
            await self.result(name, rid, "Completed")
        elif self.payload_task and not self.payload_task.done():
            await self.result(name, rid, "Rejected", "BUSY (MOCK scenario)")
        elif name == "PAYLOAD":
            self.mode = "PAYLOAD"
            self.payload_state = "MEASURING"
            self.payload_id = rid
            self.sample = 0
            if self.config["mock"]["receipt_delay"]:
                task = asyncio.create_task(self.delayed_receipt(rid, self.writer))
                self.delayed.add(task)
                task.add_done_callback(self.delayed.discard)
            else:
                await self.result(name, rid, "Received")
            self.payload_task = asyncio.create_task(self.measure(rid))
        elif name == "REACTION":
            # This is an example result, not a recovery algorithm.
            self.mode = "STOP"
            await self.result(name, rid, "Completed")
        else:
            self.mode = name
            await self.result(name, rid, "Completed")
        await self.send(self.status())

    async def client(self, reader, writer):
        if self.writer is not None:
            writer.close()
            await writer.wait_closed()
            return
        self.writer = writer
        async def periodic():
            while True:
                await self.send(self.status(), expected=writer)
                await asyncio.sleep(self.config["mock"]["status_interval"])
        async def fault():
            delay = self.config["mock"]["disconnect_after"]
            if delay:
                await asyncio.sleep(delay)
                writer.close()
        ticker = asyncio.create_task(periodic())
        failure = asyncio.create_task(fault())
        try:
            while True:
                m = await read_message(reader)
                if m["kind"] == "ping":
                    if self.config["mock"]["send_pong"]:
                        await self.send({"kind": "pong", "sequence": m["sequence"]}, expected=writer)
                elif m["kind"] == "command":
                    await self.command(m)
                else:
                    raise ValueError("Unexpected client message")
        except (OSError, ValueError, asyncio.IncompleteReadError):
            pass
        finally:
            ticker.cancel()
            failure.cancel()
            await asyncio.gather(ticker, failure, return_exceptions=True)
            if self.writer is writer:
                self.writer = None
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    async def close(self):
        tasks = list(self.delayed)
        if self.payload_task:
            tasks.append(self.payload_task)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if self.writer:
            self.writer.close()


async def serve(config):
    rover = MockRover(config)
    server = await asyncio.start_server(rover.client, config["network"]["host"], config["network"]["port"])
    print(f"MOCK ROVER — no hardware — port {config['network']['port']}", flush=True)
    try:
        async with server:
            await server.serve_forever()
    finally:
        await rover.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args()
    try:
        asyncio.run(serve(load(args.config)))
    except KeyboardInterrupt:
        pass
