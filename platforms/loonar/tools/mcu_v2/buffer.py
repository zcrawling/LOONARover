"""Bounded RAM receive buffer. ACK means accepted in RAM, never saved to disk."""

from collections import deque


class ReceiveBuffer:
    def __init__(self, capacity=2048):
        self.capacity = capacity
        self.boot = None
        self.ack = 0
        self.pending = {}
        self.ready = deque()
        self.missing = 0
        self.full = 0

    def begin(self, boot, oldest):
        if boot != self.boot:
            self.boot = boot
            self.ack = 0
            self.pending.clear()
            self.ready.clear()
        self.advance(oldest)

    def accept(self, frame):
        if frame.boot != self.boot:
            raise ValueError("sample belongs to another MCU boot")
        if frame.sequence <= self.ack or frame.sequence in self.pending:
            return False
        if len(self.pending) + len(self.ready) >= self.capacity:
            self.full += 1
            return False  # Do not ACK; the MCU retains this record for retry.
        self.pending[frame.sequence] = frame
        self.advance()
        return True

    def advance(self, oldest=0):
        # Only skip a gap when the MCU reports it no longer retains that range.
        while self.ack + 1 in self.pending or self.ack + 1 < oldest:
            seq = self.ack + 1
            frame = self.pending.pop(seq, None)
            if frame is not None:
                self.ready.append(frame)
                self.ack = seq
            else:
                next_present = min((n for n in self.pending if n > seq), default=oldest)
                end = min(oldest, next_present)
                self.missing += end - seq
                self.ack = end - 1
        return self.ack

    def pop(self):
        return self.ready.popleft() if self.ready else None
