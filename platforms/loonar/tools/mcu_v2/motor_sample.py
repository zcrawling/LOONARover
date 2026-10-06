"""Decode the existing 64-byte motor snapshot. Left=M2, right=M1.

Current is motor winding current, not battery current. Only count/speed have
per-query ages in this protocol; other fields are cached and valid for <500 ms.
"""
import struct


def decode_motor(payload):
    if len(payload) != 64:
        raise ValueError("motor snapshot must be 64 bytes")
    valid, lc, rc, ls, rs, lcmd, rcmd = struct.unpack_from("<I6i", payload)
    li, ri, lp, rp, main, logic, temperature = struct.unpack_from("<4h3H", payload, 28)
    error, ack_age, failures, count_age, speed_age = struct.unpack_from("<5I", payload, 44)
    result = dict(valid_mask=valid, left_count=lc, right_count=rc,
                  left_speed_qpps=ls, right_speed_qpps=rs,
                  left_command_qpps=lcmd, right_command_qpps=rcmd,
                  left_current_a=li / 100, right_current_a=ri / 100,
                  left_pwm_raw=lp, right_pwm_raw=rp,
                  main_voltage_v=main / 10, logic_voltage_v=logic / 10,
                  temperature_c=temperature / 10, ack_seen=bool(payload[42]),
                  error=error, ack_age_ms=ack_age, failures=failures,
                  count_age_ms=count_age, speed_age_ms=speed_age,
                  timestamp_source="MCU_SNAPSHOT_MAPPED_TO_PI_REALTIME",
                  current_age_ms="unknown; valid flag means <500ms")
    for bit, name in enumerate(("counts", "speed", "current", "main_voltage",
                                "logic_voltage", "temperature", "error", "pwm")):
        result[name + "_valid"] = bool(valid & (1 << bit))
    return result
