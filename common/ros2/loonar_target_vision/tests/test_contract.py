import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from loonar_target_vision.contract import (class_mapping, cue_from_detections,
                                           direction_for_box, make_detection)


class ContractTests(unittest.TestCase):
    def test_portrait_thirds_and_obstacle_only(self):
        self.assertEqual(direction_for_box([0, 0, 100, 200], 360), "LEFT")
        self.assertEqual(direction_for_box([130, 0, 230, 200], 360), "CENTER")
        self.assertEqual(direction_for_box([260, 0, 350, 200], 360), "RIGHT")
        obstacle = make_detection(1, 0.8, [10, 20, 50, 70], 360, 640)
        self.assertEqual(cue_from_detections([obstacle], 360), ("NOT_DETECTED", None))
        target = make_detection(0, 0.7, [260, 20, 350, 70], 360, 640)
        self.assertEqual(cue_from_detections([obstacle, target], 360),
                         ("DETECTED", "RIGHT"))

    def test_coco_demo_and_mission_mapping(self):
        mapping, mode = class_mapping({0: "person", 1: "bicycle"})
        self.assertEqual((mapping, mode), ({0: 1, 1: 1}, "DEMO"))
        self.assertEqual(make_detection(0, 0.8, [1, 2, 4, 5], 360, 640, mapping)["class_name"],
                         "obstacle")
        self.assertEqual(class_mapping({0: "target_rover", 1: "obstacle"}),
                         ({0: 0, 1: 1}, "MISSION"))

    def test_invalid_box_is_rejected(self):
        with self.assertRaises(ValueError):
            make_detection(0, 0.9, [40, 20, 40, 50], 360, 640)


if __name__ == "__main__":
    unittest.main()
