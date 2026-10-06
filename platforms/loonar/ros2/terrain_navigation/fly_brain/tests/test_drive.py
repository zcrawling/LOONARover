from loonar_fly.drive import DriveGate
import pytest


def test_stable_fresh_stream_and_clamps():
    gate = DriveGate()
    candidate = dict(linear_mps=2, angular_rps=-4)
    assert gate.evaluate(0, "", candidate) == (False, 0, 0)
    assert 0 < gate.evaluate(.6, "", candidate)[1] <= .01 + 1e-9
    assert gate.evaluate(.7, "depth expired", candidate) == (False, 0, 0)
    assert gate.evaluate(.8, "", candidate) == (False, 0, 0)
    assert 0 < gate.evaluate(1.4, "", candidate)[1] <= .01 + 1e-9
    for i in range(1, 50):
        enabled, v, w = gate.evaluate(1.4 + i*.05, "", candidate)
    assert enabled and v == .2 and w == -.6


def test_stop_latches_and_duration_is_bounded():
    gate = DriveGate(max_drive_seconds=2)
    candidate = dict(linear_mps=.01, angular_rps=0)
    gate.evaluate(0, "", candidate)
    assert gate.evaluate(1, "", candidate)[0]
    assert not gate.evaluate(3.01, "", candidate)[0]
    assert not gate.evaluate(4, "", candidate)[0]
    gate = DriveGate()
    gate.halt("Ctrl+C")
    assert not gate.evaluate(100, "", candidate)[0]


def test_nonfinite_motion_is_rejected():
    gate = DriveGate(settle_seconds=0)
    assert gate.evaluate(0, "", dict(linear_mps=float('nan'), angular_rps=0)) == (False, 0, 0)


def test_user_speed_ceiling_cannot_be_exceeded_by_configuration():
    for speed in (1.0, .20001, 0, -1, float('nan'), float('inf')):
        with pytest.raises(ValueError):
            DriveGate(max_speed=speed)
    assert DriveGate(max_speed=.2).max_speed == .2
