import json
import unittest

from cli.vision_overlay import VisionCache, canvas_box, parse_packet


def packet():
    return {
        'schema': 1, 'sequence': 1, 'state': 'DETECTED', 'direction': 'LEFT',
        'model_mode': 'MISSION', 'processing_ms': 80,
        'width': 360, 'height': 640,
        'detections': [{'class_id': 0, 'class_name': 'target_rover',
                        'confidence': 0.9, 'xyxy': [10, 20, 110, 220]}],
    }


class VisionOverlayTests(unittest.TestCase):
    def test_portrait_box_and_age(self):
        data = packet()
        self.assertEqual(parse_packet(json.dumps(data).encode()), data)
        self.assertEqual(canvas_box(data['detections'][0]['xyxy'], 360, 640,
                                    (50, 100, 410, 740)), (60, 120, 160, 320))
        cache = VisionCache()
        cache.update(json.dumps(data).encode(), now=10.0)
        self.assertIsNotNone(cache.snapshot(now=10.4))
        self.assertIsNone(cache.snapshot(now=10.43))

    def test_invalid_packet_rejected(self):
        data = packet()
        data['detections'][0]['xyxy'] = [0, 0, 400, 200]
        with self.assertRaises(ValueError):
            parse_packet(json.dumps(data).encode())
        data = packet()
        data['direction'] = None
        with self.assertRaises(ValueError):
            parse_packet(json.dumps(data).encode())


if __name__ == '__main__':
    unittest.main()
