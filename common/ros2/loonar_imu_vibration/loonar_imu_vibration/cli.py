"""Offline commands; usable without ROS installed (bag export uses rosbags)."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path

import numpy as np

from .core import Config
from .data import export_bag, write_json
from .pipeline import evaluate_run, fit, make_dataset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    export = sub.add_parser('export-bag')
    export.add_argument('bag')
    export.add_argument('--output', required=True)
    for field in ('run-id', 'terrain-id', 'preparation-id', 'profile-id'):
        export.add_argument('--'+field, required=True)
    export.add_argument('--imu-topic', default='/imu/data')
    export.add_argument('--wheel-topic', default='/wheel/odom')
    export.add_argument('--gt-topic')
    export.add_argument('--gt-base-frame', default='base_link')
    export.add_argument('--cmd-topic', default='/cmd_vel')
    export.add_argument('--gt-source')
    export.add_argument('--gt-kind', choices=['external', 'pseudo'], default='external')
    export.add_argument('--no-slip', action='store_true')
    dataset = sub.add_parser('dataset')
    dataset.add_argument('--runs', nargs='+', required=True)
    dataset.add_argument('--output', required=True)
    for k, v in asdict(Config()).items():
        dataset.add_argument('--'+k.replace('_','-'), default=v, type=str if isinstance(v, str) else float)
    dataset.add_argument('--stride-s', type=float, default=0.05)
    dataset.add_argument('--gt-max-gap-s', type=float, default=0.2)
    train = sub.add_parser('train')
    train.add_argument('dataset')
    train.add_argument('--split', required=True, help='JSON with train, validation, test run-id lists')
    train.add_argument('--output', required=True)
    train.add_argument('--split-preparations', action='store_true')
    train.add_argument('--alphas', nargs='+', type=float, default=[0, 0.1, 1, 10])
    evaluate = sub.add_parser('evaluate')
    evaluate.add_argument('dataset')
    evaluate.add_argument('--model', required=True)
    evaluate.add_argument('--output', required=True)
    evaluate.add_argument('--min-c', type=float, default=0)
    evaluate.add_argument('--max-c', type=float, default=2)
    evaluate.add_argument('--max-z', type=float, default=6)
    evaluate.add_argument('--min-support', type=float, default=0.05)
    evaluate.add_argument('--no-slip-tolerance-m', type=float, help='User-chosen degradation tolerance; no default acceptance threshold')
    args = parser.parse_args()
    if args.command == 'export-bag':
        export_bag(args)
    elif args.command == 'dataset':
        cfg = Config(**{k: getattr(args, k) for k in asdict(Config())})
        result = make_dataset(args.runs, cfg, args.stride_s, args.gt_max_gap_s)
        write_json(args.output, result)
        print(json.dumps(dict(samples=len(result['samples']), labeled=sum(s['c_v'] is not None for s in result['samples']), exclusions=result['exclusions']), indent=2))
    elif args.command == 'train':
        result = fit(json.loads(Path(args.dataset).read_text()), json.loads(Path(args.split).read_text()),
                     args.split_preparations, args.alphas)
        write_json(args.output, result)
        print('Saved OLS/Ridge baseline; improvement remains unproven until independent test evaluation.')
    else:
        data = json.loads(Path(args.dataset).read_text())
        model = json.loads(Path(args.model).read_text())
        if data['config'] != model['config']:
            raise ValueError('Dataset/model configuration mismatch')
        rows = [evaluate_run(data['runs'][r]['directory'], model, Config(**model['config']),
                             args.min_c, args.max_c, args.max_z, data['gt_max_gap_s'], args.min_support) for r in model['split']['test']]
        summary = {}
        for label, no_slip in (('no_slip', True), ('other_terrain', False)):
            selected = [r for r in rows if r['no_slip'] == no_slip]
            change = [abs(r['corrected_final_error_m'])-abs(r['baseline_final_error_m']) for r in selected]
            entry = dict(runs=len(change), mean_absolute_error_change_m=float(np.mean(change)) if change else None,
                         interpretation='negative means corrected is better', acceptance='insufficient_runs_or_unset_tolerance')
            if len(change) >= 3:
                rng = np.random.default_rng(2026)
                means = rng.choice(change, size=(5000,len(change)), replace=True).mean(axis=1)
                low, high = np.quantile(means, [0.025,0.975])
                entry['bootstrap_run_mean_change_95pct_m'] = [float(low),float(high)]
                if no_slip and args.no_slip_tolerance_m is not None:
                    if args.no_slip_tolerance_m < 0:
                        raise ValueError('Tolerance must be nonnegative')
                    entry['acceptance'] = 'pass' if high <= args.no_slip_tolerance_m else 'not_demonstrated'
                elif not no_slip:
                    entry['acceptance'] = 'improvement_supported' if high < 0 else 'not_demonstrated'
            summary[label] = entry
        write_json(args.output, dict(runs=rows, summary=summary, scope='held-out runs; no overlapping-window distance sums',
                                     caveat='Bootstrap is exploratory for small run counts. Other-terrain membership is not proof of slip.'))
        print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
