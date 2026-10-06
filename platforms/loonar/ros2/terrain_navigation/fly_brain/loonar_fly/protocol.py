"""Bounded request tracking; no dependence on synchronized PC/Pi clocks."""
from collections import OrderedDict
import math
import uuid


class Requests:
    def __init__(self, ttl=0.75):
        self.session = uuid.uuid4().hex
        self.sequence = 0
        self.pending = OrderedDict()
        self.accepted = 0
        self.ttl = ttl

    def issue(self, now, oldest_sensor):
        self.sequence += 1
        self.pending[self.sequence] = oldest_sensor
        while self.pending and (len(self.pending) > 16 or
                                now - next(iter(self.pending.values())) > self.ttl):
            self.pending.popitem(last=False)
        return {"schema": 1, "session": self.session, "sequence": self.sequence}

    def accept(self, response, now):
        if response.get("schema") != 1 or response.get("session") != self.session:
            raise ValueError("wrong schema/session")
        seq = response.get("sequence")
        if type(seq) is not int or seq <= self.accepted or seq not in self.pending:
            raise ValueError("unknown/replayed/out-of-order result")
        stamp = self.pending[seq]
        if not math.isfinite(now) or not 0 <= now - stamp <= self.ttl:
            raise ValueError("expired sensor-to-result latency")
        self.accepted = seq
        while self.pending and next(iter(self.pending)) <= seq:
            self.pending.popitem(last=False)
        return stamp
