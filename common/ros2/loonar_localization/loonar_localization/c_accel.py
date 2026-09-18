"""Experimental acceleration-window C estimation. No V1/TF/command writes."""
from dataclasses import dataclass
import numpy as np


@dataclass
class CConfig:
    bias_seconds: float = 1.
    max_gap: float = .08
    min_velocity: float = .02
    min_excitation: float = .06
    min_denominator: float = .02
    min_samples: int = 15
    c_min: float = .2
    c_max: float = 1.8
    max_c_difference: float = .25
    max_bias_std: float = .08

    def __post_init__(self):
        if min(self.bias_seconds, self.max_gap, self.min_velocity, self.min_excitation,
               self.min_denominator, self.max_c_difference, self.max_bias_std) <= 0:
            raise ValueError('C thresholds must be positive')
        if self.min_samples < 3 or not 0 < self.c_min < self.c_max:
            raise ValueError('invalid C bounds/sample count')


def fit_window(rows, c, backwards=False):
    """Reverse integration uses final confirmed zero velocity, never C_acc."""
    if len(rows) < c.min_samples:
        return None, 'insufficient_samples', []
    d = np.array(rows); t,v,a = d.T
    dt = np.diff(t)
    if np.any(dt <= 0) or np.any(dt > c.max_gap):
        return None, 'timestamp_gap', []
    vi = np.r_[0., np.cumsum((a[1:]+a[:-1])*.5*dt)]
    if backwards:
        vi -= vi[-1]
    mask = abs(v) >= c.min_velocity
    denominator = float(v[mask]@v[mask])
    if mask.sum() < c.min_samples or denominator < c.min_denominator or np.ptp(v) < c.min_excitation:
        return None, 'UNOBSERVABLE', vi.tolist()
    raw = float(v[mask]@vi[mask]/denominator)
    return raw, 'ok', vi.tolist()


class CEstimator:
    def __init__(self, config=None):
        self.c = config or CConfig()
        self.phase = 'STOP'; self.bias_rows = []; self.bias = None
        self.acc_rows = []; self.dec_rows = []; self.dec_pending = False
        self.c_acc = self.c_dec = None; self.c_valid = False
        self.run_bad = False; self.reason = 'await_stationary_bias'; self.unreliable = False
        self.vi = 0.; self.prev = None; self.pose = np.zeros(3)
        self.last_window = None

    def finish(self, backwards):
        rows = self.dec_rows if backwards else self.acc_rows
        raw, reason, vi = fit_window(rows, self.c, backwards)
        self.last_window = dict(kind='deceleration' if backwards else 'acceleration',
                                rows=[dict(t=t,vx_encoder=v,a_corrected=a,v_imu=x)
                                      for (t,v,a),x in zip(rows,vi)], C_raw=raw, reason=reason)
        if backwards:
            self.c_dec = raw
            self.unreliable = (self.run_bad or raw is None or self.c_acc is None or
                               not self.c.c_min <= raw <= self.c.c_max or
                               abs(raw-self.c_acc) > self.c.max_c_difference)
            if self.unreliable:
                self.c_valid = False
                self.reason = 'C_dec_unreliable:'+reason
        else:
            self.c_acc = raw
            self.c_valid = (not self.run_bad and raw is not None and self.c.c_min <= raw <= self.c.c_max)
            self.reason = 'C_acc_valid' if self.c_valid else 'C_acc_invalid:'+reason

    def update(self, t, v, a, yaw, wz, phase, stationary, valid=True, initial_xy=None):
        if phase not in ('STOP','ACCEL','CRUISE','DECEL'):
            raise ValueError('unknown experiment phase')
        finite = np.isfinite([t,v,a,yaw,wz]).all()
        if not finite:
            raise ValueError('nonfinite input')
        dt = 0. if self.prev is None else t-self.prev[0]
        if dt < 0 or (self.prev is not None and dt == 0):
            raise ValueError('nonmonotonic time')
        gap = self.prev is not None and dt > self.c.max_gap
        if phase == 'ACCEL' and self.phase != 'ACCEL':
            if self.phase != 'STOP':
                valid = False
            self.acc_rows=[]; self.dec_rows=[]; self.dec_pending=False
            self.c_acc=self.c_dec=None; self.c_valid=False; self.unreliable=False
            self.vi=0.; self.run_bad=(self.bias is None or not stationary or gap or not valid)
            self.reason='collect_acceleration' if not self.run_bad else 'invalid_start_or_bias'
            self.last_window=None
        if not valid or gap:
            self.c_valid=False
            self.reason='invalid_acceleration_or_timing'
            if phase != 'STOP' or self.dec_pending or self.phase=='DECEL':self.run_bad=True
        if self.phase=='ACCEL' and phase!='ACCEL':
            # Include boundary sample to cover the full ramp interval.
            self.acc_rows.append((t,v,a-(self.bias or 0.)))
            self.finish(False)
        if phase=='DECEL' and self.phase!='DECEL':
            self.dec_rows=[]; self.dec_pending=True
        if self.phase=='DECEL' and phase not in ('DECEL','STOP'):
            self.run_bad=True; self.c_valid=False; self.reason='deceleration_without_stop'
        corrected = a-(self.bias or 0.)
        if phase=='ACCEL':
            self.acc_rows.append((t,v,corrected))
            if len(self.acc_rows)>1:
                old=self.acc_rows[-2]; self.vi+=(corrected+old[2])*.5*(t-old[0])
        if self.dec_pending:
            self.dec_rows.append((t,v,corrected))
            if phase=='STOP' and stationary and valid:
                self.finish(True); self.dec_pending=False
        # Freeze calibration during motion and pending deceleration evaluation.
        if phase!='STOP':
            self.bias_rows=[]
        if phase=='STOP' and not self.dec_pending:
            if stationary and valid and not gap:
                self.bias_rows.append((t,a))
                while len(self.bias_rows)>2 and self.bias_rows[1][0]<=t-self.c.bias_seconds:
                    self.bias_rows.pop(0)
                if t-self.bias_rows[0][0]>=self.c.bias_seconds*.99:
                    values=np.array([x[1] for x in self.bias_rows])
                    if values.std()<=self.c.max_bias_std:self.bias=float(values.mean())
                    else:self.bias=None
            else:
                self.bias_rows=[];self.bias=None
        applied = self.c_acc if self.c_valid else 1.
        vc = applied*v
        if self.prev is None:
            if initial_xy is not None:self.pose[:2]=initial_xy
        elif not gap:
            delta=np.arctan2(np.sin(yaw-self.prev[2]),np.cos(yaw-self.prev[2]))
            mid=self.prev[2]+delta*.5; distance=.5*(self.prev[1]+vc)*dt
            self.pose[:2]+=distance*np.array([np.cos(mid),np.sin(mid)])
        self.pose[2]=yaw
        self.prev=(t,vc,yaw);self.phase=phase
        return dict(t=t,phase=phase,C_acc=self.c_acc,C_dec=self.c_dec,C_valid=bool(self.c_valid),
                    C_applied=applied,C_unreliable=bool(self.unreliable or self.run_bad),
                    v_imu=self.vi if phase=='ACCEL' else None,vx_encoder=v,vx_corrected=vc,
                    a_corrected=corrected,accel_bias=self.bias,acceleration_valid=bool(valid),
                    reason=self.reason,pose=self.pose.tolist(),wz=wz)
