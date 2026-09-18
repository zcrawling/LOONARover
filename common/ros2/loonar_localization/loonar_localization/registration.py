"""Bounded stop keyframes and point-to-plane ICP with observability rejection."""
from dataclasses import dataclass
import numpy as np
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation


def pose_matrix(p):
    T = np.eye(4)
    T[:3, :3] = Rotation.from_euler('z', p[2]).as_matrix()
    T[:2, 3] = p[:2]
    return T


def transform(T, points):
    return points @ T[:3, :3].T + T[:3, 3]


@dataclass
class ICPConfig:
    mode: str = 'gyro_yaw'
    voxel: float = .04
    max_points: int = 4000
    max_range: float = 3.
    correspondence: float = .15
    iterations: int = 40
    min_pairs: int = 80
    min_inlier_ratio: float = .5
    max_rmse: float = .035
    min_eigen_ratio: float = .002
    max_tilt: float = .15
    tolerance: float = 1e-5

    def __post_init__(self):
        if self.mode not in ('gyro_yaw', 'full_6d'):
            raise ValueError('mode must be gyro_yaw or full_6d')
        if min(self.voxel, self.max_range, self.correspondence, self.max_rmse, self.tolerance, self.max_tilt) <= 0:
            raise ValueError('ICP metric thresholds must be positive')
        if self.iterations < 1 or self.min_pairs < 15 or self.max_points < self.min_pairs:
            raise ValueError('invalid ICP iteration/point limits')
        if not 0 < self.min_inlier_ratio <= 1 or not 0 < self.min_eigen_ratio <= 1:
            raise ValueError('invalid ICP quality ratios')


def prepare(points, c):
    p = np.asarray(points, dtype=float).reshape(-1, 3)
    p = p[np.isfinite(p).all(axis=1)]
    p = p[(np.linalg.norm(p, axis=1) > .1) & (np.linalg.norm(p, axis=1) < c.max_range)]
    if len(p):
        _, ids = np.unique(np.floor(p/c.voxel).astype(int), axis=0, return_index=True)
        p = p[np.sort(ids)]
    if len(p) > c.max_points:
        p = p[np.linspace(0, len(p)-1, c.max_points, dtype=int)]
    return p


def register(target, source, initial=None, config=None):
    """Return T_target_source. Independent gate; initial agreement is not evidence."""
    c = config or ICPConfig()
    A, B = prepare(target, c), prepare(source, c)
    result = dict(accepted=False, reason='insufficient_points', converged=False)
    if min(len(A), len(B)) < c.min_pairs:
        return result
    tree = cKDTree(A)
    _, ids = tree.query(A, k=min(15, len(A)))
    neighbors = A[ids]; centered = neighbors-neighbors.mean(axis=1, keepdims=True)
    values, vectors = np.linalg.eigh(np.einsum('nki,nkj->nij', centered, centered))
    normals = vectors[:, :, 0]
    valid_normals = values[:, 0]/np.maximum(values.sum(axis=1), 1e-12) < .1
    T = np.eye(4) if initial is None else np.array(initial, copy=True)
    fixed_yaw = Rotation.from_matrix(T[:3, :3]).as_euler('xyz')[2]

    def constrained_jacobian(current, source_points, normals):
        # Roll/pitch are nuisance variables; yaw remains the gyro prior exactly.
        angles = Rotation.from_matrix(current[:3, :3]).as_euler('xyz')
        columns = []
        for axis in (0, 1):
            plus = angles.copy(); minus = angles.copy()
            plus[axis] += 1e-6; minus[axis] -= 1e-6
            derivative = (Rotation.from_euler('xyz', plus).as_matrix()-
                          Rotation.from_euler('xyz', minus).as_matrix())/2e-6
            columns.append(np.sum((source_points@derivative.T)*normals, axis=1))
        return np.column_stack([*columns, normals])

    converged = False
    for _ in range(c.iterations):
        P = transform(T, B)
        distances, ids = tree.query(P)
        good = (distances < c.correspondence) & valid_normals[ids]
        if good.sum() < c.min_pairs:
            return dict(result, reason='insufficient_correspondences')
        X, Y, N = P[good], A[ids[good]], normals[ids[good]]
        residual = np.sum(N*(X-Y), axis=1)
        J = constrained_jacobian(T, B[good], N) if c.mode == 'gyro_yaw' else np.column_stack([np.cross(X, N), N])
        delta = np.linalg.lstsq(J, -residual, rcond=None)[0]
        if not np.isfinite(delta).all():
            return dict(result, reason='nonfinite_solution')
        if c.mode == 'gyro_yaw':
            angles = Rotation.from_matrix(T[:3, :3]).as_euler('xyz')
            angles[:2] += delta[:2]; angles[2] = fixed_yaw
            T[:3, :3] = Rotation.from_euler('xyz', angles).as_matrix()
            T[:3, 3] += delta[2:]
        else:
            D = np.eye(4); D[:3, :3] = Rotation.from_rotvec(delta[:3]).as_matrix(); D[:3, 3] = delta[3:]
            T = D@T
        if np.linalg.norm(delta) < c.tolerance:
            converged = True
            break
    P = transform(T, B); distances, ids = tree.query(P)
    good = (distances < c.correspondence) & valid_normals[ids]
    X, Y, N = P[good], A[ids[good]], normals[ids[good]]
    if len(X) < c.min_pairs:
        return dict(result, reason='insufficient_final_correspondences')
    # Center and scale rotational columns to avoid origin/range-dependent conditioning.
    centered = X-X.mean(axis=0); scale = max(np.sqrt(np.mean(np.sum(centered**2, axis=1))), .1)
    J = np.column_stack([np.cross(centered, N)/scale, N])
    if c.mode == 'gyro_yaw':
        J = constrained_jacobian(T, B[good]-B[good].mean(axis=0), N)
        J[:, :2] /= scale
    eig = np.linalg.eigvalsh(J.T@J/len(J)); ratio = float(eig[0]/max(eig[-1], 1e-12))
    rmse = float(np.sqrt(np.mean(np.sum((X-Y)**2, axis=1))))
    inliers = float(good.mean()); tilt = float(np.linalg.norm(Rotation.from_matrix(T[:3, :3]).as_euler('xyz')[:2]))
    checks = [(converged, 'not_converged'), (inliers >= c.min_inlier_ratio, 'low_inlier_ratio'),
              (rmse <= c.max_rmse, 'high_rmse'), (ratio >= c.min_eigen_ratio, 'degenerate'),
              (tilt <= c.max_tilt, 'outside_planar_correction')]
    failed = [reason for ok, reason in checks if not ok]
    return dict(accepted=not failed, reason=','.join(failed) or 'accepted', converged=converged,
                rmse=rmse, inlier_ratio=inliers, correspondences=int(good.sum()), eigen_ratio=ratio,
                mode=c.mode, fixed_yaw_rad=float(fixed_yaw),
                point_plane_rmse=float(np.sqrt(np.mean(np.sum(N*(X-Y), axis=1)**2))),
                tilt_rad=tilt, transform=T.tolist())


class StopCorrection:
    """Last accepted anchor survives rejection; only map->odom may change."""
    def __init__(self, config=None, minimum_travel=.02):
        self.c = config or ICPConfig()
        self.minimum_travel = minimum_travel
        self.anchor = None
        self.map_odom = np.eye(4)
        self.last_stop_id = None
        self.failures = 0

    def submit(self, stop_id, stamp, cloud, odom_pose, wheel_distance):
        if stop_id == self.last_stop_id:
            return dict(accepted=False, reason='already_processed_stop')
        p = prepare(cloud, self.c)
        if len(p) < self.c.min_pairs:
            return dict(accepted=False, reason='insufficient_points', prepared_points=len(p), required_points=self.c.min_pairs)
        self.last_stop_id = stop_id
        O = pose_matrix(odom_pose)
        if self.anchor is None:
            self.anchor = (stamp, p, O, self.map_odom@O, wheel_distance)
            return dict(accepted=False, reason='anchor_initialized', anchor_stamp=stamp)
        old_stamp, A, old_O, map_A, old_distance = self.anchor
        if stamp <= old_stamp:
            return dict(accepted=False, reason='stale_keyframe')
        quality = register(A, p, np.linalg.inv(old_O)@O, self.c)
        quality.update(stamp=stamp, anchor_stamp=old_stamp)
        if not quality['accepted']:
            self.failures += 1
            quality['uncertainty_growth'] = self.failures
            return quality
        relative = np.array(quality['transform'])
        yaw = float(Rotation.from_matrix(relative[:3, :3]).as_euler('xyz')[2])
        if self.c.mode == 'gyro_yaw':
            yaw = float(odom_pose[2]-Rotation.from_matrix(old_O[:3, :3]).as_euler('xyz')[2])
        planar = pose_matrix([relative[0, 3], relative[1, 3], yaw])
        map_B = map_A@planar
        self.map_odom = map_B@np.linalg.inv(O)
        body_motion = float(np.linalg.norm(planar[:2, 3])); wheel_motion = wheel_distance-old_distance
        quality.update(map_odom=self.map_odom.tolist(), corrected_stop_pose=map_B.tolist(),
                       translation_xyz=relative[:3, 3].tolist(), yaw_correction_applied=self.c.mode != 'gyro_yaw',
                       body_translation=body_motion, wheel_travel=wheel_motion,
                       state='STUCK_SUSPECT' if wheel_motion > self.minimum_travel*5 and body_motion < self.minimum_travel else 'VALID')
        self.anchor = (stamp, p, O, map_B, wheel_distance)
        self.failures = 0
        return quality
