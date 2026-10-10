"""Rover body adapter: measured terrain, direction memory, turn/advance selection.

This is explicitly NOT a behaviour attributed to the original fly connectome.
All distances are SI, relative to a levelled axle frame, +y left, +yaw left.
"""
import math
import numpy as np

from .vision import fit_floor, surface_metrics, preferred_surface, neural_features, grid_index

HEADINGS = np.deg2rad([-45, -30, -15, 0, 15, 30, 45])


def scene_from_points(points, *, wheel_radius=.098, robot_length=.30,
                      robot_width=.30, wheel_track=.21, obstacle_diameter_fraction=.30, max_step_down=.035,
                      resolution=.05, lookahead=.9):
    """Measured grid only. Missing returns are unknown, never a fabricated pit.

    Ground is fitted from measured points with a calibrated-height fallback.
    Obstacle height is >= 30% wheel DIAMETER above that surface. Three height-
    qualified returns support a cell. Below-ground surfaces remain drop candidates.
    Flatness ranks paths only after excluding measured obstacles.
    """
    xyz = np.asarray(points, dtype=float).reshape(-1, 3)
    front, half = robot_length/2, robot_width/2
    xyz = xyz[np.isfinite(xyz).all(axis=1)]
    xyz = xyz[(xyz[:, 0] >= 0) & (xyz[:, 0] <= lookahead+front) &
              (np.abs(xyz[:, 1]) <= .95) & (xyz[:, 2] >= -wheel_radius-.5) & (xyz[:, 2] < .65)]
    if not len(xyz):
        return dict(ready=False, reason="no usable transformed points")
    floor = fit_floor(xyz, wheel_radius)
    plane = np.asarray(floor["coefficients"])
    point_height = xyz[:, 2] - (xyz[:, :2] @ plane[:2]+plane[2])
    max_step_up = 2*wheel_radius*obstacle_diameter_fraction
    xy, inverse, counts = grid_index(xyz, resolution)
    low = np.full(len(xy), np.inf)
    high = np.full(len(xy), -np.inf)
    np.minimum.at(low, inverse, point_height)
    np.maximum.at(high, inverse, point_height)
    keep = counts >= 3
    centers = (xy[keep]+.5)*resolution
    low, high = low[keep], high[keep]
    if not len(centers):
        return dict(ready=False, reason="no cells with three supporting returns")
    # Margin covers the entire intersecting cell, not just its centre.
    pad = resolution/math.sqrt(2)
    # A lone flying pixel cannot turn a supported floor cell into a wall.
    high_count = np.bincount(inverse, weights=(point_height >= max_step_up-1e-9), minlength=len(xy))[keep]
    above = high_count >= 3
    below = high < -max_step_down - .005
    ground = (~above & ~below & (low >= -max_step_down))
    # Discard unsupported high outliers from low-step height reporting too.
    supported_high = high.copy()
    supported_high[~above & (high >= max_step_up-1e-9)] = low[~above & (high >= max_step_up-1e-9)]
    mean_z = np.bincount(inverse, weights=xyz[:, 2], minlength=len(xy))[keep]/counts[keep]
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
        measured_surface = corridor & ground & (along <= front+.65)
        metrics = surface_metrics(centers[measured_surface], mean_z[measured_surface],
                                  angle, support_end, floor["confidence"])
        directions.append(dict(heading=float(angle), clearance_m=clearance,
            obstacle=kind, measured_height_m=height, support_until_m=min(lookahead, support_end),
            near_blind_m=first_visible, unknown_ground=bool(unknown_ahead),
            low_step_m=step_height, observed_cells=int(corridor.sum()), **metrics))
    turn = {}
    hazard_cells = np.zeros(len(xy), dtype=bool)
    hazard_cells[keep] = above | below
    hazards = xyz[hazard_cells[inverse] & ((point_height >= max_step_up-1e-9) |
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
    scene = dict(ready=True, directions=directions, turn_clear=turn,
                floor=floor, obstacle_threshold_m=max_step_up,
                preferred_heading_rad=preferred_surface(directions),
                point_count=int(len(xyz)), cell_count=int(len(centers)),
                reference_ground_z=float(plane[2]), reference="measured surface + TF/IMU; explicit calibrated prior if no fit",
                rotation_scope="observed hazards, next 0.2rad; rear unseen")
    scene["vision"] = neural_features(scene)
    return scene


class Avoidance:
    """Real-time body behaviour; direction stays latched until a new path opens."""
    def __init__(self):
        self.mode = "cruise"
        self.sign = 0
        self.surface_heading = 0.
        self.surface_until = 0.
        self.until = 0.
        self.clear_since = None
        self.last_frame = None
        self.last_at = None
        self.last_clearance = None
        self.last_obstacle = None
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
        if (self.last_at is not None and .02 < now-self.last_at < .5
                and center["obstacle"] == self.last_obstacle != "none"):
            measured = max(0., (self.last_clearance-distance)/(now-self.last_at))
            self.closing = .6*self.closing + .4*min(measured, .2)
        else:
            self.closing = 0.
        self.last_at, self.last_clearance = now, distance
        self.last_obstacle = center["obstacle"]
        measured_hazard = center["obstacle"] != "none"
        risky_drop = center["obstacle"] == "drop" and distance < .45
        # Start turning before the measured hazard reaches the body boundary.
        turn_needed = (measured_hazard and distance < max(.22, self.closing*1.2)) or risky_drop
        unknown = bool(center["unknown_ground"])
        # A horizontal camera cannot prove continuous ground under both wheels.
        # Missing ground is diagnostic, not evidence to stop/scan indefinitely.
        opened = not measured_hazard or distance > (.5 if center["obstacle"] == "drop" else .30)
        if self.mode == "turn":
            if opened:
                if self.clear_since is None:
                    self.clear_since = now
                if now >= self.until and now-self.clear_since >= .15:
                    self.mode, self.sign = "cruise", 0
            else:
                self.clear_since = None
        elif turn_needed:
            self.mode = "turn"
            self.until, self.clear_since = now+.3, None
            def score(sign):
                side = [r for r in rays if r["heading"]*sign > .1]
                # First maximize measured clearance; flatness only breaks near ties.
                best_clear = max((r["clearance_m"] for r in side), default=-1)
                near_best = [r for r in side if r["clearance_m"] >= best_clear-.03]
                return best_clear-min((min(.025, .01*r.get("flat_cost", 0)) + .01*abs(r["heading"])
                                       for r in near_best), default=0)
            left, right = score(1), score(-1)
            # Deterministic symmetry break: right on a tie. Never random jitter.
            self.sign = 1 if left > right+.01 else -1
        blocked_turn = False
        if self.sign:
            side = "left" if self.sign > 0 else "right"
            if not scene["turn_clear"][side]:
                other = "right" if self.sign > 0 else "left"
                if scene["turn_clear"][other]:
                    self.sign *= -1
                    self.until = now+.3
                else:
                    blocked_turn = True
        if self.mode == "turn":
            mode = "no_turn_room" if blocked_turn else "turn"
            turn_rps = 0. if blocked_turn else .3
            cap = 0.
            reason = "measured hazards in both turn footprints" if blocked_turn else f"avoid {center['obstacle']}"
        else:
            # One output limiter only. Keep the neural walking drive alive so
            # releasing a turn does not wait for the slow simulated brain clock.
            risk = float(np.clip((.40-distance)/.18, 0, 1)) if measured_hazard else 0.
            cap = .2-.1*risk
            mode, turn_rps, reason = "cruise", 0., "no measured obstacle ahead"
            if risk > 0:
                mode, reason = "approach", f"approaching {center['obstacle']}"
        proposed = float(scene.get("preferred_heading_rad", 0.))
        previous = min(rays, key=lambda r: abs(r["heading"]-self.surface_heading))
        # Reject a previously preferred path immediately when an obstacle appears.
        if (now >= self.surface_until or previous["obstacle"] != "none" or previous["clearance_m"] < .55 or
                previous.get("surface_confidence", 0) < .35 or not proposed):
            if proposed != self.surface_heading:
                self.surface_until = now+.35
            self.surface_heading = proposed
        if mode in ("cruise", "approach") and self.surface_heading:
            mode, reason = "follow_surface", "steer toward flatter observed path without measured obstacles"
        scale = 1.  # motor adapter owns braking; no duplicate tonic suppression
        self.last_decision = dict(mode=mode, forward_scale=scale, speed_cap_mps=cap,
            turn_sign=self.sign, turn_rps=turn_rps, reason=reason,
            surface_heading_rad=self.surface_heading if mode == "follow_surface" else 0.,
            clearance_m=distance, closing_mps=self.closing,
            risk=1.-cap/.2, obstacle=center["obstacle"], unknown_ground=unknown)
        return self.last_decision

    @staticmethod
    def command(candidate, decision):
        if not decision:
            return dict(linear_mps=0., angular_rps=0.)
        v = min(candidate["linear_mps"], decision["speed_cap_mps"])
        w = candidate["angular_rps"]
        if decision["mode"] == "turn":
            # Explicit rover reflex for symmetry breaking. Retains neural turn
            # magnitude when larger, without pretending this is original biology.
            w = decision["turn_sign"]*max(decision["turn_rps"], abs(w))
        elif decision["mode"] == "follow_surface":
            # Gentle continuous steering, not a new pivot or forward-speed cap.
            target = float(np.clip(.6*decision["surface_heading_rad"], -.2, .2))
            w = target + .2*float(np.clip(w, -.3, .3))
        elif decision["mode"] in ("await_scene", "no_turn_room"):
            v, w = 0., 0.
        return dict(linear_mps=max(0., v), angular_rps=float(np.clip(w, -.4, .4)))
