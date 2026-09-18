#!/usr/bin/env python3
"""Create an offline, sequential ICP preview PLY from a ROS 2 PointCloud2 bag.

This is intentionally a diagnostic tool, not the rover's mapping pipeline.  It
reads a limited number of recorded PointCloud2 frames, downsamples every frame,
aligns each frame to its predecessor with point-to-point ICP, and writes a
binary PLY that CloudCompare or MeshLab can open.

It neither needs nor uses TF/odometry.  Consequently, accumulated drift is
expected; use it to inspect the LIMO depth data and decide whether later 2.5D
work is worthwhile.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Iterable

import numpy as np
from rosbags.highlevel import AnyReader
from rosbags.typesys import Stores, get_typestore
from scipy.spatial import cKDTree


POINTFIELD_FLOAT32 = 7
POINTFIELD_FLOAT64 = 8
FIELD_DTYPES = {
    POINTFIELD_FLOAT32: "<f4",
    POINTFIELD_FLOAT64: "<f8",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bag", type=Path, help="ROS 2 bag directory containing metadata.yaml")
    parser.add_argument("--topic", default="/tof/depth/points", help="PointCloud2 topic")
    parser.add_argument("--output", type=Path, default=Path("icp_preview.ply"), help="output binary PLY")
    parser.add_argument("--poses-csv", type=Path, default=Path("icp_poses.csv"), help="output ICP result CSV")
    parser.add_argument("--stride", type=int, default=5, help="use one frame every N recorded frames")
    parser.add_argument("--max-frames", type=int, default=60, help="maximum selected frames")
    parser.add_argument("--voxel-m", type=float, default=0.03, help="per-frame/final voxel size in metres")
    parser.add_argument("--max-correspondence-m", type=float, default=0.15, help="ICP correspondence limit in metres")
    parser.add_argument("--iterations", type=int, default=30, help="maximum ICP iterations per frame pair")
    parser.add_argument("--min-z-m", type=float, default=0.15, help="discard points nearer than this")
    parser.add_argument("--max-z-m", type=float, default=8.0, help="discard points farther than this")
    parser.add_argument("--max-points-per-frame", type=int, default=20000, help="post-voxel point cap per frame")
    args = parser.parse_args()
    if args.stride < 1 or args.max_frames < 2 or args.voxel_m <= 0 or args.max_correspondence_m <= 0:
        parser.error("stride/max-frames and metric limits must be positive; max-frames must be at least 2")
    return args


def point_field_dtype(fields: Iterable[object], point_step: int) -> np.dtype:
    by_name = {field.name: field for field in fields}
    required = ("x", "y", "z")
    missing = [name for name in required if name not in by_name]
    if missing:
        raise ValueError(f"PointCloud2 is missing fields: {', '.join(missing)}")
    formats: list[str] = []
    offsets: list[int] = []
    for name in required:
        field = by_name[name]
        if field.datatype not in FIELD_DTYPES or field.count != 1:
            raise ValueError(f"unsupported {name} PointField datatype/count")
        formats.append(FIELD_DTYPES[field.datatype])
        offsets.append(field.offset)
    return np.dtype({"names": required, "formats": formats, "offsets": offsets, "itemsize": point_step})


def points_from_message(message: object, min_z: float, max_z: float) -> np.ndarray:
    dtype = point_field_dtype(message.fields, message.point_step)
    count = message.width * message.height
    array = np.frombuffer(message.data, dtype=dtype, count=count)
    points = np.column_stack((array["x"], array["y"], array["z"])).astype(np.float64, copy=False)
    mask = np.isfinite(points).all(axis=1) & (points[:, 2] >= min_z) & (points[:, 2] <= max_z)
    return points[mask]


def voxel_downsample(points: np.ndarray, voxel: float, cap: int) -> np.ndarray:
    if len(points) == 0:
        return points
    keys = np.floor(points / voxel).astype(np.int32)
    _, indices = np.unique(keys, axis=0, return_index=True)
    result = points[np.sort(indices)]
    if len(result) > cap:
        result = result[np.linspace(0, len(result) - 1, cap, dtype=np.int64)]
    return result


def transform_points(points: np.ndarray, transform: np.ndarray) -> np.ndarray:
    return points @ transform[:3, :3].T + transform[:3, 3]


def best_fit_transform(source: np.ndarray, target: np.ndarray) -> np.ndarray:
    source_center = source.mean(axis=0)
    target_center = target.mean(axis=0)
    source_zero = source - source_center
    target_zero = target - target_center
    u, _, vt = np.linalg.svd(source_zero.T @ target_zero)
    rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0:
        vt[-1, :] *= -1
        rotation = vt.T @ u.T
    transform = np.eye(4)
    transform[:3, :3] = rotation
    transform[:3, 3] = target_center - rotation @ source_center
    return transform


def icp(source: np.ndarray, target: np.ndarray, distance_limit: float, iterations: int) -> tuple[np.ndarray, float, float]:
    if len(source) < 20 or len(target) < 20:
        raise ValueError("too few points after filtering/downsampling")
    tree = cKDTree(target)
    transform = np.eye(4)
    fitness = 0.0
    rmse = float("inf")
    for _ in range(iterations):
        moved = transform_points(source, transform)
        distances, matches = tree.query(moved, distance_upper_bound=distance_limit)
        keep = np.isfinite(distances) & (matches < len(target))
        if keep.sum() < 20:
            raise ValueError("too few ICP correspondences; decrease frame stride or increase correspondence limit")
        delta = best_fit_transform(moved[keep], target[matches[keep]])
        transform = delta @ transform
        new_rmse = float(np.sqrt(np.mean(distances[keep] ** 2)))
        fitness = float(keep.mean())
        if abs(rmse - new_rmse) < 1e-5:
            rmse = new_rmse
            break
        rmse = new_rmse
    return transform, fitness, rmse


def write_ply(path: Path, points: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.asarray(points, dtype="<f4")
    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        f"element vertex {len(data)}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "end_header\n"
    ).encode("ascii")
    with path.open("wb") as output:
        output.write(header)
        data.tofile(output)


def main() -> int:
    args = parse_args()
    if not (args.bag / "metadata.yaml").is_file():
        raise SystemExit(f"not a ROS 2 bag directory: {args.bag}")

    frames: list[tuple[int, np.ndarray]] = []
    # LIMO records ROS 2 Humble bags.  Its SQLite metadata does not embed the
    # message definitions, so provide the matching standard ROS type store.
    with AnyReader([args.bag], default_typestore=get_typestore(Stores.ROS2_HUMBLE)) as reader:
        connections = [connection for connection in reader.connections if connection.topic == args.topic]
        if not connections:
            available = "\n  ".join(sorted({connection.topic for connection in reader.connections}))
            raise SystemExit(f"topic not found: {args.topic}\nAvailable topics:\n  {available}")
        for index, (connection, timestamp, rawdata) in enumerate(reader.messages(connections=connections)):
            if index % args.stride:
                continue
            message = reader.deserialize(rawdata, connection.msgtype)
            raw_points = points_from_message(message, args.min_z_m, args.max_z_m)
            points = voxel_downsample(raw_points, args.voxel_m, args.max_points_per_frame)
            if len(points) >= 20:
                frames.append((timestamp, points))
            if len(frames) >= args.max_frames:
                break

    if len(frames) < 2:
        raise SystemExit("fewer than two usable frames; adjust range/stride or record a longer bag")

    poses: list[tuple[int, np.ndarray, float, float, int]] = []
    global_points: list[np.ndarray] = [frames[0][1]]
    previous_pose = np.eye(4)
    previous_points = frames[0][1]
    poses.append((frames[0][0], previous_pose, 1.0, 0.0, len(previous_points)))
    print(f"frame 0: points={len(previous_points)} pose=identity")

    for index, (timestamp, current_points) in enumerate(frames[1:], start=1):
        try:
            relative, fitness, rmse = icp(
                current_points, previous_points, args.max_correspondence_m, args.iterations
            )
        except ValueError as error:
            print(f"frame {index}: skipped ({error})")
            continue
        pose = previous_pose @ relative
        global_points.append(transform_points(current_points, pose))
        poses.append((timestamp, pose, fitness, rmse, len(current_points)))
        previous_pose = pose
        previous_points = current_points
        print(f"frame {index}: points={len(current_points)} fitness={fitness:.3f} rmse_m={rmse:.4f}")

    merged = voxel_downsample(np.vstack(global_points), args.voxel_m, cap=np.iinfo(np.int32).max)
    write_ply(args.output, merged)
    args.poses_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.poses_csv.open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["timestamp_ns", "fitness", "rmse_m", "point_count", *[f"t{i}{j}" for i in range(4) for j in range(4)]])
        for timestamp, pose, fitness, rmse, count in poses:
            writer.writerow([timestamp, fitness, rmse, count, *pose.reshape(-1)])
    print(f"wrote {len(merged)} points to {args.output}")
    print(f"wrote {len(poses)} pose records to {args.poses_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
