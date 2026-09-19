import time
from collections import deque
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class State:
    def __init__(self, config):
        self.config = config
        self.connection = "RECONNECTING"
        self.error = None
        self.status = None
        self.sample = None
        self.last_rx = None
        self.last_status = None
        self.last_sample = None
        self.rx = 0
        self.tx = 0
        self.gaps = 0
        self.pending = {}
        self.events = deque(maxlen=config["display"]["event_limit"])
        self.event_sequence = 0

    def event(self, text, request_id=None):
        self.event_sequence += 1
        self.events.append({"id": self.event_sequence, "time": now(), "text": text, "request_id": request_id})

    def snapshot(self):
        t = time.monotonic()
        age = lambda stamp: None if stamp is None else round(t - stamp, 2)
        active = self.connection == "CONNECTED"
        return {"source": "MOCK / 예시 데이터", "connection": self.connection,
                "error": self.error, "status": self.status, "payload_sample": self.sample,
                "status_age": age(self.last_status), "sample_age": age(self.last_sample),
                "last_rx_age": age(self.last_rx),
                "status_stale": not active or self.last_status is None or t-self.last_status > self.config["display"]["stale_after"],
                "sample_stale": not active or self.last_sample is None or t-self.last_sample > self.config["display"]["stale_after"] or not self.status or self.status.get("payload", {}).get("state") != "MEASURING",
                "rx_messages": self.rx, "tx_messages": self.tx, "data_gaps": self.gaps,
                "requests": list(self.pending.values()), "events": list(self.events)}
