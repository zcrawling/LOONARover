"""The GCS maps general detection classes to rover or obstacle display labels."""

import unittest

from cli.target_vision import (Box, Result, check_classes, direction_for_boxes,
                               extract_result, result_is_fresh)


class Value:
    def __init__(self, value):
        self.value = value

    def item(self):
        return self.value


class Coordinates:
    def __init__(self, values):
        self.values = values

    def tolist(self):
        return self.values


class PredictionBox:
    cls = Value(0)
    conf = Value(.9)
    xyxy = [Coordinates([-10, 100, 80, 200])]


class TargetVisionTests(unittest.TestCase):
    def test_general_and_rover_model_classes_are_mapped(self):
        self.assertEqual(check_classes({0: 'person', 1: 'car'}),
                         {0: 'obstacle', 1: 'obstacle'})
        self.assertEqual(check_classes({0: 'rover', 1: 'rock', 2: 'target_rover'}),
                         {0: 'target_rover', 1: 'obstacle', 2: 'target_rover'})
        with self.assertRaises(ValueError):
            check_classes({})

    def test_portrait_direction_uses_360_pixel_width(self):
        boxes = [Box('obstacle', .99, (0, 0, 100, 100)),
                 Box('target_rover', .80, (15, 40, 65, 180))]
        self.assertEqual(direction_for_boxes(boxes, 360), 'LEFT')
        boxes.append(Box('target_rover', .95, (270, 40, 320, 180)))
        self.assertEqual(direction_for_boxes(boxes, 360), 'RIGHT')
        self.assertEqual(direction_for_boxes([Box('target_rover', .9, (150, 0, 210, 50))], 360),
                         'CENTER')
        self.assertEqual(direction_for_boxes(boxes[:1], 360), 'NOT_DETECTED')

    def test_outdated_boxes_are_hidden(self):
        result = Result(10.0, (360, 640), (), 'NOT_DETECTED', 60)
        self.assertTrue(result_is_fresh(result, now=10.4))
        self.assertFalse(result_is_fresh(result, now=10.51))

    def test_model_boxes_remain_portrait_pixels(self):
        result = extract_result(type('Prediction', (), {'boxes': [PredictionBox()]})(),
                                (360, 640), 10.0, 20.0)
        self.assertEqual(result.boxes[0].xyxy, (0, 100, 80, 200))
        self.assertEqual(result.direction, 'LEFT')

    def test_generic_yolo_box_is_displayed_as_obstacle(self):
        result = extract_result(type('Prediction', (), {'boxes': [PredictionBox()]})(),
                                (360, 640), 10.0, 20.0,
                                check_classes({0: 'person', 1: 'car'}))
        self.assertEqual(result.boxes[0].name, 'obstacle')
        self.assertEqual(result.direction, 'NOT_DETECTED')


if __name__ == '__main__':
    unittest.main()
