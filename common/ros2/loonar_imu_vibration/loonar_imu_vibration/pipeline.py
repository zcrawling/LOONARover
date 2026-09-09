"""Run-separated regression and causal A/B evaluation. No synthetic GT labels."""
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path

import numpy as np

from .core import AXES, SCHEMA, Config, Engine, Predictor, integrate_wheel
from .data import ground_truth, read_run, write_json


def make_dataset(runs, cfg, stride_s=0.05, gt_max_gap_s=0.2):
    if stride_s <= 0 or gt_max_gap_s <= 0:
        raise ValueError('Positive stride and GT gap required')
    result = dict(schema=SCHEMA, config=asdict(cfg), stride_s=stride_s,
                  gt_max_gap_s=gt_max_gap_s, runs={}, samples=[], exclusions={})
    for directory in runs:
        meta, records = read_run(directory)
        run_id = meta['run_id']
        if run_id in result['runs']:
            raise ValueError('Duplicate run_id')
        result['runs'][run_id] = dict(meta, directory=str(Path(directory).resolve()))
        gt = ground_truth(directory, meta, gt_max_gap_s)
        engine = Engine(cfg, Predictor(None, cfg, meta['profile_id']))
        last = -np.inf
        command = None
        counts = Counter()
        for row in records:
            if row['kind'] == 'cmd':
                command = row
                continue
            if row['kind'] not in ('imu', 'wheel'):
                continue
            sample = [row['t']]+[row[k] for k in (AXES if row['kind'] == 'imu' else ('vx', 'wz'))]
            engine.add(row['kind'], sample)
            if row['kind'] != 'wheel' or row['t']-last < stride_s-1e-6:
                continue
            last = row['t']
            _, _, reason, features = engine.estimate(last)
            if features is None:
                counts[reason] += 1
                continue
            start = last-cfg.window_s
            ds = integrate_wheel(list(engine.wheel), start, last)
            gt_ds = gt(start, last) if gt else None
            if gt_ds is None:
                counts['missing_window_gt'] += 1
            ratio = gt_ds/ds if gt_ds is not None else None
            # Opposite physical/encoder direction is outside scalar-positive model.
            if ratio is not None and ratio < 0:
                counts['opposite_direction_gt'] += 1
                ratio = None
            result['samples'].append(dict(run_id=run_id, terrain_id=meta['terrain_id'],
                preparation_id=meta['preparation_id'], start=start, end=last,
                encoder_distance_m=ds, gt_distance_m=gt_ds, c_v=ratio,
                commanded_speed=command['vx'] if command else None,
                commanded_wz=command['wz'] if command else None,
                command_stamp=command['t'] if command else None,
                actual_speed_mps=gt_ds/cfg.window_s if gt_ds is not None else None,
                features=features))
        result['exclusions'][run_id] = dict(counts)
    return result


def fit(dataset, split, group_preparation=False, alphas=(0.0, 0.1, 1.0, 10.0)):
    groups = [set(split[k]) for k in ('train', 'validation', 'test')]
    if any(not g for g in groups) or any(groups[i] & groups[j] for i in range(3) for j in range(i)):
        raise ValueError('Train/validation/test must be nonempty disjoint run sets')
    if set.union(*groups) != set(dataset['runs']):
        raise ValueError('Split must account for every run exactly once')
    if group_preparation:
        prep = [{dataset['runs'][r]['preparation_id'] for r in g} for g in groups]
        if any(prep[i] & prep[j] for i in range(3) for j in range(i)):
            raise ValueError('Terrain preparation leakage')
    profiles = {r['profile_id'] for r in dataset['runs'].values()}
    if len(profiles) != 1:
        raise ValueError('Train one sensor/mount/calibration profile at a time')
    if any(r.get('gt_kind') != 'external' for r in dataset['runs'].values()):
        raise ValueError('Initial train/test baseline requires independent external GT, not pseudo-GT')
    labeled = [s for s in dataset['samples'] if s['c_v'] is not None]
    for g in groups:
        if any(not any(s['run_id'] == r for s in labeled) for r in g):
            raise ValueError('Every split run needs labeled windows; endpoint distances cannot supply them')
    names = sorted(labeled[0]['features'])
    if any(sorted(s['features']) != names for s in labeled):
        raise ValueError('Mixed feature schemas')
    train = [s for s in labeled if s['run_id'] in groups[0]]
    x = np.array([[s['features'][k] for k in names] for s in train])
    y = np.array([s['c_v'] for s in train])
    if not np.isfinite(x).all() or not np.isfinite(y).all() or len(train) < 2:
        raise ValueError('Invalid training data')
    mean, scale = x.mean(0), np.maximum(x.std(0), 1e-6)
    z = (x-mean)/scale
    intercept = float(y.mean())
    candidates = []
    for alpha in alphas:
        if not np.isfinite(alpha) or alpha < 0:
            raise ValueError('Nonnegative finite ridge alpha required')
        # alpha=0 is OLS; augmented least squares also handles rank deficiency.
        a = np.vstack([z, np.sqrt(alpha)*np.eye(len(names))])
        b = np.r_[y-intercept, np.zeros(len(names))]
        coef = np.linalg.lstsq(a, b, rcond=None)[0]
        errors = []
        for run in groups[1]:
            rows = [s for s in labeled if s['run_id'] == run]
            prediction = ((np.array([[s['features'][k] for k in names] for s in rows])-mean)/scale) @ coef+intercept
            errors.append(float(np.mean(np.abs(prediction-np.array([s['c_v'] for s in rows])))))
        candidates.append((float(np.mean(errors)), float(alpha), coef))
    error, alpha, coef = min(candidates, key=lambda c: c[0])
    return dict(schema=SCHEMA, config=dataset['config'], profile_id=next(iter(profiles)),
                feature_names=names, mean=mean.tolist(), scale=scale.tolist(), coef=coef.tolist(),
                intercept=intercept, alpha=alpha, split=split, preparation_split=group_preparation,
                validation_run_mean_c_mae=error,
                validation_candidates=[{'alpha': a, 'run_mean_c_mae': e} for e,a,c in candidates],
                approved_for_use=False, uncertainty='feature-support only; not a probability')


def evaluate_run(directory, model, cfg, min_c=0.0, max_c=2.0, max_z=6.0, gt_max_gap_s=0.2, min_support=0.05):
    meta, records = read_run(directory)
    gt = ground_truth(directory, meta, gt_max_gap_s)
    if gt is None:
        raise ValueError('Evaluation requires external window GT')
    predictor = Predictor(model, cfg, meta['profile_id'], min_c, max_c, max_z, min_support)
    engine = Engine(cfg, predictor)
    previous = None
    start = None
    baseline = corrected = 0.0
    errors_a, errors_b, factors, c_errors = [], [], [], []
    reasons = Counter()
    coverage_missing = 0
    for row in records:
        if row['kind'] not in ('imu', 'wheel'):
            continue
        sample = [row['t']]+[row[k] for k in (AXES if row['kind'] == 'imu' else ('vx','wz'))]
        engine.add(row['kind'], sample)
        if row['kind'] != 'wheel':
            continue
        t = row['t']
        c, score, reason, f = engine.estimate(t)
        if previous is not None:
            if start is None:
                start = previous
            ds = row['vx']*(t-previous)
            baseline += ds
            corrected += c*ds
            truth = gt(start, t)
            if truth is None:
                coverage_missing += 1
            else:
                errors_a.append(baseline-truth)
                errors_b.append(corrected-truth)
            factors.append(c)
            reasons[reason] += 1
            if f is not None:
                den = integrate_wheel(list(engine.wheel), t-cfg.window_s, t)
                num = gt(t-cfg.window_s, t)
                if num is not None:
                    c_errors.append(c-num/den)
        previous = t
    if not errors_a or coverage_missing:
        raise ValueError('GT must cover the whole evaluated run without gaps; crop runs explicitly')
    truth = gt(start, previous)
    return dict(run_id=meta['run_id'], terrain_id=meta['terrain_id'], no_slip=meta.get('no_slip', False),
                gt_distance_m=truth, baseline_distance_m=baseline, corrected_distance_m=corrected,
                baseline_final_error_m=errors_a[-1], corrected_final_error_m=errors_b[-1],
                baseline_relative_error=abs(errors_a[-1]/truth) if abs(truth)>1e-6 else None,
                corrected_relative_error=abs(errors_b[-1]/truth) if abs(truth)>1e-6 else None,
                baseline_distance_rmse_m=float(np.sqrt(np.mean(np.square(errors_a)))),
                corrected_distance_rmse_m=float(np.sqrt(np.mean(np.square(errors_b)))),
                c_window_rmse=float(np.sqrt(np.mean(np.square(c_errors)))) if c_errors else None,
                c_mean=float(np.mean(factors)), c_min=float(min(factors)), c_max=float(max(factors)),
                c_quantiles=np.quantile(factors, [0.05, 0.5, 0.95]).tolist(), reasons=dict(reasons),
                spatial_trajectory_error=None,
                limitation='Longitudinal displacement only; no independent yaw/lateral correction or spatial ATE')
