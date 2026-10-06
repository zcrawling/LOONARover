"""Pure algorithms: no ROS, clocks, hardware or persistent world map."""

from collections import deque
from dataclasses import dataclass
import math
import numpy as np


def fresh(stamp, now, timeout):
    return stamp is not None and 0 <= now - stamp <= timeout


class Stationarity:
    def __init__(self):
        self.samples = deque()
        self.quiet_since = None
        self.last = None

    def update(self, now, gyro, accel, wheels, active, p):
        if self.last is not None and now <= self.last:
            self.samples.clear()
            self.quiet_since = None
        self.last = now
        values = np.array([*gyro, *accel, *wheels], dtype=float)
        if not np.isfinite(values).all():
            self.samples.clear()
            self.quiet_since = None
            return 3, 0.0
        self.samples.append((now, values))
        # Retain one sample just before the window to measure its full duration.
        while (
            len(self.samples) > 2 and self.samples[1][0] <= now - p["minimum_duration"]
        ):
            self.samples.popleft()
        quiet = (
            not active
            and max(abs(v) for v in wheels) < p["wheel_velocity_threshold"]
            and np.linalg.norm(gyro) < p["gyro_threshold"]
        )
        if not quiet:
            self.quiet_since = None
            return 0, 0.0
        if self.quiet_since is None:
            self.quiet_since = now
        elapsed = now - self.quiet_since
        if len(self.samples) < 3 or now - self.samples[0][0] < p["minimum_duration"]:
            return 1, 0.0
        data = np.array([x[1] for x in self.samples])
        stable = (
            max(np.std(data[:, :3], axis=0)) < p["gyro_std_threshold"]
            and max(np.std(data[:, 3:6], axis=0)) < p["accel_std_threshold"]
            and np.max(np.abs(data[:, 6:])) < p["wheel_velocity_threshold"]
        )
        if not stable:
            self.quiet_since = now
        confidence = min(
            1.0, elapsed / max(p["minimum_duration"], p["settling_min_time"])
        )
        return (2 if stable and confidence >= 1 else 1), (confidence if stable else 0.0)


@dataclass
class Candidate:
    heading: float
    safe_distance: float = 0.0
    cost: float = math.inf
    confidence: float = 0.0
    reason: str = "unsafe footprint"


def footprint_indices(grid, s, theta, p):
    """Conservatively include every cell intersecting the swept rectangle.

    A half-cell diagonal inflation covers edges/corners, including map exterior.
    Cell order is x-major: i * size_y + j. Tail expands the rear support extent.
    """
    res = grid.resolution
    c, sn = math.cos(theta), math.sin(theta)
    front = p["robot_length"] / 2 + p["safety_margin"]
    rear = max(p["robot_length"] / 2, p["tail_offset"]) + p["safety_margin"]
    side = p["robot_width"] / 2 + p["safety_margin"]
    radius = math.hypot(max(front, rear), side) + res
    cx, cy = s * c, s * sn
    ids = []
    outside = False
    for i in range(
        math.floor((cx - radius - grid.x_min) / res),
        math.ceil((cx + radius - grid.x_min) / res),
    ):
        for j in range(
            math.floor((cy - radius - grid.y_min) / res),
            math.ceil((cy + radius - grid.y_min) / res),
        ):
            x = grid.x_min + (i + 0.5) * res - cx
            y = grid.y_min + (j + 0.5) * res - cy
            u, v = c * x + sn * y, -sn * x + c * y
            pad = res / math.sqrt(2)
            if -rear - pad <= u <= front + pad and abs(v) <= side + pad:
                if not (0 <= i < grid.size_x and 0 <= j < grid.size_y):
                    outside = True
                else:
                    ids.append(i * grid.size_y + j)
    return ids, outside


def assess(cells, heading, p):
    if not cells:
        return False, math.inf, 0.0, "empty footprint"
    unknown = sum(c.unknown or not c.observed for c in cells) / len(cells)
    if unknown > p["max_unknown_ratio"]:
        return False, math.inf, 0.0, "unknown"
    risks, conf = [], []
    for c in cells:
        if c.drop_suspect:
            return False, math.inf, 0.0, "drop suspect"
        if c.unknown or not c.observed:
            continue
        vals = [
            c.confidence,
            c.slope,
            c.roughness,
            c.step_up,
            c.step_down,
            c.depression_depth,
            c.gradient_x,
            c.gradient_y,
        ]
        if (
            not all(math.isfinite(v) for v in vals)
            or c.confidence < p["min_confidence"]
        ):
            return False, math.inf, 0.0, "low confidence"
        cross = abs(
            math.atan(
                -math.sin(heading) * c.gradient_x + math.cos(heading) * c.gradient_y
            )
        )
        ratios = [
            c.slope / p["max_slope"],
            cross / p["max_cross_slope"],
            c.roughness / p["max_roughness"],
            c.step_up / p["max_step_up"],
            c.step_down / p["max_step_down"],
            c.depression_depth / p["max_drop_depth"],
        ]
        if max(ratios) > 1:
            return False, math.inf, 0.0, "terrain limit"
        risk = (
            p["w_slope"] * ratios[0]
            + p["w_roughness"] * ratios[2]
            + p["w_step"] * max(ratios[3:])
            + p["w_risk"] * max(ratios)
        )
        risks.append(risk)
        conf.append(c.confidence)
    if not conf:
        return False, math.inf, 0.0, "no observed ground"
    return True, max(risks) + p["w_unknown"] * unknown, min(conf), "safe"


def evaluate(grid, heading, previous, p):
    candidate = Candidate(heading)
    max_cost, confidence = 0.0, 1.0
    # Include swept rotation. Translation alone cannot certify a turn.
    turn_step = min(
        0.05, grid.resolution / max(p["robot_length"], p["robot_width"], 0.01)
    )
    for angle in np.linspace(
        0, heading, max(2, math.ceil(abs(heading) / turn_step) + 1)
    ):
        ids, outside = footprint_indices(grid, 0, angle, p)
        ok, cost, conf, reason = assess([grid.cells[i] for i in ids], angle, p)
        if outside or not ok:
            candidate.reason = "rotation: " + ("outside map" if outside else reason)
            return candidate
        max_cost, confidence = max(max_cost, cost), min(confidence, conf)
    # Half-cell increments + inflated footprint cover gaps between samples.
    for s in np.arange(0, p["lookahead_distance"] + 1e-8, grid.resolution / 2):
        ids, outside = footprint_indices(grid, s, heading, p)
        ok, cost, conf, reason = assess([grid.cells[i] for i in ids], heading, p)
        if outside or not ok:
            candidate.reason = "outside map" if outside else reason
            break
        candidate.safe_distance = float(s)
        max_cost, confidence = max(max_cost, cost), min(confidence, conf)
    # Judge the actual executable segment, not an unrelated 20 cm horizon.
    if command_distance(candidate.safe_distance, p) > 0:
        candidate.confidence = confidence
        candidate.cost = (
            max_cost
            + p["w_turn"] * abs(heading)
            + p["w_heading_change"] * abs(heading - previous)
            - p["w_progress"] * candidate.safe_distance
        )
        candidate.reason = "safe"
    return candidate


def command_distance(safe, p):
    # Never clamp upward into unobserved terrain. Short candidates are rejected.
    distance = min(
        p["max_drive_distance"],
        p["distance_safety_factor"] * safe,
        safe - p["stopping_margin"],
    )
    return distance if distance >= p["min_drive_distance"] else 0.0


def collision_guard(xyz, wheel_velocities, yaw_rate, p):
    """Near-field emergency guard; low relief still requires a valid terrain plan.

    xyz is levelled axle-relative, wheel velocities are rad/s. Include one full
    sensor timeout in reaction distance so an aging frame cannot understate it.
    Braking parameters are configurable starting assumptions, not measurements.
    """
    front = p["robot_length"] / 2
    rear = max(front, p["tail_offset"])
    radius = math.hypot(max(front, rear), p["robot_width"] / 2)
    left, right = np.asarray(wheel_velocities) * p["wheel_radius"]
    omega = max(abs(yaw_rate), abs(right - left) / p["wheel_track"])
    speed = abs((left + right) / 2) + omega * radius
    clearance = (
        max(p["stopping_margin"], p["safety_margin"])
        + speed * (p["sensor_timeout"] + p["brake_reaction_time"])
        + speed * speed / (2 * p["brake_deceleration"])
    )
    # Never raise a stricter configured height cutoff. Small relief is left to
    # slope/step/drop/unknown/confidence gates in the planner, not declared safe.
    height_cutoff = min(
        p["collision_min_height"], -p["wheel_radius"] + p["max_step_up"]
    )
    high = (xyz[:, 2] > height_cutoff) & (xyz[:, 2] < p["collision_max_height"])
    if omega > p["gyro_threshold"]:
        nearby = np.hypot(xyz[:, 0], xyz[:, 1]) <= radius + clearance
    else:
        nearby = (
            (xyz[:, 0] > 0)
            & (xyz[:, 0] <= front + clearance)
            & (
                np.abs(xyz[:, 1])
                <= max(
                    p["collision_half_width"], p["robot_width"] / 2 + p["safety_margin"]
                )
            )
        )
    hits = xyz[high & nearby]
    blocked = len(hits) >= p["collision_min_points"]
    reason = "clear"
    if blocked:
        reason = (
            f"collision braking envelope: {len(hits)} points, "
            f"front gap={np.min(hits[:, 0])-front:.3f}m, "
            f"required clearance={clearance:.3f}m"
        )
    return blocked, reason


def primitive_command(kind, target, speed, distance, yaw, gyro, p):
    if kind == 0:
        return 0.0, 0.0, True
    if kind == 1:
        remaining = target - distance
        if remaining <= p["distance_tolerance"]:
            return 0.0, 0.0, True
        v = min(
            speed, p["straight_normal_speed"], max(0.01, remaining * p["distance_kp"])
        )
        w = np.clip(
            -p["straight_yaw_kp"] * yaw - p["straight_yaw_kd"] * gyro,
            -p["max_heading_correction"],
            p["max_heading_correction"],
        )
        return v, float(w), False
    error = target - yaw  # Integrated gyro: continuous across +/-pi, never wheel yaw.
    if abs(error) <= p["yaw_tolerance"]:
        return 0.0, 0.0, abs(gyro) < p["settle_gyro_threshold"]
    w = math.copysign(
        min(speed, p["rotate_speed"], max(0.02, abs(error) * p["rotate_kp"])), error
    )
    return 0.0, w, False


def depression_regions(grid, threshold):
    """4-connected measured depressions; unknown/drop depth is never fabricated."""
    pending = {
        i
        for i, c in enumerate(grid.cells)
        if c.observed
        and not c.unknown
        and math.isfinite(c.depression_depth)
        and c.depression_depth >= threshold
    }
    regions = []
    while pending:
        seed = pending.pop()
        queue = [seed]
        members = []
        while queue:
            k = queue.pop()
            members.append(k)
            x, y = divmod(k, grid.size_y)
            for i, j in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                n = i * grid.size_y + j
                if 0 <= i < grid.size_x and 0 <= j < grid.size_y and n in pending:
                    pending.remove(n)
                    queue.append(n)
        xs = [k // grid.size_y for k in members]
        ys = [k % grid.size_y for k in members]
        regions.append(
            dict(
                depth=max(grid.cells[k].depression_depth for k in members),
                area=len(members) * grid.resolution**2,
                length=(max(xs) - min(xs) + 1) * grid.resolution,
                width=(max(ys) - min(ys) + 1) * grid.resolution,
                x=grid.x_min + (min(xs) + max(xs) + 1) * grid.resolution / 2,
                y=grid.y_min + (min(ys) + max(ys) + 1) * grid.resolution / 2,
            )
        )
    return regions
