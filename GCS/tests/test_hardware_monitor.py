import json
from pathlib import Path
import tempfile
import unittest

from cli.pi_hardware_probe import parse_pmic, wireless, read_status
from cli.hardware_monitor import lines


class HardwareTests(unittest.TestCase):
    def test_pmic_adc_units_and_wireless(self):
        rails = parse_pmic(' EXT5V_V volt(24)=5.04108000V\n VDD_CORE_A current(7)=0.75012000A')
        self.assertEqual(rails['EXT5V_V'], dict(value=5.04108, unit='V'))
        self.assertEqual(rails['VDD_CORE_A']['unit'], 'A')
        self.assertEqual(wireless('wlan0: 0000 68. -42. -256 0 0')[0]['signal_dbm'], -42)
        self.assertEqual(parse_pmic('error'), {})

    def test_stale_and_invalid_samples_never_become_live_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            packet = dict(role='control', boot_id='boot', updated_mono=100, online=True,
                health_mono=100, temperature_c=45, motor_mono=100,
                last_tx_ns=123, last_tx_mono=99,
                motor=dict(main_voltage_v=12, main_voltage_valid=True,
                           temperature_c=35, temperature_valid=True))
            def read(now=100.5):
                (path/'control.json').write_text(json.dumps(packet))
                return read_status('control', now, 'boot', [path])
            live = read()
            self.assertEqual(live['battery_v'], 12)
            self.assertEqual(live['driver_temperature_c'], 35)
            self.assertEqual(live['last_tx_age_s'], 1.5)
            self.assertIsNone(read(102)['battery_v'])
            stale = read(105)
            self.assertFalse(stale['online'])
            self.assertIsNone(stale['temperature_c'])
            packet['motor']['main_voltage_valid'] = False
            self.assertIsNone(read()['battery_v'])
            packet['boot_id'] = 'previous-boot'
            self.assertFalse(read()['available'])

    def test_ssh_disconnect_hides_old_temperatures_but_keeps_last_io(self):
        packet = dict(cpu_temperature_c=48, input_voltage_v=5.1,
                      control=dict(available=True, online=True, temperature_c=55,
                                   last_tx_ns=1_000_000_000, last_tx_age_s=1))
        view = '\n'.join(lines('pi', packet, 10, '연결 끊김'))
        self.assertNotIn('48.00', view)
        self.assertNotIn('55.00', view)
        self.assertIn('STALE', view)
        self.assertIn('11.0초 전', view)

    def test_ui_temperature_cards_removed(self):
        root = Path(__file__).resolve().parents[1]
        html = (root/'webui/static/index.html').read_text()
        js = (root/'webui/static/app.js').read_text()
        self.assertNotIn('id="pi-temperature"', html)
        self.assertNotIn('id="temperature"', html)
        self.assertNotIn("set('pi-temperature'", js)
        self.assertNotIn("set('temperature'", js)
