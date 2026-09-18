"""Original V1 midpoint integration, shared by offline and streaming estimators."""
import numpy as np


def integrate_trajectory(t, v, w, initial=None):
    pose = np.zeros(3) if initial is None else np.asarray(initial, dtype=float)
    t, v, w = (np.asarray(x, dtype=float) for x in (t, v, w))
    if len(t) == 0 or len(t) != len(v) or len(t) != len(w):
        raise ValueError('nonempty equally sized samples required')
    if not np.isfinite(np.r_[t, v, w, pose]).all() or np.any(np.diff(t) <= 0):
        raise ValueError('finite, strictly increasing samples required')
    theta = pose[2] + np.r_[0., np.cumsum(np.diff(t)*(w[1:]+w[:-1])/2)]
    ds = np.diff(t)*(v[1:]+v[:-1])/2
    mid = (theta[1:]+theta[:-1])/2
    return np.column_stack([pose[0]+np.r_[0.,np.cumsum(ds*np.cos(mid))],
                            pose[1]+np.r_[0.,np.cumsum(ds*np.sin(mid))],theta])
