"""Low-bandwidth Pi temperature receiver; never sends rover commands."""
import asyncio
import json
import math
import time


async def receive(state, host, port=7445):
    while True:
        writer = None
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port, limit=1024), 3)
            while True:
                line = await asyncio.wait_for(reader.readline(), 3)
                if not line:
                    break
                value = json.loads(line)['cpu_temperature_c']
                if value is not None and (type(value) not in (float, int)
                        or not math.isfinite(value) or not -40 <= value <= 150):
                    raise ValueError('invalid Pi temperature')
                state.pi_temperature = value
                state.pi_temperature_at = time.monotonic()
        except (OSError, asyncio.TimeoutError, ValueError, KeyError, TypeError):
            pass
        finally:
            state.pi_temperature = None
            if writer is not None:
                writer.close()
                try:
                    await writer.wait_closed()
                except OSError:
                    pass
        await asyncio.sleep(2)
