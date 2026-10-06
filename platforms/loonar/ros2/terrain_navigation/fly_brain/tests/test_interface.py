import json
from types import SimpleNamespace

import numpy as np
import pytest

from loonar_fly.interface import depth_array, encode_depth, rates_from_features, decode_candidate, ExpansionEncoder
from loonar_fly.protocol import Requests


def test_invalid_depth_never_becomes_near_obstacle_or_free_space():
    for value in (0, -1, np.nan, np.inf, 6):
        features = encode_depth(np.full((4, 6), value))
        assert features["left"]["distance_m"] is None
        assert features["left"]["valid_fraction"] == 0
        assert features["left"]["proximity"] == 0


def test_asymmetric_scene_encodes_correct_hemifield():
    depth = np.ones((4, 6), dtype=np.float32)
    depth[:, :3] = .2
    rates = rates_from_features({"depth": encode_depth(depth)})
    assert rates["LC4_left"] > 80
    assert rates["LC4_right"] == 0
    assert rates["LPLC2_left"] == 0  # missing camera is explicit zero looming


def test_padded_big_endian_image():
    data = np.array([[.2, .3, 999], [.4, .5, 999]], dtype=">f4")
    msg = SimpleNamespace(encoding="32FC1", width=2, height=2, step=12,
                          is_bigendian=True, data=data.tobytes())
    np.testing.assert_allclose(depth_array(msg), [[.2, .3], [.4, .5]])
    msg.step = 4
    with pytest.raises(ValueError):
        depth_array(msg)


def test_silent_brain_has_no_motion_fallback():
    rates = {f"{name}_{side}": 0 for name in ("DNp09", "DNa02") for side in ("left", "right")}
    candidate = decode_candidate(rates)
    assert candidate["linear_mps"] == candidate["angular_rps"] == 0
    assert candidate["actuation_enabled"] is False
    rates["DNa02_right"] = 200
    assert decode_candidate(rates)["angular_rps"] == -.6
    rates["DNp09_left"] = float("nan")
    with pytest.raises(ValueError):
        decode_candidate(rates)


def test_sensor_age_session_order_and_replay_protection():
    requests = Requests(ttl=.5)
    one = requests.issue(10, 9.9)
    two = requests.issue(10.1, 10)
    with pytest.raises(ValueError):
        requests.accept(dict(two, session="previous_run"), 10.2)
    assert requests.accept(two, 10.2) == 10
    for packet in (one, two):
        with pytest.raises(ValueError):
            requests.accept(packet, 10.2)
    three = requests.issue(10.2, 10.1)
    with pytest.raises(ValueError):
        requests.accept(three, 10.7)
    assert len(requests.pending) <= 16
    for i in range(100):
        requests.issue(11 + i*.01, 11 + i*.01)
    assert len(requests.pending) <= 16


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1, 2])
def test_reject_malformed_features(bad):
    features = {"depth": {s: {"proximity": bad} for s in ("left", "right")}}
    with pytest.raises(ValueError):
        rates_from_features(features)


def test_camera_expansion_requires_a_recent_frame_pair():
    import cv2
    rng = np.random.default_rng(123)
    texture = rng.integers(0, 256, (64, 96), dtype=np.uint8)
    bigger = cv2.warpAffine(texture, cv2.getRotationMatrix2D((47.5, 31.5), 0, 1.05), (96, 64))
    jpeg = lambda img: cv2.imencode(".jpg", img)[1].tobytes()
    encoder = ExpansionEncoder()
    assert encoder.update(jpeg(texture), 10) == {"left": 0, "right": 0}
    expansion = encoder.update(jpeg(bigger), 10.1)
    assert min(expansion.values()) > .01
    assert encoder.update(jpeg(texture), 11) == {"left": 0, "right": 0}
    with pytest.raises(ValueError):
        encoder.update(b"not a jpeg", 11.1)
