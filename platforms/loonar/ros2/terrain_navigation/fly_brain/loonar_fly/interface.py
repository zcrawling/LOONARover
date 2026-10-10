"""Explicitly artificial sensor encoder and uncalibrated motor readout.

This module does not claim that ToF is a fly sense, or that these gains turn
descending neuron activity into a validated rover locomotion policy.
"""
import math
import numpy as np


def depth_array(message):
    if message.encoding != "32FC1" or message.height < 2 or message.width < 2:
        raise ValueError("expected a nonempty metre-valued 32FC1 depth image")
    if message.step < message.width * 4 or len(message.data) != message.height * message.step:
        raise ValueError("invalid depth buffer/stride")
    dtype = np.dtype(">f4" if message.is_bigendian else "<f4")
    return np.ndarray((message.height, message.width), dtype=dtype,
                      buffer=bytes(message.data), strides=(message.step, 4)).astype(np.float32)


def encode_depth(depth):
    """Two visual hemifields; low values must be VALID ranges, not zero holes.

    Quantiles are scene features, not terrain clearance or passability tests.
    The calibrated terrain safety stack still owns those decisions.
    """
    if depth.ndim != 2 or min(depth.shape) < 2:
        raise ValueError("depth must be an HxW image")
    result = {}
    for side, half in zip(("left", "right"), np.array_split(depth, 2, axis=1)):
        valid = np.isfinite(half) & (half >= 0.08) & (half <= 5.0)
        fraction = float(valid.mean())
        distance = float(np.quantile(half[valid], 0.15)) if fraction >= 0.25 else None
        # Map optical left to left brain as an explicit experimental assumption.
        # This is not reconstructed retinotopy or a verified steering sign.
        activation = 0.0 if distance is None else float(np.clip((0.8 - distance) / 0.72, 0, 1))
        result[side] = {"distance_m": distance, "valid_fraction": fraction,
                        "proximity": activation}
    return result


def rates_from_features(features, motivation_hz=None):
    rates = {}
    vision = features.get("vision")
    if vision is not None and vision.get("source") != "surface_v1":
        raise ValueError("unsupported vision features")
    for side in ("left", "right"):
        # Live body packets always use ground-removed surface features. The
        # depth-only branch remains for legacy recorded experiments, not driving.
        proximity = float(vision[side] if vision is not None else features["depth"][side]["proximity"])
        expansion = float(features.get("expansion", {}).get(side, 0.0))
        if not all(math.isfinite(x) and 0 <= x <= 1 for x in (proximity, expansion)):
            raise ValueError("invalid sensory feature")
        rates[f"LC4_{side}"] = 100.0 * proximity
        rates[f"LPLC2_{side}"] = 100.0 * expansion
    if vision is not None:
        heading = float(vision["preferred_heading_rad"])
        if not math.isfinite(heading) or abs(heading) > math.pi/4+1e-6:
            raise ValueError("invalid preferred surface heading")
        if heading:
            danger_side = "right" if heading > 0 else "left"
            rates[f"LC4_{danger_side}"] += 40*abs(heading)/(math.pi/4)
    if "avoidance" in features:
        decision = features["avoidance"]
        scale = float(decision["forward_scale"])
        sign = int(decision["turn_sign"])
        if not math.isfinite(scale) or not 0 <= scale <= 1 or sign not in (-1, 0, 1):
            raise ValueError("invalid avoidance modulation")
        if motivation_hz is not None:
            rates["DNp09_left"] = rates["DNp09_right"] = motivation_hz*scale
        # The measured left-visual -> right-turn response supplies a body-level
        # direction bias. No connectome weights are rewritten.
        if sign:
            danger_side = "right" if sign > 0 else "left"
            other = "left" if sign > 0 else "right"
            rates[f"LC4_{danger_side}"] = max(rates[f"LC4_{danger_side}"], 120.)
            rates[f"LC4_{other}"] *= .25
    return rates


def decode_candidate(population_hz):
    """Read actual DN spikes. Zero neural activity means zero candidate motion.

    DNa02 left/right difference is an EXPERIMENTAL steering convention.
    No state machine invents turns or advances when the model is silent.
    """
    values = [float(population_hz[f"{kind}_{side}"])
              for kind in ("DNp09", "DNa02") for side in ("left", "right")]
    if not all(math.isfinite(x) and x >= 0 for x in values):
        raise ValueError("invalid descending neuron rates")
    forward = min((values[0] + values[1]) / 2 / 150, 1.0) * 0.2
    turn = float(np.clip((values[2] - values[3]) / 100, -1, 1)) * 0.3
    return {"linear_mps": forward, "angular_rps": turn,
            "calibrated": False, "actuation_enabled": False}


class WallTimeReadout:
    """Smooth motor readout using real elapsed time, independent of neural clock."""
    def __init__(self, tau_seconds=.12):
        self.tau = tau_seconds
        self.previous = None
        self.values = {}

    def update(self, rates, now):
        if not self.values or self.previous is None or now-self.previous > .75:
            self.values = dict(rates)
        else:
            alpha = 1.-math.exp(-max(0., now-self.previous)/self.tau)
            self.values = {k: self.values.get(k, v)+alpha*(v-self.values.get(k, v)) for k, v in rates.items()}
        self.previous = now
        return dict(self.values)


class ExpansionEncoder:
    """Low-resolution optical expansion, with bounded frame history.

    Uses image radial flow as a simple artificial looming cue. Pure camera
    rotation can contaminate it; this is not a biological vision model.
    """
    def __init__(self):
        self.previous = None
        self.stamp = None

    def update(self, jpeg, stamp):
        import cv2
        if len(jpeg) > 4_000_000:
            raise ValueError("oversized JPEG")
        frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_GRAYSCALE)
        if frame is None:
            raise ValueError("invalid JPEG")
        gray = cv2.resize(frame, (96, 64))
        result = {"left": 0.0, "right": 0.0}
        if self.previous is not None and 0.02 <= stamp - self.stamp <= 0.5:
            flow = cv2.calcOpticalFlowFarneback(self.previous, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
            y, x = np.mgrid[:64, :96]
            x, y = x - 47.5, y - 31.5
            radial = (flow[..., 0]*x + flow[..., 1]*y) / (x*x + y*y + 25)
            radial = np.maximum(radial / (stamp - self.stamp), 0)
            result = {side: float(np.clip(np.quantile(half, .8), 0, 1))
                      for side, half in zip(("left", "right"), np.array_split(radial, 2, axis=1))}
        self.previous, self.stamp = gray, stamp
        return result
