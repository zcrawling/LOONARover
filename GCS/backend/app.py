"""Local Unix-socket API; no external web service or dependencies."""
import argparse
import asyncio
import fcntl
import json
import os

from .config import DEFAULT_CONFIG, LOCAL_SOCKET, load
from .connection import Connection
from .state import State


async def serve(config):
    LOCAL_SOCKET.parent.mkdir(mode=0o700, exist_ok=True)
    lock = open(LOCAL_SOCKET.parent / "backend.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise RuntimeError("GCS backend is already running")
    LOCAL_SOCKET.unlink(missing_ok=True)
    state = State(config)
    connection = Connection(config, state)

    async def client(reader, writer):
        try:
            line = await asyncio.wait_for(reader.readline(), 5)
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("Expected object")
            if request.get("action") == "state":
                response = state.snapshot()
            elif request.get("action") == "command" and isinstance(request.get("command"), str):
                response = await connection.command(request["command"])
            else:
                response = {"ok": False, "text": "Unknown local request"}
            writer.write(json.dumps(response, ensure_ascii=False).encode() + b"\n")
            await asyncio.wait_for(writer.drain(), 5)
        except (ValueError, OSError, asyncio.TimeoutError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    server = await asyncio.start_unix_server(client, path=str(LOCAL_SOCKET), limit=8192)
    os.chmod(LOCAL_SOCKET, 0o600)
    task = asyncio.create_task(connection.run())
    print(f"GCS backend | MOCK ONLY | {config['network']['host']}:{config['network']['port']}", flush=True)
    print(f"Local API: {LOCAL_SOCKET}", flush=True)
    try:
        async with server:
            await server.serve_forever()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        LOCAL_SOCKET.unlink(missing_ok=True)
        lock.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args()
    try:
        asyncio.run(serve(load(args.config)))
    except KeyboardInterrupt:
        pass
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        parser.exit(1, f"GCS startup error: {exc}\n")


if __name__ == "__main__":
    main()
