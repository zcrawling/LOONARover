"""Small, deterministic ToF preprocessor; no neural model or motor ownership."""
from collections import deque
import math
import warnings

import numpy as np


def grid_index(points, resolution):
    """Group XY cells with integer keys; avoids costly structured-array sort."""
    cells = np.floor(np.asarray(points)[:, :2]/resolution).astype(np.int64)
    origin = cells.min(axis=0)
    width = int(cells[:, 1].max()-origin[1]+1)
    keys = (cells[:, 0]-origin[0])*width+cells[:, 1]-origin[1]
    unique, inverse, counts = np.unique(keys, return_inverse=True, return_counts=True)
    xy = np.column_stack((unique//width+origin[0], unique % width+origin[1]))
    return xy, inverse, counts


class DepthWindow:
    """Fuse up to five stationary frames, never blend unregistered moving frames.

    Cold start and motion use the latest frame immediately. Current invalid
    pixels stay invalid. A newly closer, spatially supported patch bypasses
    the temporal median so an appearing obstacle is not averaged away.
    """
    def __init__(self):
        self.frames = deque(maxlen=5)
        self.key = None
        self.gravity = None
        self.was_stationary = False

    def update(self, depth, stamp, stationary, gravity, key):
        z = np.asarray(depth, dtype=float)
        g = np.asarray(gravity, dtype=float)
        g = g / np.linalg.norm(g)
        reset = (not stationary or not self.was_stationary or self.key != key or
                 (self.frames and not 0 < stamp-self.frames[-1][0] < .25) or
                 (self.gravity is not None and np.dot(g, self.gravity) < math.cos(.015)))
        if reset:
            self.frames.clear()
        if not self.frames:
            self.gravity = g
        self.key = key
        self.was_stationary = bool(stationary)
        self.frames.append((stamp, z.copy()))
        while stamp-self.frames[0][0] > .4:
            self.frames.popleft()
        out = z.copy()
        used = len(self.frames) if stationary else 1
        spread = 0.
        if used >= 3:
            stack = np.stack([f[1] for f in self.frames])
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                median = np.nanmedian(stack, axis=0)
                mad = np.nanmedian(np.abs(stack-median), axis=0)
            supported = np.sum(np.isfinite(stack), axis=0) >= 3
            current = np.isfinite(z)
            stable = supported & (mad <= .015) & current
            out[stable] = median[stable]
            out[supported & ~stable & current] = np.nan
            closer = current & np.isfinite(median) & (z < median-.04)
            pad = np.pad(closer.astype(int), 1)
            neighbors = sum(pad[y:y+z.shape[0], x:x+z.shape[1]] for y in range(3) for x in range(3))
            newly_near = closer & (neighbors >= 3)
            out[newly_near] = z[newly_near]
            out[~current] = np.nan
            if np.any(stable):
                spread = float(np.median(mad[stable]))
        return out, dict(frames=used, mode="stationary_median" if used >= 3 else "latest_frame",
                         stationary=bool(stationary), median_mad_m=spread,
                         span_seconds=float(stamp-self.frames[0][0]))


def fit_floor(points, wheel_radius):
    """Gravity-constrained robust plane z=ax+by+c anchored near the axle floor.

    Equalize spatial cells before fitting, so a dense wall cannot dominate.
    Reject planes outside the plausible axle intercept, rather than fitting
    an obstacle top as a new ground plane. No fit uses an explicit geometric
    prior and reports zero measured confidence; it does not invent free space.
    """
    xyz = np.asarray(points, float)
    fallback = dict(coefficients=[0., 0., -wheel_radius], measured=False,
                    confidence=0., residual_m=None, inlier_cells=0,
                    reason="insufficient supported floor; calibrated height prior")
    if len(xyz) < 18:
        return fallback
    grid, inverse, counts = grid_index(xyz, .05)
    # Lower quantile retains floor in cells also containing vertical faces.
    order = np.lexsort((xyz[:, 2], inverse))
    starts = np.r_[0, np.cumsum(counts)[:-1]]
    rank = (counts-1)*.25
    lo, hi = np.floor(rank).astype(int), np.ceil(rank).astype(int)
    lower_z = xyz[order[starts+lo], 2]
    upper_z = xyz[order[starts+hi], 2]
    samples = np.column_stack((
        np.bincount(inverse, weights=xyz[:, 0])/counts,
        np.bincount(inverse, weights=xyz[:, 1])/counts,
        lower_z+(rank-lo)*(upper_z-lower_z)))[counts >= 3]
    if len(samples) < 12:
        return fallback
    samples = samples[(samples[:, 0] <= .85) & (np.abs(samples[:, 1]) <= .65) &
                      (np.abs(samples[:, 2]+wheel_radius) <= .22)]
    if len(samples) < 12:
        return fallback
    design = np.column_stack((samples[:, :2], np.ones(len(samples))))
    # Anchor on the nearest visible support, not distant tops/riser cells.
    # A global fit can tilt a few degrees to absorb the lower part of a step,
    # reducing a 65mm obstacle below the 60mm decision boundary.
    near = samples[:, 0] <= min(.40, float(samples[:, 0].min())+.15)
    if np.count_nonzero(near) < 4:
        return fallback
    rng = np.random.default_rng(783)
    near_ids = np.flatnonzero(near)
    best, best_score = None, -1
    # A known-height candidate also handles floor patches too narrow for a
    # reliable free three-parameter fit; it still needs measured inliers.
    candidates = [np.array([0., 0., -wheel_radius])]
    for _ in range(72):
        ids = rng.choice(near_ids, 3, replace=False)
        if abs(np.linalg.det(design[ids])) < .003:
            continue
        candidates.append(np.linalg.solve(design[ids], samples[ids, 2]))
    for plane in candidates:
        if np.linalg.norm(plane[:2]) > math.tan(.35) or abs(plane[2]+wheel_radius) > .025:
            continue
        errors = np.abs(design @ plane-samples[:, 2])
        inside = errors <= .012
        if inside.sum() < 10 or np.count_nonzero(inside & near) < 4:
            continue
        score = int(inside.sum()) + 3*int(np.count_nonzero(inside & near)) - 10000*float(np.median(errors[near]))
        if score > best_score:
            best, best_score = (plane, inside), score
    if best is None:
        return fallback
    plane, inside = best
    residual = np.abs(design @ plane-samples[:, 2])
    # Do not refine using riser points merely inside the broad RANSAC band.
    refine_band = min(.006, max(.002, 3*float(np.median(residual[inside & near]))))
    anchor = near & (residual <= refine_band)
    refined, _, rank, _ = np.linalg.lstsq(design[anchor], samples[anchor, 2], rcond=None)
    if rank == 3 and np.linalg.norm(refined[:2]) <= math.tan(.35) and abs(refined[2]+wheel_radius) <= .025:
        plane = refined
    errors = np.abs(design @ plane-samples[:, 2])
    inside = errors <= .012
    return dict(coefficients=plane.tolist(), measured=True,
                confidence=float(min(1., inside.sum()/30)*inside.mean()),
                residual_m=float(np.median(errors[inside])), inlier_cells=int(inside.sum()),
                reason="measured near-ground plane, gravity and axle-height constrained")


def surface_metrics(centers, heights, angle, support, floor_confidence):
    """Compare physical slope, roughness and support across candidate paths."""
    if len(centers) < 8 or np.ptp(centers[:, 0]) < .15 or np.ptp(centers[:, 1]) < .06:
        return dict(surface_confidence=0., slope_rad=0., cross_slope_rad=0.,
                    roughness_m=0., flat_cost=2.)
    design = np.column_stack((centers, np.ones(len(centers))))
    plane, _, rank, _ = np.linalg.lstsq(design, heights, rcond=None)
    if rank < 3:
        return dict(surface_confidence=0., slope_rad=0., cross_slope_rad=0.,
                    roughness_m=0., flat_cost=2.)
    c, s = math.cos(angle), math.sin(angle)
    slope = abs(math.atan(plane[0]*c+plane[1]*s))
    cross = abs(math.atan(-plane[0]*s+plane[1]*c))
    rough = float(np.quantile(np.abs(heights-design @ plane), .9))
    confidence = float(min(1., len(centers)/20)*min(1., support/.4)*floor_confidence)
    return dict(surface_confidence=confidence, slope_rad=slope, cross_slope_rad=cross,
                roughness_m=rough, flat_cost=float(1.5*slope+2*cross+rough/.025+.25*(1-min(1., support/.6))))


def preferred_surface(directions):
    """Hard obstacle exclusion first, flatness second, straight on near ties."""
    center = min(directions, key=lambda r: abs(r["heading"]))
    eligible = [r for r in directions if r["obstacle"] == "none" and r["clearance_m"] >= .55 and
                r.get("surface_confidence", 0) >= .35 and r["support_until_m"] >= .3]
    if not eligible:
        return 0.
    score = lambda r: r["flat_cost"] + .10*abs(r["heading"])
    best = min(eligible, key=score)
    if center in eligible and score(center) <= score(best)+.10:
        return 0.
    return float(best["heading"])


def neural_features(scene):
    """Ground-removed hazard proximity; no raw floor distance enters LC4."""
    result = dict(source="surface_v1", left=0., right=0.,
                  preferred_heading_rad=float(scene.get("preferred_heading_rad", 0.)),
                  floor_confidence=float(scene.get("floor", {}).get("confidence", 0.)))
    for side, sign in (("left", 1), ("right", -1)):
        rays = [r for r in scene["directions"] if r["heading"]*sign >= 0 and r["obstacle"] != "none"]
        result[side] = max((float(np.clip((.8-r["clearance_m"])/.8, 0, 1)) for r in rays), default=0.)
    return result
