"""ROS-independent causal features, signed wheel integration and model inference."""
from collections import deque
from dataclasses import asdict, dataclass
import math

import numpy as np

SCHEMA = 'loonar-cv-v1'
AXES = ('ax', 'ay', 'az', 'gx', 'gy', 'gz')


@dataclass(frozen=True)
class Config:
    # Experimental settings, not calibrated vehicle limits.
    window_s: float = 1.0
    sample_hz: float = 100.0
    max_gap_s: float = 0.05
    min_encoder_distance_m: float = 0.02
    min_speed_mps: float = 0.005
    hp_tau_s: float = 0.15
    preprocessing: str = 'both'

    def __post_init__(self):
        for name in ('window_s', 'sample_hz', 'max_gap_s', 'hp_tau_s'):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f'{name} must be finite and positive')
        if self.window_s * self.sample_hz < 4:
            raise ValueError('Window must contain at least four resampled points')
        for name in ('min_encoder_distance_m', 'min_speed_mps'):
            if not math.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f'{name} must be finite and positive')
        if self.preprocessing not in ('raw', 'highpass', 'both'):
            raise ValueError('preprocessing must be raw, highpass, or both')


def stats(x):
    x = np.asarray(x, dtype=float)
    mean = float(np.mean(x))
    centered = x - mean
    variance = float(np.mean(centered ** 2))
    return dict(mean=mean, std=math.sqrt(variance), rms=float(np.sqrt(np.mean(x*x))),
                peak_to_peak=float(np.ptp(x)), mad=float(np.median(np.abs(x-np.median(x)))),
                skewness=float(np.mean(centered**3)/variance**1.5) if variance > 1e-20 else 0.0,
                excess_kurtosis=float(np.mean(centered**4)/variance**2-3) if variance > 1e-20 else 0.0,
                difference_rms=float(np.sqrt(np.mean(np.diff(x)**2))))


def highpass(x, dt, tau):
    # Window-local initialization. Identical offline/live, uses no future frames.
    y = np.zeros_like(x)
    alpha = tau / (tau + dt)
    for i in range(1, len(x)):
        y[i] = alpha * (y[i-1] + x[i] - x[i-1])
    return y


def integrate_wheel(wheel, start, end):
    """vx at t_i describes the encoder increment over (t_(i-1), t_i]."""
    return sum(max(0.0, min(end, b[0])-max(start, a[0])) * b[1]
               for a, b in zip(wheel, wheel[1:]))


def features(imu, wheel, end, cfg):
    start = end - cfg.window_s
    imu = np.asarray(imu, dtype=float)
    wheel = np.asarray(wheel, dtype=float)
    for data, columns, name in ((imu, 7, 'imu'), (wheel, 3, 'wheel')):
        if data.ndim != 2 or data.shape[1] != columns or len(data) < 2:
            return None, name + '_window_insufficient'
        if not np.isfinite(data).all() or np.any(np.diff(data[:, 0]) <= 0):
            return None, name + '_invalid_time_or_value'
        if data[0, 0] > start or end-data[-1, 0] > cfg.max_gap_s or data[-1, 0] > end+1e-6:
            return None, name + '_coverage'
        inside = data[max(0, np.searchsorted(data[:, 0], start)-1):]
        if np.max(np.diff(inside[:, 0])) > cfg.max_gap_s:
            return None, name + '_gap'
    inside_wheel = wheel[wheel[:, 0] >= start]
    ds = integrate_wheel(wheel, start, end)
    if abs(ds) < cfg.min_encoder_distance_m:
        return None, 'small_encoder_distance'
    if np.any(inside_wheel[:, 1] > cfg.min_speed_mps) and np.any(inside_wheel[:, 1] < -cfg.min_speed_mps):
        return None, 'direction_reversal'
    # Integer count makes resampling deterministic across bag and runtime.
    grid = np.linspace(start, end, round(cfg.window_s*cfg.sample_hz)+1)
    result = {}
    for i, axis in enumerate(AXES):
        values = np.interp(grid, imu[:, 0], imu[:, i+1])
        versions = {}
        if cfg.preprocessing in ('raw', 'both'):
            versions['raw'] = values
        if cfg.preprocessing in ('highpass', 'both'):
            versions['hp'] = highpass(values, cfg.window_s/(len(grid)-1), cfg.hp_tau_s)
        for version, sequence in versions.items():
            result.update({f'{axis}_{version}_{k}': v for k, v in stats(sequence).items()})
    for col, name in ((1, 'encoder_vx'), (2, 'encoder_wz')):
        result.update({name+'_'+k: v for k, v in stats(np.interp(grid, wheel[:, 0], wheel[:, col])).items()})
    return result, 'ok'


class Predictor:
    def __init__(self, model, cfg, profile_id, min_c=0.0, max_c=2.0, max_z=6.0, min_support=0.05):
        if not (math.isfinite(min_c) and math.isfinite(max_c) and 0 <= min_c <= 1 <= max_c):
            raise ValueError('C bounds must include baseline 1 and be finite/nonnegative')
        if not math.isfinite(max_z) or max_z <= 0:
            raise ValueError('max_z must be positive')
        if not math.isfinite(min_support) or not 0 <= min_support <= 1:
            raise ValueError('min_support must be between zero and one')
        self.model, self.cfg = model, cfg
        self.min_c, self.max_c, self.max_z = min_c, max_c, max_z
        self.min_support = min_support
        if model is not None:
            if model['schema'] != SCHEMA or model['config'] != asdict(cfg) or model['profile_id'] != profile_id:
                raise ValueError('Model feature config/profile mismatch')
            n = len(model['feature_names'])
            if n == 0 or len(set(model['feature_names'])) != n:
                raise ValueError('Invalid feature schema')
            for key in ('mean', 'scale', 'coef'):
                a = np.asarray(model[key], dtype=float)
                if a.shape != (n,) or not np.isfinite(a).all():
                    raise ValueError('Invalid model array: ' + key)
            if np.any(np.asarray(model['scale']) <= 0) or not math.isfinite(model['intercept']):
                raise ValueError('Invalid model scale/intercept')

    def predict(self, values):
        if self.model is None:
            return 1.0, 0.0, 'no_model'
        m = self.model
        if set(values) != set(m['feature_names']):
            return 1.0, 0.0, 'feature_schema_mismatch'
        x = np.asarray([values[k] for k in m['feature_names']])
        z = (x - m['mean']) / m['scale']
        if not np.isfinite(z).all() or np.max(np.abs(z)) > self.max_z:
            return 1.0, 0.0, 'out_of_training_support'
        c = float(z @ m['coef'] + m['intercept'])
        if not math.isfinite(c) or not self.min_c <= c <= self.max_c:
            return 1.0, 0.0, 'c_out_of_range'
        # This is feature support, NOT calibrated prediction probability.
        score = max(0.0, 1-float(np.max(np.abs(z)))/self.max_z)
        if score < self.min_support:
            return 1.0, score, 'low_feature_support'
        return c, score, 'ok'


class Engine:
    def __init__(self, cfg, predictor):
        self.cfg, self.predictor = cfg, predictor
        self.imu, self.wheel = deque(), deque()

    def add(self, kind, sample):
        buf = self.imu if kind == 'imu' else self.wheel
        sample = tuple(float(v) for v in sample)
        if not all(math.isfinite(v) for v in sample) or (buf and sample[0] <= buf[-1][0]):
            self.imu.clear()
            self.wheel.clear()
            return False
        buf.append(sample)
        cutoff = sample[0] - self.cfg.window_s - self.cfg.max_gap_s
        while len(buf) > 2 and buf[1][0] < cutoff:
            buf.popleft()
        # Memory bound even if one stream keeps running while another stops.
        while len(buf) > 10000:
            buf.popleft()
        return True

    def estimate(self, end):
        # Future-stamped samples are never admitted to this window.
        f, reason = features([s for s in self.imu if s[0] <= end],
                             [s for s in self.wheel if s[0] <= end], end, self.cfg)
        if f is None:
            return 1.0, 0.0, reason, None
        c, score, reason = self.predictor.predict(f)
        return c, score, reason, f
