"""The integrated launcher must use the backend's calibrated geometry/socket."""

import importlib.util
import json
from pathlib import Path
import pytest
import yaml

spec = importlib.util.spec_from_file_location(
    "configure_auto", Path(__file__).resolve().parents[1] / "configure_auto.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_uses_backend_registry_and_preserves_height_limits(tmp_path):
    config = {
        "/**": {
            "ros__parameters": dict(
                robot_width=0.30,
                wheel_radius=0.10,
                collision_min_height=-0.03,
                collision_max_height=0.60,
                self_z_min=-0.08,
                self_z_max=0.40,
            )
        }
    }
    source = tmp_path / "terrain.local.yaml"
    source.write_text(yaml.safe_dump(config))
    before = source.read_bytes()
    registry = tmp_path / "control.json"
    registry.write_text(
        json.dumps(
            {"devices": {"control": {"geometry": {"radius_m": 0.11, "track_m": 0.25}}}}
        )
    )
    helper = (
        tmp_path
        / "install/pi5/loonar_tof_adapter/lib/loonar_tof_adapter/cubeeye_capture"
    )
    helper.parent.mkdir(parents=True)
    helper.touch()
    socket = tmp_path / "custom-runtime/ros-samples.sock"
    out = module.configure(registry, socket, tmp_path)
    p = yaml.safe_load(out.read_text())["/**"]["ros__parameters"]
    assert p["registry"] == str(registry)
    assert p["sample_socket"] == str(socket)
    assert p["gateway_socket"] == str(socket.parent / "gateway/ros.sock")
    assert p["wheel_radius"] == 0.11 and p["wheel_track"] == 0.25
    assert p["collision_min_height"] == pytest.approx(-0.04)
    assert p["self_z_min"] == pytest.approx(-0.09)
    assert source.read_bytes() == before
    registry.write_text(
        json.dumps(
            {"devices": {"control": {"geometry": {"radius_m": 0.11, "track_m": 0.4}}}}
        )
    )
    with pytest.raises(ValueError, match="footprint"):
        module.configure(registry, socket, tmp_path)
