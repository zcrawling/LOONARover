"""Selected peers must affect every rule without granting observers control."""
import importlib.util
from pathlib import Path
import unittest

path=Path(__file__).resolve().parents[1]/'network/configure.py'
spec=importlib.util.spec_from_file_location('network_configure',path)
config=importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)

class NetworkConfigTests(unittest.TestCase):
    def test_control_and_observer_are_separate(self):
        policy, env=config.render('192.0.2.80',['192.0.2.81','192.0.2.81'])
        self.assertIn('ip saddr != 192.0.2.80 tcp dport',policy)
        self.assertIn('ip daddr != 192.0.2.80 udp dport { 5600, 5601 }',policy)
        self.assertIn('ip daddr != { 192.0.2.80, 192.0.2.81 } udp dport { 6101, 6102 }',policy)
        self.assertEqual(env['GROUND_STATION_IP'],'192.0.2.80')
        self.assertEqual(env['LOONAR_STATUS_DESTINATIONS'],'192.0.2.80,192.0.2.81')
        self.assertNotIn('10.254.',policy)
        self.assertNotIn('@',policy)
        self.assertNotIn('22',policy)
    def test_bad_peer_cannot_enter_shell_or_firewall(self):
        for value in ['192.0.2.8; reboot','256.1.1.1','', '::1']:
            with self.subTest(value=value),self.assertRaises(ValueError):config.render(value)
    def test_observer_optional(self):
        _,env=config.render('192.0.2.80')
        self.assertEqual(env['LOONAR_STATUS_DESTINATIONS'],'192.0.2.80')

if __name__=='__main__':unittest.main()
