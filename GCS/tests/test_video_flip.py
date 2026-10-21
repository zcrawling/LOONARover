import json
import threading
import unittest
from collections import deque
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image
from cli.video_compass import Player
from cli.vision_overlay import VisionCache


class VideoFlipTests(unittest.TestCase):
    def test_flip_repaints_paused_frame_and_discards_old_orientation_boxes(self):
        # Exercise draw without opening a window or starting a camera/model.
        player = Player.__new__(Player)
        player.root = Mock()
        player.canvas = Mock()
        player.canvas.winfo_width.return_value = 104
        player.canvas.winfo_height.return_value = 100
        player.video_done = threading.Event()
        frame = Image.new('RGB', (8, 4), 'black')
        frame.putpixel((0, 0), (255, 0, 0))
        frame.putpixel((7, 3), (0, 255, 0))
        player.frames = deque([frame])
        player.samples = deque()
        player.frame = player.photo = player.last_size = player.last_flip = None
        player.status = Mock()
        player.detector = SimpleNamespace(status='ready')
        player.vision = VisionCache()
        player.vision.update(json.dumps(dict(schema=1, sequence=0, state='NOT_DETECTED',
            direction=None, width=8, height=4, flipped=False, processing_ms=0,
            detections=[dict(class_id=1, class_name='obstacle', confidence=.9, xyxy=[0,0,2,2])])).encode())
        with patch('cli.video_compass.ImageTk.PhotoImage', side_effect=lambda image: image):
            for flipped, expected, rectangles in ((False,(255,0,0),2),
                                                  (True,(0,255,0),1),
                                                  (False,(255,0,0),2)):
                player.flipped = flipped
                player.canvas.reset_mock()
                player.draw()
                self.assertEqual(player.photo.getpixel((0,0)), expected)
                self.assertEqual(player.canvas.create_rectangle.call_count, rectangles)
