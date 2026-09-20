"""Read-only GroundLink v1 telemetry monitor for a real rover."""

import argparse
import json
import socket
import struct
import sys
import time


HEADER = struct.Struct("<4sHHII")
MAGIC = b"LNK1"
VERSION = 1
MAX_PAYLOAD = 512

TYPE_NAMES = {
    0x8001: "COMMAND_RESULT",
    0x8002: "GATEWAY_STATUS",
    0x8003: "VEHICLE_STATUS",
    0x8004: "LOONAR_MCU_STATUS",
    0x8005: "DEVICE_STATUS",
    0x8006: "EVENT",
    0x8007: "MCU_V2_STATUS",
}
MODE_NAMES = {1: "AUTO", 2: "MANUAL", 3: "STOP", 4: "PAYLOAD", 5: "REACTION"}
SOURCE_NAMES = {0: "NONE", 1: "ROS_AUTO", 2: "GROUND_MANUAL", 3: "GROUND_STOP"}
RESULT_NAMES = {
    0: "OK",
    1: "BAD_PAYLOAD",
    2: "GATEWAY_DISCONNECTED",
    3: "NOT_IMPLEMENTED",
    4: "INTERNAL_ERROR",
}
DEVICE_NAMES = ("IMU", "MOTOR", "PAYLOAD_SENSOR", "LIDAR", "CAMERA", "MCU_LINK", "WIFI")
DEVICE_STATE_NAMES = {0: "UNKNOWN", 1: "CONNECTED", 2: "DISCONNECTED", 3: "ERROR"}


class ProtocolError(ValueError):
    pass


class FrameParser:
    """Accumulate TCP bytes and return complete GroundLink frames."""

    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        frames = []
        while len(self.buffer) >= HEADER.size:
            magic, version, frame_type, sequence, payload_length = HEADER.unpack_from(self.buffer)
            if magic != MAGIC:
                raise ProtocolError(f"잘못된 magic: {magic!r}")
            if version != VERSION:
                raise ProtocolError(f"지원하지 않는 버전: {version}")
            if frame_type not in TYPE_NAMES:
                raise ProtocolError(f"알 수 없는 수신 타입: 0x{frame_type:04x}")
            if payload_length > MAX_PAYLOAD:
                raise ProtocolError(f"payload가 너무 큼: {payload_length}")
            end = HEADER.size + payload_length
            if len(self.buffer) < end:
                break
            frames.append((frame_type, sequence, bytes(self.buffer[HEADER.size:end])))
            del self.buffer[:end]
        return frames


def _exact(payload, size, name):
    if len(payload) != size:
        raise ProtocolError(f"{name} payload 길이 오류: {len(payload)} (예상 {size})")


def decode_payload(frame_type, payload):
    """Decode one payload into values safe to print as JSON."""
    if frame_type == 0x8001:
        _exact(payload, 10, "COMMAND_RESULT")
        ground_sequence, command_type, received, forwarded, mode, result = struct.unpack("<IHBBBB", payload)
        return {
            "ground_sequence": ground_sequence,
            "command_type": f"0x{command_type:04x}",
            "cfs_received": bool(received),
            "adapter_forwarded": bool(forwarded),
            "mode": MODE_NAMES.get(mode, f"UNKNOWN({mode})"),
            "result": RESULT_NAMES.get(result, f"UNKNOWN({result})"),
        }
    if frame_type == 0x8002:
        _exact(payload, 20, "GATEWAY_STATUS")
        mode, source, has_last, reason, linear, angular = struct.unpack("<BBBBdd", payload)
        return {
            "mode": MODE_NAMES.get(mode, f"UNKNOWN({mode})"),
            "last_source": SOURCE_NAMES.get(source, f"UNKNOWN({source})"),
            "has_last": bool(has_last),
            "reason": reason,
            "last_linear_mps": linear if has_last else None,
            "last_angular_radps": angular if has_last else None,
        }
    if frame_type == 0x8003:
        _exact(payload, 92, "VEHICLE_STATUS")
        values = struct.unpack("<QI10d", payload)
        timestamp_ms, flags, *numbers = values
        names = (
            "battery_voltage", "battery_percent", "odom_x", "odom_y", "odom_yaw",
            "linear_mps", "angular_radps", "imu_roll", "imu_pitch", "imu_yaw",
        )
        valid_bits = (0, 1, 2, 2, 2, 3, 3, 4, 4, 4)
        result = {"timestamp_ms": timestamp_ms, "valid_flags": f"0x{flags:08x}"}
        result.update({name: value if flags & (1 << bit) else None
                       for name, value, bit in zip(names, numbers, valid_bits)})
        return result
    if frame_type == 0x8004:
        _exact(payload, 50, "LOONAR_MCU_STATUS")
        timestamp, uptime, temperature, state, inhibits, linear, angular, errors = struct.unpack(
            "<QQdHIddI", payload
        )
        return {"timestamp_ms": timestamp, "uptime_ms": uptime, "temperature_c": temperature,
                "state": state, "inhibit_flags": f"0x{inhibits:08x}",
                "applied_linear_mps": linear, "applied_angular_radps": angular,
                "rx_errors": errors}
    if frame_type == 0x8005:
        if len(payload) < 9:
            raise ProtocolError("DEVICE_STATUS payload가 너무 짧음")
        timestamp, count = struct.unpack_from("<QB", payload)
        _exact(payload, 9 + 9 * count, "DEVICE_STATUS")
        devices = []
        for index in range(count):
            state, updated = struct.unpack_from("<BQ", payload, 9 + index * 9)
            name = DEVICE_NAMES[index] if index < len(DEVICE_NAMES) else f"DEVICE_{index}"
            devices.append({"name": name,
                            "state": DEVICE_STATE_NAMES.get(state, f"UNKNOWN({state})"),
                            "last_update_ms": updated})
        return {"timestamp_ms": timestamp, "devices": devices}
    if frame_type == 0x8006:
        if len(payload) < 16:
            raise ProtocolError("EVENT payload가 너무 짧음")
        timestamp, severity, code, source_length, text_length = struct.unpack_from("<QBIBH", payload)
        _exact(payload, 16 + source_length + text_length, "EVENT")
        start = 16
        try:
            source = payload[start:start + source_length].decode("utf-8")
            text = payload[start + source_length:].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProtocolError("EVENT 문자열이 UTF-8이 아님") from exc
        return {"timestamp_ms": timestamp, "severity": severity, "code": code,
                "source": source, "text": text}
    if frame_type == 0x8007:
        _exact(payload, 128, "MCU_V2_STATUS")
        magic, role, online, version, boot, session, stamp, uid, age, errors = struct.unpack_from(
            "<4sBBHIIQQII", payload)
        if magic != b"MCU2" or role not in (1, 2) or online not in (0, 1) or version != 2:
            raise ProtocolError("MCU_V2_STATUS header 오류")
        names = ("inhibit", "last_command", "link_progress", "driver_progress", "imu_progress",
                 "rx_errors", "sample_drops", "priority_drops", "buffer_depth", "gyro_age_ms",
                 "driver_ack_age_ms", "imu_resets", "rejected", "latest_sequence")
        result = dict(role="control" if role == 1 else "payload", online=bool(online),
                      uid=f"{uid:016x}", boot=boot, session=session, host_stamp_ms=stamp,
                      health_age_ms=age, host_errors=errors,
                      uptime_ms=struct.unpack_from("<Q", payload, 48)[0],
                      temperature_c=struct.unpack_from("<f", payload, 56)[0],
                      transport=payload[116], identity_bound=bool(payload[117]),
                      driver_failures=struct.unpack_from("<I", payload, 120)[0])
        result.update(zip(names, struct.unpack_from("<14I", payload, 60)))
        return result
    raise ProtocolError(f"지원하지 않는 타입: 0x{frame_type:04x}")


def monitor(host, port, connect_timeout, reconnect):
    """Connect to the rover and print telemetry without sending any bytes."""
    delay = 1.0
    while True:
        print(f"[연결 시도] {host}:{port}", flush=True)
        try:
            with socket.create_connection((host, port), timeout=connect_timeout) as sock:
                sock.settimeout(None)
                parser = FrameParser()
                print("[연결 성공] 텔레메트리 수신 대기 중 (종료: Ctrl+C)", flush=True)
                while True:
                    data = sock.recv(4096)
                    if not data:
                        raise ConnectionError("로버가 연결을 종료함")
                    for frame_type, sequence, payload in parser.feed(data):
                        record = {"type": TYPE_NAMES[frame_type], "sequence": sequence}
                        record.update(decode_payload(frame_type, payload))
                        print(json.dumps(record, ensure_ascii=False), flush=True)
        except (OSError, ProtocolError) as exc:
            print(f"[연결/프로토콜 오류] {exc}", file=sys.stderr, flush=True)
            if not reconnect:
                return 1
            print(f"[{delay:.0f}초 후 재접속]", file=sys.stderr, flush=True)
            time.sleep(delay)
            delay = min(delay * 2, 10.0)


def main():
    parser = argparse.ArgumentParser(
        description="실제 로버 GroundLink v1 텔레메트리 읽기 전용 모니터"
    )
    parser.add_argument("host", help="로버 IP 주소 (예: 192.168.1.50)")
    parser.add_argument("--port", type=int, default=7443, help="GroundLink TCP 포트 (기본: 7443)")
    parser.add_argument("--connect-timeout", type=float, default=3.0, help="연결 제한 시간(초)")
    parser.add_argument("--reconnect", action="store_true", help="연결이 끊기면 자동 재접속")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port는 1~65535여야 합니다")
    if args.connect_timeout <= 0:
        parser.error("connect-timeout은 0보다 커야 합니다")
    try:
        return monitor(args.host, args.port, args.connect_timeout, args.reconnect)
    except KeyboardInterrupt:
        print("\n[종료]")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
