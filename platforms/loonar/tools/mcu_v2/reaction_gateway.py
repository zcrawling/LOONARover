"""Nonblocking configuration/START handshake on the existing serial owner."""
import time
from .reaction_wheel import CONFIG, Settings, status
from .wire import Kind


class ReactionController:
    def __init__(self, link, report):
        self.link, self.report = link, report
        self.pending = None
        self.running = False
        self.saw_active = False
        self.last_state = None

    def cancel(self):
        if self.pending or self.running:
            self.report('CANCELLED')
        self.pending = None
        self.running = self.saw_active = False

    def request(self, raw):
        if self.pending or self.running:
            self.report('ERROR,busy'); return
        try:
            if len(raw) != 41 or raw[0] not in (1,2):
                raise ValueError('bad_request')
            settings = Settings(*CONFIG.unpack(raw[1:]))
            settings.encode()
        except (ValueError, TypeError):
            self.report('ERROR,bad_settings'); return
        sequence = self.link.send(Kind.REACTION_CONFIGURE, raw[1:])
        self.pending = ('CONFIGURE', sequence, raw[0], time.monotonic()+2)
        self.report('CONFIGURING')

    def receive(self, frame):
        if frame.kind == Kind.RESULT and self.pending and frame.sequence == self.pending[1]:
            phase, _, side, _ = self.pending
            expected = Kind.REACTION_CONFIGURE if phase == 'CONFIGURE' else Kind.REACTION
            try:
                self.link.check_result(frame, expected)
            except ValueError:
                self.pending = None
                self.report('ERROR,mcu_rejected'); return
            if phase == 'CONFIGURE':
                sequence = self.link.send(Kind.REACTION, bytes([side]))
                self.pending = ('START', sequence, side, time.monotonic()+2)
            else:
                self.pending = None
                self.running = True
                self.saw_active = False
                self.last_state = None
                self.report('ACCEPTED')
        elif frame.kind == Kind.REACTION_STATUS:
            value = status(frame.payload)
            if self.running:
                self.saw_active |= value['active']
                if value['state'] != self.last_state:
                    self.last_state = value['state']
                    self.report(f"{value['state']},{value['direction']},{value['esc_us']},{value['servo_us']}")
                if self.saw_active and not value['active']:
                    self.running = False
                    self.report('END' if self.last_phase == 'SERVO_HOLD' else 'INTERRUPTED')
                if value['active']:
                    self.last_phase = value['state']

    def tick(self):
        if self.pending and time.monotonic() >= self.pending[3]:
            self.pending = None
            self.link.send(Kind.STOP)
            self.report('ERROR,response_timeout')
