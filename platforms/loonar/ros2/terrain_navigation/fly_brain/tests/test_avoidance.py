import copy
import numpy as np
import pytest

from loonar_fly.avoidance import Avoidance, scene_from_points
from loonar_fly.interface import rates_from_features, WallTimeReadout


def floor():
    x, y = np.meshgrid(np.arange(.16, 1.04, .01), np.arange(-.8, .81, .01))
    return np.column_stack((x.ravel(), y.ravel(), np.full(x.size, -.098)))


def surface(height, start=.35):
    points = floor()
    points[points[:, 0] >= start, 2] += height
    return scene_from_points(points)


def front(scene):
    return scene['directions'][3]


def test_ground_and_small_step_remain_drivable():
    for height, mode, cap in ((0, 'cruise', .2), (.02, 'low_step', .05)):
        scene = surface(height)
        assert front(scene)['obstacle'] == 'none'
        assert not front(scene)['unknown_ground']
        decision = Avoidance().update(scene, 0, '1')
        assert decision['mode'] == mode
        assert decision['speed_cap_mps'] == cap


@pytest.mark.parametrize('height,kind', [(.20, 'wall'), (.08, 'step_up'), (-.08, 'drop')])
def test_measured_hazards_turn_before_body_reaches_them(height, kind):
    scene = surface(height)
    assert front(scene)['obstacle'] == kind
    decision = Avoidance().update(scene, 0, '1')
    assert decision['mode'] == 'turn'
    cmd = Avoidance.command(dict(linear_mps=.2, angular_rps=0), decision)
    assert cmd['linear_mps'] == 0
    assert abs(cmd['angular_rps']) == .5


def test_missing_ground_is_unknown_and_scans_without_inventing_a_drop():
    points = floor()
    scene = scene_from_points(points[points[:, 0] < .3])
    assert front(scene)['unknown_ground']
    assert front(scene)['obstacle'] == 'none'
    decision = Avoidance().update(scene, 0, '1')
    assert decision['mode'] == 'scan'
    assert decision['speed_cap_mps'] == 0
    assert abs(Avoidance.command(dict(linear_mps=.2, angular_rps=0), decision)['angular_rps']) == .35


def test_approach_slows_and_tonic_forward_stimulus_falls():
    decision = Avoidance().update(surface(.2, .55), 0, '1')
    assert decision['mode'] == 'approach'
    assert 0 < decision['speed_cap_mps'] < .1
    features = dict(depth={s: dict(proximity=.5) for s in ('left', 'right')}, avoidance=decision)
    rates = rates_from_features(features, 150)
    assert 0 < rates['DNp09_left'] == rates['DNp09_right'] < 75
    features['avoidance'] = Avoidance().update(surface(.2), 0, '2')
    rates = rates_from_features(features, 150)
    assert rates['DNp09_left'] == rates['DNp09_right'] == 0
    assert rates['LC4_left'] > rates['LC4_right']  # tie selects right turn


def test_turn_direction_latches_then_releases_on_sustained_open_path():
    adapter = Avoidance()
    scene = surface(.2)
    first = adapter.update(scene, 0, '0')
    assert first['turn_sign'] == -1
    # Make the opposite side look best. A committed turn must not chatter.
    changed = copy.deepcopy(scene)
    for ray in changed['directions'][4:]:
        ray.update(clearance_m=.9, support_until_m=.9)
    for i in range(1, 10):
        decision = adapter.update(changed, i*.1, str(i))
        assert decision['turn_sign'] == -1
        assert decision['mode'] == 'turn'
    opened = surface(0)
    assert adapter.update(opened, 1., '10')['mode'] == 'turn'
    assert adapter.update(opened, 1.1, '11')['mode'] == 'turn'
    decision = adapter.update(opened, 1.4, '12')
    assert decision['mode'] == 'cruise'
    assert decision['turn_sign'] == 0


def test_chooses_open_side_and_can_change_when_measured_turn_is_blocked():
    scene = surface(.2)
    for ray in scene['directions'][4:]:
        ray.update(clearance_m=.9, support_until_m=.9)
    adapter = Avoidance()
    assert adapter.update(scene, 0, '0')['turn_sign'] == 1
    scene['turn_clear']['left'] = False
    assert adapter.update(scene, .1, '1')['turn_sign'] == -1
    scene['turn_clear']['right'] = False
    decision = adapter.update(scene, .2, '2')
    assert decision['mode'] == 'no_turn_room'
    assert Avoidance.command(dict(linear_mps=.2, angular_rps=.6), decision) == dict(linear_mps=0, angular_rps=0)


def test_approach_rate_and_same_frame_not_recounted():
    adapter = Avoidance()
    adapter.update(surface(.2, .8), 0, '0')
    decision = adapter.update(surface(.2, .60), .1, '1')
    assert decision['closing_mps'] > .3
    assert decision['mode'] == 'turn'
    assert adapter.update(surface(0), .2, '1') == decision


def test_sparse_outlier_does_not_make_a_wall():
    points = np.vstack((floor(), [.4, 0, .3]))
    assert front(scene_from_points(points))['obstacle'] == 'none'
    assert Avoidance().update(scene_from_points(points), 0, '1')['mode'] == 'cruise'


def test_real_time_readout_decays_without_waiting_for_neural_time():
    readout = WallTimeReadout()
    assert readout.update(dict(DNp09_left=150), 10)['DNp09_left'] == 150
    assert readout.update(dict(DNp09_left=0), 10.3)['DNp09_left'] < 13
    assert readout.update(dict(DNp09_left=0), 11.2)['DNp09_left'] == 0


def test_empty_observations_cannot_be_claimed_free():
    scene = scene_from_points(np.empty((0, 3)))
    assert not scene['ready']
    assert Avoidance().update(scene, 0, '0')['mode'] == 'await_scene'


def test_only_one_supported_wheel_path_is_unknown():
    points = floor()
    points = points[~((points[:, 0] > .3) & (points[:, 1] < 0))]
    scene = scene_from_points(points)
    assert front(scene)['unknown_ground']
    assert front(scene)['obstacle'] == 'none'
    assert Avoidance().update(scene, 0, '0')['mode'] == 'scan'


def test_actual_swept_footprint_distinguishes_near_wall_from_turn_room():
    assert surface(.2, .35)['turn_clear'] == dict(left=True, right=True)
    assert surface(.2, .18)['turn_clear'] == dict(left=False, right=False)


def test_floor_returns_sharing_a_wall_cell_do_not_block_turns():
    points = np.array([[.151, .02, -.098], [.153, .02, -.098], [.155, .02, -.098],
                       [.198, .02, .15], [.198, .021, .16], [.198, .022, .17]])
    scene = scene_from_points(points)
    assert front(scene)['obstacle'] == 'wall'
    assert scene['turn_clear'] == dict(left=True, right=True)
