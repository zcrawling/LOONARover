"""Causal estimator core. SI units; all vectors are in base_link."""
from collections import deque
from dataclasses import dataclass
from enum import Enum
import math
import numpy as np
from .integration import integrate_trajectory


class Primitive(str, Enum):
    UNKNOWN = 'UNKNOWN'
    STOP = 'STOP'
    STRAIGHT_SLOW = 'STRAIGHT_SLOW'
    STRAIGHT_NORMAL = 'STRAIGHT_NORMAL'
    ROTATE_LEFT = 'ROTATE_LEFT'
    ROTATE_RIGHT = 'ROTATE_RIGHT'


class PrimitiveManager:
    """Prior from commands, never evidence of actual motion or a command publisher."""
    def __init__(self, slow_speed=.075):
        self.slow_speed = slow_speed
        self.state = Primitive.UNKNOWN

    def observe(self, v, w):
        if not np.isfinite([v, w]).all():
            self.state = Primitive.UNKNOWN
        elif abs(v) < 1e-6 and abs(w) < 1e-6:
            self.state = Primitive.STOP
        elif abs(w) < 1e-6:
            self.state = Primitive.STRAIGHT_SLOW if abs(v) <= self.slow_speed else Primitive.STRAIGHT_NORMAL
        elif abs(v) < 1e-6:
            self.state = Primitive.ROTATE_LEFT if w > 0 else Primitive.ROTATE_RIGHT
        else:
            self.state = Primitive.UNKNOWN
        return self.state

    @staticmethod
    def plan(relative_yaw, distance):
        """Return a prior plan; signed targets, no actuator side effects."""
        plan = []
        if abs(relative_yaw) > 1e-9:
            plan += [(Primitive.ROTATE_LEFT if relative_yaw > 0 else Primitive.ROTATE_RIGHT, relative_yaw), (Primitive.STOP, 0.)]
        if abs(distance) > 1e-9:
            plan += [(Primitive.STRAIGHT_NORMAL, distance), (Primitive.STOP, 0.)]
        return plan or [(Primitive.STOP, 0.)]


@dataclass
class Config:
    # Provisional diagnostic thresholds, not calibrated mechanical limits.
    stationary_window: float = 1.
    max_gap: float = .08
    stop_v: float = .005
    stop_gyro: float = .025
    stop_gyro_std: float = .01
    stop_accel_std: float = .06
    bias_tau: float = 10.
    yaw_threshold: float = .05
    accel_sigma: float = .068
    score_threshold: float = 3.
    shock_threshold: float = 2.
    suspect_hold: float = .25
    recovery_hold: float = 1.
    base_v_variance: float = .01
    base_w_variance: float = .001
    stationary_enabled: bool = True
    zero_update_enabled: bool = True
    monitor_enabled: bool = True
    constraints_enabled: bool = True


@dataclass
class Sample:
    t: float
    vx: float
    wheel_wz: float
    gyro: np.ndarray
    accel: np.ndarray
    # True only for externally validated gravity/lever-arm compensated acceleration.
    acceleration_valid: bool = False
    wheel_speeds: tuple = ()


class StationaryDetector:
    def __init__(self, config):
        self.c = config
        self.samples = deque()

    def reset(self):
        self.samples.clear()

    def update(self, s, bias, prior):
        q = self.samples
        if q and (s.t <= q[-1].t or s.t-q[-1].t > self.c.max_gap):
            q.clear()
        q.append(s)
        while len(q) > 2 and q[1].t <= s.t-self.c.stationary_window:
            q.popleft()
        if not self.c.stationary_enabled:
            return False, 'stationary_detector_disabled'
        if len(q) < 3 or s.t-q[0].t < self.c.stationary_window*.99:
            return False, 'insufficient_contiguous_window'
        gyro = np.array([x.gyro for x in q])-bias
        accel = np.array([x.accel for x in q])
        wheels = [max([abs(x.vx)] + [abs(v) for v in x.wheel_speeds]) for x in q]
        stable = (max(wheels) <= self.c.stop_v and
                  np.max(np.linalg.norm(gyro, axis=1)) <= self.c.stop_gyro and
                  np.max(np.std(gyro, axis=0)) <= self.c.stop_gyro_std and
                  np.max(np.std(accel, axis=0)) <= self.c.stop_accel_std)
        if stable and prior not in [Primitive.STOP, Primitive.UNKNOWN]:
            return True, 'sensor_window_stationary_command_conflict'
        return bool(stable), 'sensor_window_stationary' if stable else 'motion_or_variance'


class Monitor:
    def __init__(self, c):
        self.c = c
        self.since = None
        self.clear_since = None
        self.state = 'VALID'
        self.filtered_yaw = 0.
        self.filtered_accel = None
        self.filtered_v = None

    def update(self, s, wz, dt, prior):
        alpha = -math.expm1(-dt/.25)
        self.filtered_yaw += alpha*(s.wheel_wz-wz-self.filtered_yaw)
        reasons = []
        score = None
        if abs(self.filtered_yaw) > self.c.yaw_threshold:
            reasons.append('wheel_gyro_yaw_inconsistency')
        # Causal low-pass velocity derivative. Never use gravity-bearing proxy here.
        if s.acceleration_valid:
            old = s.vx if self.filtered_v is None else self.filtered_v
            self.filtered_v = old + alpha*(s.vx-old)
            self.filtered_accel = s.accel[0] if self.filtered_accel is None else self.filtered_accel+alpha*(s.accel[0]-self.filtered_accel)
            score = abs((self.filtered_v-old)/dt-self.filtered_accel)/self.c.accel_sigma
            if score > self.c.score_threshold:
                reasons.append('longitudinal_inconsistency')
        else:
            self.filtered_v = self.filtered_accel = None
        if abs(np.linalg.norm(s.accel)-9.80665) > self.c.shock_threshold and not s.acceleration_valid:
            reasons.append('vertical_or_body_shock')
        if reasons:
            self.clear_since = None
            if self.since is None:
                self.since = s.t
            self.state = 'SUSPECT'
            if s.t-self.since >= self.c.suspect_hold:
                self.state = 'CONTACT_LOSS_SUSPECT' if 'vertical_or_body_shock' in reasons else 'DEGRADED'
        else:
            self.since = None
            if self.clear_since is None:
                self.clear_since = s.t
            if s.t-self.clear_since >= self.c.recovery_hold:
                self.state = 'VALID'
        if not self.c.monitor_enabled:
            return 'UNKNOWN', .2, ['monitor_disabled'], score
        confidence = {'VALID': 1., 'SUSPECT': .5, 'DEGRADED': .1, 'CONTACT_LOSS_SUSPECT': .05}[self.state]
        return self.state, confidence, reasons, score


class Estimator:
    def __init__(self, config=None, bias=None):
        self.c = config or Config()
        if min(self.c.stationary_window, self.c.max_gap, self.c.bias_tau, self.c.accel_sigma) <= 0:
            raise ValueError('windows, time constants and sigma must be positive')
        self.bias = np.array(bias if bias is not None else [0., 0., 0.], dtype=float)
        self.pose = np.zeros(3)
        self.baseline = np.zeros(3)
        self.cov = np.zeros((3, 3))
        self.detector = StationaryDetector(self.c)
        self.monitor = Monitor(self.c)
        self.prev = None
        self.prev_velocity = None
        self.wheel_distance = 0.
        self.last = None

    @staticmethod
    def integrate(pose, v0, v1, w0, w1, dt):
        return integrate_trajectory([0., dt], [v0, v1], [w0, w1], pose)[-1]

    def update(self, s, prior=Primitive.UNKNOWN):
        numbers = [s.t, s.vx, s.wheel_wz, *s.gyro, *s.accel, *s.wheel_speeds]
        if not np.isfinite(numbers).all():
            raise ValueError('non-finite sensor data')
        if self.prev is not None and s.t <= self.prev.t:
            raise ValueError('non-monotonic timestamp')
        dt = 0. if self.prev is None else s.t-self.prev.t
        gap = dt > self.c.max_gap
        if gap:
            self.detector.reset()
            self.monitor = Monitor(self.c)
            self.cov += np.diag([dt*self.c.base_v_variance]*2+[dt*self.c.base_w_variance])
        stationary, stationary_reason = self.detector.update(s, self.bias, prior)
        if stationary and self.c.zero_update_enabled:
            measured = np.mean([x.gyro for x in self.detector.samples], axis=0)
            self.bias += -math.expm1(-dt/self.c.bias_tau)*(measured-self.bias)
        wz = s.gyro[2]-self.bias[2]
        state, confidence, reasons, score = self.monitor.update(s, wz, max(dt, .001), prior)
        if gap:
            state, confidence = 'DEGRADED', .05
            reasons.append('sensor_gap_no_integration')
        if prior in [Primitive.ROTATE_LEFT, Primitive.ROTATE_RIGHT]:
            confidence = min(confidence, .3)
            reasons.append('rotate_translation_uncertain')
        zero = stationary and self.c.zero_update_enabled
        vout, wout = (0., 0.) if zero else (s.vx, wz)
        if self.prev is not None and not gap:
            self.pose = self.integrate(self.pose, *[self.prev_velocity[0], vout, self.prev_velocity[1], wout], dt)
            self.baseline = self.integrate(self.baseline, self.prev.vx, s.vx, self.prev.wheel_wz, s.wheel_wz, dt)
            self.wheel_distance += dt*(abs(self.prev.vx)+abs(s.vx))/2
            # Model uncertainty, not an empirically calibrated covariance estimate.
            theta = self.pose[2]; ds = dt*(self.prev_velocity[0]+vout)/2
            F = np.eye(3); F[0, 2] = -ds*math.sin(theta); F[1, 2] = ds*math.cos(theta)
            self.cov = F@self.cov@F.T + np.diag([self.c.base_v_variance]*2+[self.c.base_w_variance])*dt/max(confidence, .01)
        nhc = self.c.constraints_enabled and prior in [Primitive.STRAIGHT_SLOW, Primitive.STRAIGHT_NORMAL] and state == 'VALID'
        self.prev, self.prev_velocity = s, (vout, wout)
        self.last = dict(t=s.t, pose=self.pose.tolist(), encoder_pose=self.baseline.tolist(), bias=self.bias.tolist(), vx=vout, wz=wout,
                         encoder_vx=s.vx, yaw_residual=s.wheel_wz-wz, stationary=stationary, stationary_reason=stationary_reason,
                         zero_update=zero, state=state, confidence=confidence, covariance=self.cov.tolist(), reasons=reasons,
                         longitudinal_score=score, acceleration_valid=s.acceleration_valid, nhc_weight=confidence if nhc else 0.,
                         nhc_applied=False, primitive=prior.value, wheel_distance=self.wheel_distance)
        return self.last


class PrimitiveSequence:
    """Feedback-driven rotate/stop/straight/stop request state machine.

    Returns motion requests to an autonomy caller, never executes them. Distance
    completion is DR-based and therefore not an independent actual-distance bound.
    """
    def __init__(self, slow=.05, normal=.1, angular=.15, distance_tolerance=.01, yaw_tolerance=.02):
        if min(slow, normal, angular, distance_tolerance, yaw_tolerance) <= 0:
            raise ValueError('primitive speeds and tolerances must be positive')
        self.slow, self.normal, self.angular = slow, normal, angular
        self.distance_tolerance, self.yaw_tolerance = distance_tolerance, yaw_tolerance
        self.queue = deque()
        self.origin = None
        self.slow_mode = False

    def start(self, relative_yaw, distance, slow_mode=False):
        if not np.isfinite([relative_yaw, distance]).all():
            raise ValueError('nonfinite primitive goal')
        if self.queue:
            raise ValueError('sequence already active; cancel explicitly first')
        # Always establish a confirmed stop before beginning a new sequence.
        self.queue = deque([(Primitive.STOP, 0.), *PrimitiveManager.plan(relative_yaw, distance)])
        self.origin = None
        self.slow_mode = slow_mode

    def cancel(self):
        self.queue.clear()
        self.origin = None
        return dict(primitive=Primitive.STOP.value, vx=0., wz=0., complete=True, reason='cancelled')

    def update(self, result):
        if not result.get('valid', True):
            return dict(primitive=Primitive.UNKNOWN.value, vx=None, wz=None, complete=False, reason='feedback_unavailable')
        while self.queue:
            primitive, target = self.queue[0]
            if self.origin is None:
                self.origin = np.array(result['pose'])
            pose = np.array(result['pose'])
            if primitive == Primitive.STOP:
                done = bool(result['stationary'])
                v, w = 0., 0.
            elif primitive in [Primitive.ROTATE_LEFT, Primitive.ROTATE_RIGHT]:
                progress = (pose[2]-self.origin[2])*np.sign(target)
                done = progress >= abs(target)-self.yaw_tolerance
                v, w = 0., float(np.sign(target)*self.angular)
            else:
                direction = np.array([math.cos(self.origin[2]), math.sin(self.origin[2])])
                progress = np.dot(pose[:2]-self.origin[:2], direction)*np.sign(target)
                done = progress >= abs(target)-self.distance_tolerance
                v, w = float(np.sign(target)*(self.slow if self.slow_mode else self.normal)), 0.
                if self.slow_mode:
                    primitive = Primitive.STRAIGHT_SLOW
            if not done:
                return dict(primitive=primitive.value, vx=v, wz=w, complete=False, reason='await_stationary' if primitive == Primitive.STOP else 'running')
            self.queue.popleft()
            self.origin = None
            # After motion completion, don't reuse its old stationary flag to skip STOP.
            if primitive != Primitive.STOP:
                return dict(primitive=Primitive.STOP.value, vx=0., wz=0., complete=False, reason='motion_target_reached')
        return dict(primitive=Primitive.STOP.value, vx=0., wz=0., complete=True, reason='complete')
