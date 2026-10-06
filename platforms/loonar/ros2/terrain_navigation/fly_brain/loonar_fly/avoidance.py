"""Rover body adapter: measured terrain, direction memory, turn/advance selection.

This is explicitly NOT a behaviour attributed to the original fly connectome.
All distances are SI, relative to a levelled axle frame, +y left, +yaw left.
"""
import math
import numpy as np

HEADINGS = np.deg2rad([-45, -30, -15, 0, 15, 30, 45])


def scene_from_points(points, *, wheel_radius=.098, robot_length=.30,
                      robot_width=.30, wheel_track=.21, max_step_up=.035, max_step_down=.035,
                      resolution=.05, lookahead=.9):
    """Measured grid only. Missing returns are unknown, never a fabricated pit.

    Ground reference follows the calibrated axle height after IMU levelling.
    Three returns support a cell. Small positive relief remains traversable;
    a measured surface below the support plane is a drop candidate. Conservative
    height-based classification does not certify ramps or a wheel's climbing limit.
    """
    xyz = np.asarray(points, dtype=float).reshape(-1, 3)
    front, half = robot_length/2, robot_width/2
    xyz = xyz[np.isfinite(xyz).all(axis=1)]
    xyz = xyz[(xyz[:, 0] >= 0) & (xyz[:, 0] <= lookahead+front) &
              (np.abs(xyz[:, 1]) <= .95) & (xyz[:, 2] >= -wheel_radius-.5) & (xyz[:, 2] < .65)]
    if not len(xyz):
        return dict(ready=False, reason="no usable transformed points")
    xy, inverse, counts = np.unique(np.floor(xyz[:, :2]/resolution).astype(int),
                                    axis=0, return_inverse=True, return_counts=True)
    low = np.full(len(xy), np.inf)
    high = np.full(len(xy), -np.inf)
    np.minimum.at(low, inverse, xyz[:, 2]+wheel_radius)
    np.maximum.at(high, inverse, xyz[:, 2]+wheel_radius)
    keep = counts >= 3
    centers = (xy[keep]+.5)*resolution
    low, high = low[keep], high[keep]
    if not len(centers):
        return dict(ready=False, reason="no cells with three supporting returns")
    # Margin covers the entire intersecting cell, not just its centre.
    pad = resolution/math.sqrt(2)
    # A lone flying pixel cannot turn a supported floor cell into a wall.
    high_count = np.bincount(inverse, weights=(xyz[:, 2]+wheel_radius > max_step_up+.005), minlength=len(xy))[keep]
    above = high_count >= 3
    below = high < -max_step_down - .005
    ground = (~above & ~below & (low >= -max_step_down))
    # Discard unsupported high outliers from low-step height reporting too.
    supported_high = high.copy()
    supported_high[~above & (high > max_step_up+.005)] = low[~above & (high > max_step_up+.005)]
    directions = []
    for angle in HEADINGS:
        c, s = math.cos(angle), math.sin(angle)
        along = centers[:, 0]*c + centers[:, 1]*s
        across = -centers[:, 0]*s + centers[:, 1]*c
        corridor = (np.abs(across) <= half+pad) & (along >= front-pad) & (along < lookahead+front)
        danger = corridor & (above | below)
        if danger.any():
            candidates = np.flatnonzero(danger)
            first = candidates[np.argmin(along[candidates])]
            clearance = max(0., float(along[first]-pad-front))
            kind = "drop" if below[first] else ("wall" if high[first] > .12 else "step_up")
            height = float(high[first])
        else:
            clearance, kind, height = lookahead, "none", 0.
        # Look for continuity along the path, beginning at the first visible
        # ground bin. Near-field blind ground is explicitly reported separately.
        # Both wheel paths need support. A floor return beside a missing wheel
        # track must not conceal a hole under the other wheel.
        lane_bins = []
        for offset in (-wheel_track/2, wheel_track/2):
            lane = corridor & ground & (np.abs(across-offset) <= resolution/2+.02)
            lane_bins.append(np.unique(np.floor(np.maximum(along[lane]-front, 0)/.1).astype(int)))
        bins = np.intersect1d(*lane_bins)
        support_end = 0.
        first_visible = None
        if len(bins):
            first_visible = float(bins[0]*.1)
            if first_visible <= .25:
                expected = int(bins[0])
                for k in bins:
                    if k != expected:
                        break
                    support_end = (int(k)+1)*.1
                    expected += 1
        unknown_ahead = support_end < min(.45, clearance)
        step_height = float(max(0., np.max(supported_high[corridor & ground]))) if np.any(corridor & ground) else 0.
        directions.append(dict(heading=float(angle), clearance_m=clearance,
            obstacle=kind, measured_height_m=height, support_until_m=min(lookahead, support_end),
            near_blind_m=first_visible, unknown_ground=bool(unknown_ahead),
            low_step_m=step_height, observed_cells=int(corridor.sum())))
    turn = {}
    hazard_cells = np.zeros(len(xy), dtype=bool)
    hazard_cells[keep] = above | below
    point_height = xyz[:, 2]+wheel_radius
    hazards = xyz[hazard_cells[inverse] & ((point_height > max_step_up+.005) |
                  (point_height < -max_step_down-.005)), :2]
    for side, sign in (("left", 1), ("right", -1)):
        hit = False
        for angle in np.linspace(0, sign*.2, 5):
            c, s = math.cos(angle), math.sin(angle)
            u = hazards[:, 0]*c + hazards[:, 1]*s
            v = -hazards[:, 0]*s + hazards[:, 1]*c
            # Only measured hazards in the next small swept footprint veto this
            # turn. Unseen rear space is not claimed to be certified clear.
            hit |= bool(np.count_nonzero((np.abs(u) < front+.01) & (np.abs(v) < half+.01)) >= 3)
        turn[side] = not hit
    return dict(ready=True, directions=directions, turn_clear=turn,
                point_count=int(len(xyz)), cell_count=int(len(centers)),
                reference_ground_z=-wheel_radius, reference="TF + synchronized IMU + calibrated axle height",
                rotation_scope="observed hazards, next 0.2rad; rear unseen")


class Avoidance:
    """Real-time body behaviour; direction stays latched until a new path opens."""
    def __init__(self):
        self.mode = "cruise"
        self.sign = 0
        self.until = 0.
        self.clear_since = None
        self.last_frame = None
        self.last_at = None
        self.last_clearance = None
        self.closing = 0.
        self.last_decision = {}

    def update(self, scene, now, frame_id):
        if frame_id == self.last_frame:
            return self.last_decision
        self.last_frame = frame_id
        if not scene or not scene.get("ready"):
            self.last_decision = dict(mode="await_scene", forward_scale=0., speed_cap_mps=0.,
                turn_sign=0, turn_rps=0., reason="awaiting calibrated terrain observations", risk=1.)
            return self.last_decision
        rays = scene["directions"]
        center = min(rays, key=lambda r: abs(r["heading"]))
        distance = center["clearance_m"]
        if self.last_at is not None and .02 < now-self.last_at < .5:
            measured = max(0., (self.last_clearance-distance)/(now-self.last_at))
            self.closing = .6*self.closing + .4*min(measured, 1.)
        else:
            self.closing = 0.
        self.last_at, self.last_clearance = now, distance
        measured_hazard = center["obstacle"] != "none"
        risky_drop = center["obstacle"] == "drop" and distance < .45
        # Start turning before the measured hazard reaches the body boundary.
        turn_needed = (measured_hazard and distance < max(.22, self.closing*1.2)) or risky_drop
        unknown = bool(center["unknown_ground"])
        if unknown and center["support_until_m"] < .25:
            turn_needed = True
        opened = (not measured_hazard or distance > .5) and not unknown
        if self.mode in ("turn", "scan"):
            if opened:
                if self.clear_since is None:
                    self.clear_since = now
                if now >= self.until and now-self.clear_since >= .3:
                    self.mode, self.sign = "cruise", 0
            else:
                self.clear_since = None
        elif turn_needed:
            self.mode = "scan" if unknown and not measured_hazard else "turn"
            self.until, self.clear_since = now+.6, None
            def score(sign):
                side = [r for r in rays if r["heading"]*sign > .1]
                return max((min(r["clearance_m"], r["support_until_m"])
                            - .1*abs(r["heading"]) for r in side), default=-1)
            left, right = score(1), score(-1)
            # Deterministic symmetry break: right on a tie. Never random jitter.
            self.sign = 1 if left > right+.03 else -1
        blocked_turn = False
        if self.sign:
            side = "left" if self.sign > 0 else "right"
            if not scene["turn_clear"][side]:
                other = "right" if self.sign > 0 else "left"
                if scene["turn_clear"][other]:
                    self.sign *= -1
                    self.until = now+.6
                else:
                    blocked_turn = True
        if self.mode in ("turn", "scan"):
            mode = "no_turn_room" if blocked_turn else self.mode
            turn_rps = 0. if blocked_turn else (.35 if self.mode == "scan" else .5)
            scale, cap = 0., 0.
            reason = "measured hazards in both turn footprints" if blocked_turn else (
                "look for observed ground" if self.mode == "scan" else f"avoid {center['obstacle']}")
        else:
            # Smooth slowdown ahead of turns, including approach speed.
            risk = float(np.clip((.55-distance)/.4, 0, 1)) if measured_hazard else 0.
            scale = (1-risk)**2
            cap = .2*scale
            mode, turn_rps, reason = "cruise", 0., "open path"
            if unknown:
                cap = min(cap, .04)
                mode, reason = "inspect", "partial ground; approach slowly and rescan"
            elif center["low_step_m"] > .015:
                cap = min(cap, .05)
                mode, reason = "low_step", "measured low step; cross slowly"
            elif risk > 0:
                mode, reason = "approach", f"approaching {center['obstacle']}"
        self.last_decision = dict(mode=mode, forward_scale=scale, speed_cap_mps=cap,
            turn_sign=self.sign, turn_rps=turn_rps, reason=reason,
            clearance_m=distance, closing_mps=self.closing,
            risk=1.-scale, obstacle=center["obstacle"], unknown_ground=unknown)
        return self.last_decision

    @staticmethod
    def command(candidate, decision):
        if not decision:
            return dict(linear_mps=0., angular_rps=0.)
        v = min(candidate["linear_mps"], decision["speed_cap_mps"])
        w = candidate["angular_rps"]
        if decision["mode"] in ("turn", "scan"):
            # Explicit rover reflex for symmetry breaking. Retains neural turn
            # magnitude when larger, without pretending this is original biology.
            w = decision["turn_sign"]*max(decision["turn_rps"], abs(w))
        elif decision["mode"] in ("await_scene", "no_turn_room"):
            v, w = 0., 0.
        if abs(w) > .2:
            v = min(v, .05)
        return dict(linear_mps=max(0., v), angular_rps=float(np.clip(w, -.6, .6)))
