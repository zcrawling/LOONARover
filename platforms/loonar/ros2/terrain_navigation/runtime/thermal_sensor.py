"""Read-only Pi CPU temperature stream, independent of motion and ROS load."""
import asyncio
import json
import math
from pathlib import Path
import signal

PORT = 7445
SENSOR = Path('/sys/class/thermal/thermal_zone0/temp')


def read_temperature(path=SENSOR):
    try:
        value = float(path.read_text().strip()) / 1000
        return value if math.isfinite(value) and -40 <= value <= 150 else None
    except (OSError, ValueError):
        return None


async def stream(reader, writer):
    peer=writer.get_extra_info('peername')
    if not peer or peer[0] not in ('10.254.254.2','127.0.0.1'):
        writer.close()
        await writer.wait_closed()
        return
    try:
        while not reader.at_eof():
            packet = dict(cpu_temperature_c=read_temperature())
            writer.write((json.dumps(packet, allow_nan=False)+'\n').encode())
            await asyncio.wait_for(writer.drain(), 2)
            await asyncio.sleep(1)
    except (OSError, asyncio.TimeoutError):
        pass
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass


async def serve():
    server = await asyncio.start_server(stream, '0.0.0.0', PORT, limit=1024)
    async with server:
        await server.serve_forever()


def main():
    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGHUP, stop)
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
