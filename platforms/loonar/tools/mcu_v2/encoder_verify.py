"""Read-only encoder comparison; consumes the existing binary motor sample."""
import csv
import struct
import time


class EncoderVerify:
    def __init__(self, path):
        self.file = open(path, 'x', newline='')
        self.csv = csv.writer(self.file)
        self.csv.writerow(('stamp_ns', 'boot', 'seq', 'valid', 'left_count', 'right_count',
                           'left_qpps', 'right_qpps', 'left_command', 'right_command',
                           'ack_age_ms', 'count_age_ms', 'speed_age_ms', 'driver_errors',
                           'link_failures', 'main_voltage_raw', 'state', 'delta_qpps',
                           'abs_delta_percent_of_command'))
        self.key = None
        self.since = 0
        self.last_stamp = 0
        self.last_feedback = None
        self.n = 0
        self.total = self.worst = 0.0
        self.last_print = 0.0
        print(f'Encoder CSV: {path}', flush=True)

    def feed(self, sample, now_ns=None):
        p = bytes.fromhex(sample['payload'])
        valid, lc, rc, ls, rs, lcmd, rcmd = struct.unpack_from('<I6i', p)
        errors, ack_age, failures, count_age, speed_age = struct.unpack_from('<5I', p, 44)
        stamp = sample['stamp_ns']
        now_ns = time.time_ns() if now_ns is None else now_ns
        key = (sample['boot'], lcmd, rcmd)
        gap = stamp - self.last_stamp
        if key != self.key or gap <= 0 or gap > 250_000_000:
            self.key, self.since = key, stamp
        self.last_stamp = stamp
        fresh = (valid & 3 == 3 and p[42] and ack_age <= 100 and
                 count_age <= 200 and speed_age <= 200 and
                 0 <= now_ns - stamp <= 250_000_000 and errors == 0)
        straight = lcmd == rcmd and lcmd != 0
        state = ('STALE/FAULT' if not fresh else 'STOP/TURN' if not straight
                 else 'SETTLING' if stamp - self.since < 1_000_000_000 else 'STRAIGHT')
        delta = ls - rs
        percent = 100 * abs(delta) / abs(lcmd) if straight else None
        # Do not count repeated snapshots of the same RoboClaw speed response.
        feedback = (sample['boot'], (stamp // 1_000_000) - speed_age)
        if state == 'STRAIGHT' and feedback != self.last_feedback:
            self.n += 1
            self.total += percent
            self.worst = max(self.worst, percent)
        self.last_feedback = feedback
        self.csv.writerow((stamp, sample['boot'], sample['seq'], valid, lc, rc,
                           ls, rs, lcmd, rcmd, ack_age, count_age, speed_age, errors,
                           failures, struct.unpack_from('<H', p, 32)[0], state, delta,
                           '' if percent is None else round(percent, 3)))
        now = time.monotonic()
        if now - self.last_print >= 1:
            comparison = f'{percent:.1f}%' if state == 'STRAIGHT' else 'N/A'
            print(f'ENC {state} cmd L/R={lcmd}/{rcmd} actual={ls}/{rs} qpps '
                  f'count={lc}/{rc} delta={delta} diff={comparison} '
                  f'track_error L/R={ls-lcmd}/{rs-rcmd} '
                  f'valid_n={self.n} mean/max={self.total/max(1,self.n):.1f}/{self.worst:.1f}%', flush=True)
            self.file.flush()
            self.last_print = now
        return state

    def close(self):
        self.file.close()
        print(f'Encoder summary: valid speed responses={self.n}; '
              f'mean/max |L-R| / |command|={self.total/max(1,self.n):.2f}/{self.worst:.2f}% '
              '(stable straight samples only; no automatic pass/fail)', flush=True)
