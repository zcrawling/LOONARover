"""GCP1 MOCK protocol. Deliberately incompatible with real LNK1 GroundLink."""
import json
import math
import struct

HEADER = struct.Struct("!4sI")
MAGIC = b"GCP1"
MAX_BODY = 16384
KINDS = {"command", "result", "status", "payload", "ping", "pong"}
COMMANDS = {"STOP", "MANUAL", "AUTO", "PAYLOAD", "REACTION"}
RESULTS = {"Received", "Completed", "Ended", "Failed", "Aborted", "Rejected"}


class ProtocolError(ValueError):
    pass


def validate(message):
    if not isinstance(message, dict) or message.get("kind") not in KINDS:
        raise ProtocolError("Unknown message kind")
    kind = message["kind"]
    if kind in ("command", "result", "payload"):
        if not isinstance(message.get("request_id"), str) or not 1 <= len(message["request_id"]) <= 80:
            raise ProtocolError("Missing request_id")
    if kind in ("command", "result") and message.get("command") not in COMMANDS:
        raise ProtocolError("Unknown command")
    if kind == "result" and message.get("result") not in RESULTS:
        raise ProtocolError("Unknown result")
    if kind in ("ping", "pong") and (type(message.get("sequence")) is not int or message["sequence"] <= 0):
        raise ProtocolError("Invalid heartbeat sequence")
    if kind == "status":
        if message.get("mode") not in COMMANDS or not isinstance(message.get("values"), dict):
            raise ProtocolError("Invalid status")
        p = message.get("payload", {})
        if not isinstance(p, dict) or p.get("state") not in {"IDLE", "MEASURING", "Ended", "Failed", "Aborted"}:
            raise ProtocolError("Invalid payload state")
    if kind == "payload":
        if type(message.get("sample")) is not int or message["sample"] < 1 or not isinstance(message.get("values"), dict):
            raise ProtocolError("Invalid sample")
    def finite(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise ProtocolError("Nonfinite number")
        if isinstance(value, dict):
            for v in value.values(): finite(v)
        elif isinstance(value, list):
            for v in value: finite(v)
    finite(message)
    return message


def encode(message):
    validate(message)
    body = json.dumps(message, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
    if len(body) > MAX_BODY:
        raise ProtocolError("Oversized message")
    return HEADER.pack(MAGIC, len(body)) + body


def decode(body):
    try:
        return validate(json.loads(body))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ProtocolError(str(exc)) from exc


class Parser:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        messages = []
        while len(self.buffer) >= HEADER.size:
            magic, length = HEADER.unpack_from(self.buffer)
            if magic != MAGIC or not 0 < length <= MAX_BODY:
                raise ProtocolError("Wrong magic or invalid length")
            end = HEADER.size + length
            if len(self.buffer) < end:
                break
            messages.append(decode(bytes(self.buffer[HEADER.size:end])))
            del self.buffer[:end]
        return messages


async def read_message(reader):
    header = await reader.readexactly(HEADER.size)
    magic, length = HEADER.unpack(header)
    if magic != MAGIC or not 0 < length <= MAX_BODY:
        raise ProtocolError("Wrong magic or invalid length")
    return decode(await reader.readexactly(length))
