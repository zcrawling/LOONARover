#!/usr/bin/env python3
"""Rev B analytical estimates; no transient simulation or guaranteed accuracy claim."""
import itertools,json,math
from pathlib import Path
rt,rb,rp=94000.,18000.,47000.
k=1+rt/rb+rt/rp
rows=[]
for vb in [0.,9.,11.1,12.6]:
 for ron in [0.,4.5]:
  g0=1/rt+1/rb;g=1/rp+1/6e6+1/15e6
  va=(vb/rt+.7/6e6*(1+ron*g0))/(g0*(1+ron*g)+g)
  rows.append(dict(battery_v=vb,ron_ohm=ron,adc_v=va,nominal_factor_battery_error_mv=(va*k-vb)*1000))
errors=[]
for e in itertools.product([-.001,.001],repeat=4):
 t=47000*(1+e[0])+47000*(1+e[1]);b=18000*(1+e[2]);p=47000*(1+e[3])
 errors.append((k/(1+t/b+t/p)-1)*100)
rth=1/(1/rt+1/rb+1/rp)
data=dict(nominal_factor=k,adc_at_12v6_ideal=12.6/k,battery_lsb_mv=4.096/32768*k*1000,
 resistor_only_gain_error_percent=[min(errors),max(errors)],typical_loading_model=rows,
 off_input_v_from_2ua_and_47k_1pct=2e-6*47000*1.001,
 rc=dict(on_tau_ms=rth*1e-3,on_settle_0p1pct_ms=-math.log(.001)*rth*1e-3,
 off_discharge_from_2v025_to_0v3_us=math.log(2.025/.3)*47047*1.1e-9*1e6),
 hold_up_assumptions=dict(current_a=.010,cap_nominal_f=100e-6,cap_min_f=80e-6,
 voltage_drop_in_200us_v=.010*200e-6/80e-6,
 startup_rc_ms=22*100e-6*1000,initial_22r_power_w=3.3**2/22,
 resistor_charge_energy_j=.5*100e-6*3.3**2,
 warning='Capacitance tolerance at reference conditions only. LM66100 reverse turn-off delay is typical, not maximum; rail-collapse test required.'),
 acceptance='User accepts previous ~33mV typical ADC loading error; this does not waive ADC gain/offset, temperature, resistor and calibration error.')
p=Path(__file__).resolve().parent/'rev_b_calculations.json';p.write_text(json.dumps(data,indent=2)+'\n');print(json.dumps(data,indent=2))
