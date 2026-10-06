import importlib.util
import math
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "rqt_motor_values", Path(__file__).resolve().parents[1] / "rqt_motor_values.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class NumericDisplayTests(unittest.TestCase):
    def test_signed_values_and_units_are_preserved(self):
        result = module.numeric_values(dict(valid_mask="255", left_current_a="-0.73",
                                            right_current_a="1.25", main_voltage_v="11.5"))
        self.assertEqual(result["current_a"], [-.73, 1.25])
        self.assertEqual(result["voltage_v"], [11.5])

    def test_invalid_and_missing_values_are_gaps(self):
        result = module.numeric_values(dict(valid_mask="0", left_current_a="12",
                                            left_command_qpps="100"))
        self.assertTrue(all(math.isnan(v) for v in result["current_a"]))
        self.assertEqual(result["command_qpps"][0], 100.)
        self.assertTrue(math.isnan(result["command_qpps"][1]))

    def test_malformed_values_do_not_kill_display(self):
        result = module.numeric_values(dict(valid_mask="bad", left_command_qpps="bad"))
        self.assertTrue(all(math.isnan(v) for row in result.values() for v in row))
