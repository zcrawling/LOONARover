"""Transparent GroundLink recorder: TCP 7444 -> existing cFS TCP 7443.

Does not generate, resend, interpret for control, or modify commands.
"""
import asyncio
import struct
from .journal import emit

HEADER = struct.Struct('<4sHHII')


class Frames:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        result = []
        while len(self.buffer) >= HEADER.size:
            magic, version, kind, seq, size = HEADER.unpack_from(self.buffer)
            if magic != b'LNK1' or version != 1 or size > 512:
                raise ValueError('invalid GroundLink frame')
            end = HEADER.size+size
            if len(self.buffer) < end:
                break
            result.append((kind, seq, bytes(self.buffer[HEADER.size:end])))
            del self.buffer[:end]
        return result


async def bridge(reader, writer):
    identity = str(writer.get_extra_info('peername'))
    remote = None
    tasks = []
    try:
        upstream, remote = await asyncio.open_connection('127.0.0.1', 7443)
        emit('groundlink', 'connect', peer=identity)

        async def pump(src, dst, direction):
            parser = Frames()
            while data := await src.read(8192):
                emit('groundlink', 'bytes', data, direction=direction, peer=identity)
                # The exact received chunks are archived before forwarding.
                dst.write(data)
                await dst.drain()
                emit('groundlink', 'forwarded', direction=direction, bytes=len(data), peer=identity)
                for kind, sequence, payload in parser.feed(data):
                    emit('groundlink', 'frame', payload, direction=direction,
                         kind=kind, ground_sequence=sequence, peer=identity)
            if parser.buffer:
                emit('groundlink', 'partial_frame', bytes(parser.buffer), direction=direction)

        tasks = [asyncio.create_task(pump(reader, remote, 'gcs_to_rover')),
                 asyncio.create_task(pump(upstream, writer, 'rover_to_gcs'))]
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except (OSError, ValueError) as error:
        emit('groundlink', 'error', reason=str(error), peer=identity)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for stream in (writer, remote):
            if stream is not None:
                stream.close()
                try:
                    await stream.wait_closed()
                except OSError:
                    pass
        emit('groundlink', 'disconnect', peer=identity)


async def main():
    server = await asyncio.start_server(bridge, '0.0.0.0', 7444)
    print('GroundLink capture listening on :7444 -> localhost:7443', flush=True)
    async with server:
        await server.serve_forever()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
