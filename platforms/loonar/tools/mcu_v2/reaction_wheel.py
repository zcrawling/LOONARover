"""One manual reaction cycle over the exclusive Control USB connection.

Stop ground-support first. This tool never opens a second serial owner.
A lost connection/heartbeat requests MCU neutral; it does not measure RPM.
"""
import argparse
from dataclasses import asdict, dataclass
import json
import struct
import time

from .config import load
from .link import Link
from .wire import Kind

CONFIG = struct.Struct('<8H6I')
STATUS = struct.Struct('<BBBBHHII')
STATES = ('PREPARING', 'READY', 'FIRST', 'SECOND', 'NEUTRAL_WAIT', 'SERVO_HOLD')


@dataclass
class Settings:
    esc_neutral: int = 1488
    servo_neutral: int = 1500
    left_first_offset: int = 25
    left_second_offset: int = 50
    right_first_offset: int = 25
    right_second_offset: int = 50
    servo_left: int = 800
    servo_right: int = 2200
    left_first_ms: int = 5000
    right_first_ms: int = 10000
    second_ms: int = 10000
    servo_delay_ms: int = 10
    servo_hold_ms: int = 3000
    prepare_ms: int = 5000

    def encode(self):
        values = asdict(self)
        if any(type(v) is not int for v in values.values()):
            raise ValueError('settings must be integer microseconds/milliseconds')
        if not (1148 <= self.esc_neutral <= 1832
                and all(800 <= v <= 2200 for v in (self.servo_neutral,self.servo_left,self.servo_right))
                and 0 < self.left_first_offset <= self.left_second_offset <= 1832-self.esc_neutral
                and 0 < self.right_first_offset <= self.right_second_offset <= self.esc_neutral-1148
                and 0 < self.left_first_ms <= 60000 and 0 < self.right_first_ms <= 60000
                and 0 < self.second_ms <= 60000 and 10 <= self.servo_delay_ms <= 10000
                and 0 < self.servo_hold_ms <= 10000 and 5000 <= self.prepare_ms <= 60000):
            raise ValueError('reaction settings outside supported pulse/time limits')
        return CONFIG.pack(*values.values())


def status(payload):
    if len(payload) != STATUS.size:
        raise ValueError('invalid reaction status size')
    state, direction, active, reserved, esc, servo, elapsed, cycle = STATUS.unpack(payload)
    if state >= len(STATES) or direction > 2 or active > 1 or reserved:
        raise ValueError('invalid reaction status fields')
    return dict(state=STATES[state], direction=direction, active=bool(active),
                esc_us=esc, servo_us=servo, phase_elapsed_ms=elapsed, cycle=cycle)


def run(link, side, settings):
    settings.encode()  # Validate before configuration changes or starts.
    link.send(Kind.STOP)
    if side == 'stop':
        return
    seq = link.send(Kind.REACTION_CONFIGURE, settings.encode())
    link.check_result(link.wait(Kind.RESULT, 2, seq), Kind.REACTION_CONFIGURE)
    start_seq = None
    last_health = 0
    previous = None
    accepted = False
    duration = (settings.prepare_ms + max(settings.left_first_ms, settings.right_first_ms)
                + settings.second_ms + settings.servo_delay_ms + settings.servo_hold_ms)
    deadline = time.monotonic()+duration/1000+10
    while time.monotonic() < deadline:
        if time.monotonic()-last_health >= .1:
            link.send(Kind.HEALTH_REQUEST)
            last_health = time.monotonic()
        for frame in link.poll():
            if frame.kind == Kind.RESULT and frame.sequence == start_seq:
                link.check_result(frame, Kind.REACTION)
                accepted = True
            if frame.kind != Kind.REACTION_STATUS:
                continue
            value = status(frame.payload)
            if value['state'] != previous:
                print(json.dumps(value), flush=True)
                previous = value['state']
            if start_seq is None and value['state'] == 'READY':
                start_seq = link.send(Kind.REACTION, bytes([1 if side == 'left' else 2]))
            elif accepted and value['state'] == 'READY':
                return
        time.sleep(.002)
    raise TimeoutError('reaction cycle did not complete')


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('side', choices=('left','right','stop'))
    parser.add_argument('--registry', default='/home/loonar/loonar-motor-bench/control.json')
    parser.add_argument('--config', help='JSON object overriding Settings defaults; not persisted in MCU flash')
    args = parser.parse_args()
    settings = Settings(**(json.load(open(args.config)) if args.config else {}))
    settings.encode()
    link = Link(load(args.registry, 'control'))
    try:
        run(link, args.side, settings)
    finally:
        link.close()  # Sends STOP on success, failure and Ctrl+C.


if __name__ == '__main__':
    main()
