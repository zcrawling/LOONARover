"""Offline gyro-yaw constrained registration of two base-frame XYZ .npy clouds."""
import argparse
import json
from pathlib import Path
import numpy as np
from .registration import ICPConfig, pose_matrix, register


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=Path, required=True, help='STOP A base_link XYZ in metres')
    parser.add_argument('--source', type=Path, required=True, help='STOP B base_link XYZ in metres')
    parser.add_argument('--yaw-deg', type=float, required=True, help='Bias-corrected gyro yaw B minus A')
    parser.add_argument('--initial-x', type=float, default=0., help='DR displacement in STOP A frame, metres')
    parser.add_argument('--initial-y', type=float, default=0.)
    parser.add_argument('--correspondence', type=float, default=.15)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    initial = pose_matrix([args.initial_x,args.initial_y,np.radians(args.yaw_deg)])
    result = register(np.load(args.target,allow_pickle=False),np.load(args.source,allow_pickle=False),
                      initial,ICPConfig(correspondence=args.correspondence))
    result['initial_transform'] = initial.tolist()
    result['target'] = str(args.target); result['source'] = str(args.source)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps(result,indent=2,allow_nan=False))

if __name__ == '__main__':main()
