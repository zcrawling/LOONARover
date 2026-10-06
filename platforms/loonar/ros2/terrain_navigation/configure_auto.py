"""Use the SAME registry/geometry and runtime sockets as the existing backend."""

import json
from pathlib import Path
import sys
import yaml


def configure(registry, sample_socket, workspace):
    registry = Path(registry).resolve()
    sample_socket = Path(sample_socket).resolve()
    geometry = json.loads(registry.read_text())["devices"]["control"]["geometry"]
    config = yaml.safe_load((workspace / "terrain.local.yaml").read_text())
    p = config["/**"]["ros__parameters"]
    radius, track = float(geometry["radius_m"]), float(geometry["track_m"])
    if not (0 < radius < 1 and 0 < track <= p["robot_width"]):
        raise ValueError(
            "Registry radius/track invalid or wider than configured footprint"
        )
    # Preserve configured ground-relative limits when registry axle height differs.
    height_shift = float(p["wheel_radius"]) - radius
    p.update(
        registry=str(registry),
        sample_socket=str(sample_socket),
        gateway_socket=str(sample_socket.parent / "gateway/ros.sock"),
        wheel_radius=radius,
        wheel_track=track,
        collision_min_height=float(p["collision_min_height"]) + height_shift,
        collision_max_height=float(p["collision_max_height"]) + height_shift,
        self_z_min=float(p["self_z_min"]) + height_shift,
        self_z_max=float(p["self_z_max"]) + height_shift,
        source="sdk",
        helper=str(
            workspace
            / "install/pi5/loonar_tof_adapter/lib/loonar_tof_adapter/cubeeye_capture"
        ),
    )
    if not Path(p["helper"]).is_file():
        raise FileNotFoundError(p["helper"])
    output = workspace / "log/auto-runtime.yaml"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(config, sort_keys=False))
    return output


if __name__ == "__main__":
    configure(sys.argv[1], sys.argv[2], Path(__file__).resolve().parent)
