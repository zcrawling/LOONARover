"""Fast local terrain features, reusing calibrated terrain-navigation TF/IMU IO."""
from collections import deque
import json
import numpy as np
from sensor_msgs.msg import Image, CameraInfo
from std_msgs.msg import String
from loonar_terrain_core.ros import Runtime, Sensors, SENSOR, seconds, image_array, level_rotation, spin

from .avoidance import scene_from_points


class Terrain(Runtime):
    def __init__(self):
        super().__init__("loonar_fly_terrain", (
            "sensor_timeout", "sync_tolerance", "base_frame", "wheel_radius", "robot_length",
            "robot_width", "wheel_track", "max_step_up", "max_step_down", "amplitude_threshold", "min_range",
            "max_range", "pixel_stride", "gravity_magnitude_min", "gravity_magnitude_max"),
            dict(self_front=.15, self_rear=.15, self_half_width=.15,
                 self_z_min=-.078, self_z_max=.402))
        self.s = Sensors(self)
        self.info = self.depth = None
        self.amps = deque(maxlen=5)
        self.checked = None
        self.pub = self.create_publisher(String, "/loonar/fly/terrain", SENSOR)
        self.create_subscription(CameraInfo, "/loonar/tof/camera_info", self.on_info, SENSOR)
        self.create_subscription(Image, "/loonar/tof/depth", self.on_depth, SENSOR)
        self.create_subscription(Image, "/loonar/tof/amplitude", self.on_amp, SENSOR)
        self.create_timer(.05, self.process)

    def on_info(self, msg):
        self.info = msg

    def on_depth(self, msg):
        self.depth = msg

    def on_amp(self, msg):
        self.amps.append(msg)

    def process(self):
        d = self.depth
        if d is None or self.info is None:
            return
        stamp = seconds(d.header.stamp)
        if stamp == self.checked or not 0 <= self.now_s()-stamp <= self.p["sensor_timeout"]:
            return
        amp = next((a for a in self.amps if a.header.stamp == d.header.stamp), None)
        gravity = self.s.gravity_at(stamp, self.p["sync_tolerance"])
        if amp is None or gravity is None:
            return
        try:
            if not self.p["gravity_magnitude_min"] <= np.linalg.norm(gravity) <= self.p["gravity_magnitude_max"]:
                raise ValueError("invalid gravity")
            info = self.info
            if (d.width, d.height, d.header.frame_id) != (info.width, info.height, info.header.frame_id):
                raise ValueError("camera calibration does not match depth")
            if (amp.width, amp.height, amp.header.frame_id) != (d.width, d.height, d.header.frame_id):
                raise ValueError("amplitude does not match depth")
            if d.encoding != "32FC1" or amp.encoding != "32FC1":
                raise ValueError("expected normalized depth/amplitude")
            fx, fy, cx, cy = info.k[0], info.k[4], info.k[2], info.k[5]
            if not np.isfinite([fx, fy, cx, cy]).all() or min(fx, fy) <= 0:
                raise ValueError("invalid camera intrinsics")
            stride = max(4, self.p["pixel_stride"])
            z, a = image_array(d)[::stride, ::stride], image_array(amp)[::stride, ::stride]
            valid = np.isfinite(z) & np.isfinite(a) & (z >= self.p["min_range"]) & (z <= self.p["max_range"]) & (a >= self.p["amplitude_threshold"])
            yy, xx = np.mgrid[:d.height:stride, :d.width:stride]
            xyz = np.stack(((xx-cx)*z/fx, (yy-cy)*z/fy, z), axis=-1)[valid]
            r, t = self.transform(d.header.frame_id, d.header.stamp)
            xyz = xyz @ r.T + t
            own = ((xyz[:, 0] >= -self.p["self_rear"]) & (xyz[:, 0] <= self.p["self_front"]) &
                   (np.abs(xyz[:, 1]) <= self.p["self_half_width"]) &
                   (xyz[:, 2] >= self.p["self_z_min"]) & (xyz[:, 2] <= self.p["self_z_max"]))
            level, roll, pitch = level_rotation(gravity)
            scene = scene_from_points(xyz[~own] @ level.T, **{k: self.p[k] for k in (
                "wheel_radius", "robot_length", "robot_width", "wheel_track", "max_step_up", "max_step_down")})
            scene.update(roll=roll, pitch=pitch, valid_ratio=float(valid.mean()))
        except Exception as error:
            scene = dict(ready=False, reason=str(error))
        scene.update(stamp=stamp, frame_id=f"{d.header.stamp.sec}:{d.header.stamp.nanosec}")
        self.checked = stamp
        self.pub.publish(String(data=json.dumps(scene, allow_nan=False)))


if __name__ == "__main__":
    spin(Terrain)
