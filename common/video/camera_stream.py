"""Run the existing GStreamer pipeline with live camera controls, without ROS."""
import signal
import sys
from camera_control import ControlServer


def main():
    import gi
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst
    Gst.init(None)
    pipeline = Gst.parse_launchv(sys.argv[1:])
    bus = pipeline.get_bus()
    controls = ControlServer(pipeline.get_by_name('loonar_camera'))
    stopped = False

    def stop(*_):
        nonlocal stopped
        stopped = True
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, stop)
    try:
        if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            raise RuntimeError('Camera pipeline could not start')
        while not stopped:
            controls.poll()
            event = bus.timed_pop_filtered(100*Gst.MSECOND, Gst.MessageType.ERROR | Gst.MessageType.EOS)
            if event is not None:
                if event.type == Gst.MessageType.ERROR:
                    raise RuntimeError(str(event.parse_error()))
                break
    finally:
        pipeline.send_event(Gst.Event.new_eos())
        bus.timed_pop_filtered(2*Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
        pipeline.set_state(Gst.State.NULL)
        controls.close()


if __name__ == '__main__':
    main()
