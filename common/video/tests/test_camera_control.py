import json
import socket
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from camera_control import Exposure, ControlServer


class ExposureTests(unittest.TestCase):
    def test_ev_presets_and_reset(self):
        source=Mock()
        control=Exposure(source)
        self.assertFalse(control.handle({'operation':'status'})['configured'])
        source.set_property.assert_not_called()
        self.assertEqual(control.handle({'operation':'set','value':1.5})['ev'],1.5)
        self.assertEqual(control.handle({'operation':'add','value':-.5})['ev'],1)
        self.assertEqual(control.handle({'operation':'backlight'})['profile'],'backlight')
        source.set_property.assert_any_call('ae-constraint-mode',2)
        self.assertEqual(control.handle({'operation':'auto'})['ev'],0)
        source.set_property.assert_any_call('ae-constraint-mode',0)

    def test_invalid_input_does_not_change_camera(self):
        source=Mock();control=Exposure(source)
        for data in [[],{}, {'operation':'set','value':float('nan')},
                     {'operation':'set','value':float('inf')}, {'operation':'set','value':4},
                     {'operation':'set','value':True}]:
            with self.subTest(data=data),self.assertRaises(ValueError):control.handle(data)
        source.set_property.assert_not_called()

    def test_unsupported_plugin_is_reported_before_changing_properties(self):
        source=Mock();source.find_property.return_value=None
        with self.assertRaises(ValueError):Exposure(source).handle({'operation':'backlight'})
        source.set_property.assert_not_called()

    def test_unix_ack_and_malformed_input_do_not_stop_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'camera.sock'
            server=ControlServer(Mock(),path)
            self.addCleanup(server.close)
            with self.assertRaises(RuntimeError):ControlServer(Mock(),path)
            with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as client:
                client.bind(directory+'/client.sock');client.settimeout(.5)
                for raw,success in [(b'not-json',False), (b'[]',False),
                                    (b'{"operation":"set","value":2}',True),
                                    (b'{"operation":"status"}',True)]:
                    client.sendto(raw,str(path));server.poll()
                    result=json.loads(client.recv(4096));self.assertEqual(result['ok'],success)
                self.assertEqual(result['ev'],2)
                self.assertEqual(path.stat().st_mode & 0o777,0o600)

if __name__=='__main__':unittest.main()
