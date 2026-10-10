"""Own the existing video pipeline and publish its JPEG branch to ROS.

The Gst running-time PTS is mapped onto Pi CLOCK_REALTIME, compensating for
pipeline age at dequeue. This is not a calibrated optical exposure timestamp.
No second camera, decoder or inference model is opened.
"""
import json
import os
import signal
import sys
import time


def frame_stamp(wall_ns, clock_ns, base_ns, running_ns):
    age = clock_ns - base_ns - running_ns
    if running_ns < 0 or not 0 <= age <= 10_000_000_000:
        return wall_ns, None
    return wall_ns - age, age


def main():
    import gi
    gi.require_version("Gst", "1.0")
    gi.require_version("GstApp", "1.0")
    from gi.repository import Gst, GstApp
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import CompressedImage
    from std_msgs.msg import String

    rclpy.init(args=[])
    node = Node("loonar_camera_bag")
    images = node.create_publisher(CompressedImage, "/camera/image_raw/compressed", qos_profile_sensor_data)
    timings = node.create_publisher(String, "/camera/timing", 10)
    # Initialize DDS before GStreamer plugin initialization (Jazzy/Fast DDS).
    Gst.init(None)
    pipeline = Gst.parse_launchv(sys.argv[1:])
    sink = pipeline.get_by_name("bag_camera")
    if not isinstance(sink, GstApp.AppSink):
        raise RuntimeError("video pipeline must contain appsink name=bag_camera")
    bus = pipeline.get_bus()
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, stop)
    frames = 0
    try:
        if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            raise RuntimeError("camera pipeline could not start")
        while not stopping and rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0)
            event = bus.timed_pop_filtered(0, Gst.MessageType.ERROR | Gst.MessageType.EOS)
            if event is not None:
                if event.type == Gst.MessageType.ERROR:
                    raise RuntimeError(str(event.parse_error()))
                break
            sample = sink.try_pull_sample(100 * Gst.MSECOND)
            if sample is None:
                continue
            buffer = sample.get_buffer()
            pts = int(buffer.pts)
            running = sample.get_segment().to_running_time(Gst.Format.TIME, pts)
            clock = pipeline.get_clock()
            wall = time.time_ns()
            stamp, age = frame_stamp(wall, clock.get_time(), pipeline.get_base_time(),
                                     -1 if running == Gst.CLOCK_TIME_NONE else int(running))
            msg = CompressedImage()
            msg.header.stamp.sec, msg.header.stamp.nanosec = divmod(stamp, 1_000_000_000)
            msg.header.frame_id = "camera_optical_frame"
            msg.format = "jpeg"
            msg.data = buffer.extract_dup(0, buffer.get_size())
            images.publish(msg)
            frames += 1
            timing = {
                "stamp_ns": stamp, "host_receive_ns": wall, "gst_pts_ns": pts,
                "pipeline_age_ns": age, "published_frames": frames,
                "timestamp_source": "GST_PTS_MAPPED_TO_PI_REALTIME" if age is not None else "PI_RECEIVE_FALLBACK",
                "optical_exposure_calibrated": False,
            }
            if os.environ.get("LOONAR_CAPTURE_SESSION"):
                from loonar_recording.journal import emit
                emit('camera', 'jpeg', bytes(msg.data), timing=timing,
                     frame_id=msg.header.frame_id)
            timings.publish(String(data=json.dumps(timing)))
    finally:
        # Preserve the existing TS file's clean shutdown when --record-video is used.
        pipeline.send_event(Gst.Event.new_eos())
        bus.timed_pop_filtered(2 * Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
        pipeline.set_state(Gst.State.NULL)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
