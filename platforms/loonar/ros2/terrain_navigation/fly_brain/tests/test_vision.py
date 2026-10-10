import copy
import math
import numpy as np
import pytest

from loonar_fly.vision import DepthWindow, fit_floor, preferred_surface
from loonar_fly.avoidance import scene_from_points, Avoidance
from loonar_fly.interface import rates_from_features


def floor(radius=.1):
    x, y = np.meshgrid(np.arange(.16, 1.04, .012), np.arange(-.8, .81, .012))
    return np.column_stack((x.ravel(), y.ravel(), np.full(x.size, -radius)))


def test_stationary_median_removes_flying_pixel_and_never_fills_current_holes():
    window = DepthWindow()
    for i in range(4):
        z = np.full((8, 8), 1.+(-1)**i*.002)
        if i == 3:
            z[2, 2] = .2
            z[3, 3] = np.nan
        out, meta = window.update(z, i*.07, True, [0, 0, 9.81], 'camera')
    assert meta['mode'] == 'stationary_median' and meta['frames'] == 4
    assert out[2, 2] > .99
    assert np.isnan(out[3, 3])


def test_new_obstacle_patch_not_erased_by_old_floor_history():
    window = DepthWindow()
    for i in range(5):
        z = np.ones((8, 8))
        if i == 4:
            z[2:5, 2:5] = .2
        out, _ = window.update(z, i*.05, True, [0, 0, 9.81], 'camera')
    assert out[3, 3] == .2


def test_stationary_history_does_not_include_last_moving_frame():
    window = DepthWindow()
    window.update(np.full((4, 4), .1), 0., False, [0, 0, 9.81], 'camera')
    for i in range(1, 4):
        out, meta = window.update(np.ones((4, 4)), i*.05, True, [0, 0, 9.81], 'camera')
        assert meta['frames'] == i
    assert np.all(out == 1.)


@pytest.mark.parametrize('change', ['motion', 'stamp_gap', 'gravity', 'calibration', 'clock_reset'])
def test_history_invalidated_without_forcing_a_stop(change):
    w = DepthWindow()
    for i in range(5):
        w.update(np.ones((4, 4)), 10+i*.05, True, [0, 0, 9.81], 'camera')
    out, meta = w.update(np.full((4, 4), .5),
        11 if change == 'stamp_gap' else 1 if change == 'clock_reset' else 10.25,
        change != 'motion', [.3, 0, 9.81] if change == 'gravity' else [0, 0, 9.81],
        'newcamera' if change == 'calibration' else 'camera')
    assert meta['frames'] == 1 and np.all(out == .5)


def test_observed_floor_height_and_slope_fit_with_noise():
    xyz = floor()
    xyz[:, 2] += .08*xyz[:, 0]-.03*xyz[:, 1]+.01
    xyz[:, 2] += np.random.default_rng(1).normal(0, .002, len(xyz))
    fitted = fit_floor(xyz, .1)
    assert fitted['measured'] and fitted['confidence'] > .8
    np.testing.assert_allclose(fitted['coefficients'], [.08, -.03, -.09], atol=.003)
    scene = scene_from_points(xyz, wheel_radius=.1)
    assert scene['directions'][3]['obstacle'] == 'none'


def test_wall_is_not_fitted_as_floor():
    y, z = np.meshgrid(np.arange(-.4, .4, .01), np.arange(-.1, .4, .01))
    wall = np.column_stack((np.full(y.size, .35), y.ravel(), z.ravel()))
    assert not fit_floor(wall, .1)['measured']
    scene = scene_from_points(np.vstack((floor(), wall)), wheel_radius=.1)
    assert scene['floor']['measured']
    assert scene['directions'][3]['obstacle'] == 'wall'


@pytest.mark.parametrize('height,expected', [(.059, 'none'), (.060, 'step_up'), (.061, 'step_up')])
def test_exact_thirty_percent_diameter_boundary(height, expected):
    xyz = floor()
    xyz[(xyz[:, 0] > .35) & (xyz[:, 0] < .55) & (np.abs(xyz[:, 1]) < .2), 2] += height
    scene = scene_from_points(xyz, wheel_radius=.1)
    assert scene['obstacle_threshold_m'] == .06
    assert scene['directions'][3]['obstacle'] == expected, scene['floor']


def test_obstacle_height_relative_to_measured_surface_not_fixed_camera_height():
    xyz = floor()
    xyz[:, 2] += .015+.07*xyz[:, 0]
    raised = (xyz[:, 0] > .35) & (xyz[:, 0] < .55) & (np.abs(xyz[:, 1]) < .2)
    xyz[raised, 2] += .065
    scene = scene_from_points(xyz, wheel_radius=.1)
    assert scene['floor']['measured']
    ray = scene['directions'][3]
    assert ray['obstacle'] == 'step_up'
    assert ray['measured_height_m'] == pytest.approx(.065, abs=.003)


def test_close_floor_does_not_stimulate_obstacle_neurons():
    scene = scene_from_points(floor(), wheel_radius=.1)
    assert scene['vision']['left'] == scene['vision']['right'] == 0
    packet = dict(vision=scene['vision'], depth={s: dict(proximity=1) for s in ('left', 'right')})
    rates = rates_from_features(packet, 150)
    assert rates['LC4_left'] == rates['LC4_right'] == 0


def test_real_asymmetric_rough_floor_prefers_flat_left_and_preserves_speed():
    xyz = floor()
    rough = (xyz[:, 0] > .35) & (xyz[:, 1] < .15)
    xyz[rough, 2] += .035*(np.sin(xyz[rough, 0]*60)**2)
    scene = scene_from_points(xyz, wheel_radius=.1)
    assert scene['directions'][3]['obstacle'] == 'none'
    assert scene['preferred_heading_rad'] > 0, scene['directions']
    decision = Avoidance().update(scene, 0, '0')
    assert decision['mode'] == 'follow_surface'
    cmd = Avoidance.command(dict(linear_mps=.2, angular_rps=0), decision)
    assert cmd['linear_mps'] == .2 and 0 < cmd['angular_rps'] <= .2


def test_flat_goal_never_overrides_obstacle_goal():
    scene = scene_from_points(floor(), wheel_radius=.1)
    rays = copy.deepcopy(scene['directions'])
    for r in rays:
        r.update(flat_cost=.5, surface_confidence=1., support_until_m=.8)
    rays[-1].update(flat_cost=0., clearance_m=.1, obstacle='step_up')
    assert preferred_surface(rays) == 0
    rays[-1]['clearance_m'] = .8
    assert preferred_surface(rays) == 0  # a flat path ending at a measured obstacle still loses
    rays[3].update(clearance_m=.1, obstacle='wall')
    scene.update(directions=rays, preferred_heading_rad=math.pi/4)
    decision = Avoidance().update(scene, 0, '0')
    assert decision['mode'] == 'turn'
    assert Avoidance.command(dict(linear_mps=.2, angular_rps=0), decision)['linear_mps'] == 0


def test_unknown_not_assigned_a_flat_floor_score():
    scene = scene_from_points(floor(), wheel_radius=.1)
    for ray in scene['directions']:
        ray.update(surface_confidence=0., flat_cost=0.)
    assert preferred_surface(scene['directions']) == 0


def test_nominal_and_calibrated_diameters():
    scene = scene_from_points(floor(.098), wheel_radius=.098)
    assert scene['obstacle_threshold_m'] == pytest.approx(.0588)


def test_bad_vision_does_not_fall_back_to_raw_depth():
    with pytest.raises(ValueError):
        rates_from_features(dict(vision=dict(source='raw'), depth={s: dict(proximity=0) for s in ('left', 'right')}))


def test_preferred_surface_memory_releases_immediately_if_path_is_blocked():
    scene = scene_from_points(floor(), wheel_radius=.1)
    adapter = Avoidance()
    scene['preferred_heading_rad'] = math.pi/6
    assert adapter.update(scene, 0, '0')['surface_heading_rad'] > 0
    scene['preferred_heading_rad'] = -math.pi/6
    assert adapter.update(scene, .1, '1')['surface_heading_rad'] > 0
    scene['directions'][5].update(obstacle='wall', clearance_m=.2)
    assert adapter.update(scene, .2, '2')['surface_heading_rad'] < 0


def test_fresh_stationary_ramp_keeps_small_obstacle_height_relative_to_slope():
    xyz = floor()
    xyz[:, 2] += .12*xyz[:, 0]
    bump = (xyz[:, 0] > .4) & (xyz[:, 0] < .6) & (np.abs(xyz[:, 1]) < .15)
    xyz[bump, 2] += .050
    scene = scene_from_points(xyz, wheel_radius=.1)
    assert scene['floor']['measured']
    assert scene['directions'][3]['obstacle'] == 'none'
    assert scene['directions'][3]['low_step_m'] == pytest.approx(.05, abs=.004)
