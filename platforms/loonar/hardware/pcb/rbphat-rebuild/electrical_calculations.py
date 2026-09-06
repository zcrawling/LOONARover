#!/usr/bin/env python3
"""RBPHAT step-2 DC estimates. No simulation or hardware validation is implied.

ADS1115 loading uses the *typical* Fig. 7-5 model: ZCM to 0.7 V,
ZDIFF to AINN=GND. It is not a guaranteed impedance bound.
Run with Python standard library; JSON is written to stdout.
"""
import itertools
import json
import math


def calculate():
    top, bottom, battery = 94000.0, 18000.0, 12.6
    ratio = bottom / (top + bottom)
    rth = top * bottom / (top + bottom)
    corners = []
    for errors in itertools.product((-0.001, 0.001), repeat=3):
        rt = 47000 * (1 + errors[0]) + 47000 * (1 + errors[1])
        rb = bottom * (1 + errors[2])
        corners.append((rb / (rt + rb) / ratio - 1) * 100)
    loading = []
    for vb in (9.0, 11.1, 12.6):
        ideal = vb * ratio
        loaded = (ideal + rth * 0.7 / 6e6) / (1 + rth * (1 / 6e6 + 1 / 15e6))
        loading.append(dict(battery_v=vb, ideal_adc_v=ideal,
                            typical_loaded_adc_v=loaded,
                            inferred_battery_error_mv=(loaded / ratio - vb) * 1000))
    bias = []
    for rb in (680.0, 560.0):
        # Receiver minimum differential input resistance; no remote leakage model.
        term_min = 1 / (1 / (120 * .99) + 1 / 12000)
        vd_min = 3.0 * term_min / (2 * rb * 1.01 + term_min)
        bias.append(dict(resistor_ohm=rb,
                         nominal_idle_v=3.3 * 120 / (2 * rb + 120),
                         min_idle_v_assuming_1pct_3v_12kohm_receiver=vd_min,
                         margin_above_200mv=vd_min - .2,
                         off_rail_current_at_a_3v3_ma=3.3 / rb * 1000))
    return dict(
        divider=dict(ratio=ratio, conversion=1 / ratio, adc_at_12v6=battery * ratio,
                     current_ua=battery / (top + bottom) * 1e6,
                     top_each_mw=(battery / (top + bottom))**2 * 47000 * 1000,
                     bottom_mw=(battery / (top + bottom))**2 * bottom * 1000,
                     thevenin_ohm=rth,
                     ratio_error_percent_min=min(corners), ratio_error_percent_max=max(corners)),
        rc=dict(capacitance_nominal_f=1e-6, tau_ms=rth * 1e-3,
                cutoff_hz=1 / (2 * math.pi * rth * 1e-6),
                settle_to_0p1pct_ms=-math.log(.001) * rth * 1e-3),
        adc=dict(lsb_v_at_4v096=4.096 / 32768,
                 battery_lsb_mv=4.096 / 32768 / ratio * 1000,
                 typical_loading_only=loading,
                 tmux_50na_equivalent_battery_error_mv=50e-9 * rth / ratio * 1000,
                 adc_absmax_violation_example=dict(vdd=1.5, input_v=battery * ratio,
                                                   maximum_allowed_v=1.5 + .3),
                 poweroff_tmux_leakage_max_ua_datasheet_conditions=2),
        bias=bias,
        uart=dict(bit_time_ns_at_2mbps=500,
                  series_47ohm_20pf_10to90_ns=2.2 * 47 * 20e-12 * 1e9,
                  pullup_47kohm_20pf_10to90_ns=2.2 * 47000 * 20e-12 * 1e9),
        load_estimate=dict(two_120ohm_loads_at_3v6_ma=2 * 3.6 / 120 * 1000,
                           note='Ideal line-load estimate, not guaranteed total supply current; excludes faults'),
    )


if __name__ == '__main__':
    print(json.dumps(calculate(), indent=2))
