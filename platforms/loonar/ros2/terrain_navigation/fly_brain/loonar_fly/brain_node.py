"""PC-side whole-brain ROS worker. Latest packet wins; no inference backlog."""
import argparse
import fcntl
import json
import time
import signal
import uuid

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.signals import SignalHandlerOptions
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from std_msgs.msg import String

from .brain import WholeBrain, ROOT
from .interface import rates_from_features, decode_candidate, WallTimeReadout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--motivation-hz", type=float, default=0,
                        help="optional direct DNp09 stimulation, not autonomous motivation")
    parser.add_argument("--step-ms", type=float, default=10)
    args = parser.parse_args()
    if not 1 <= args.step_ms <= 50:
        parser.error("--step-ms must be between 1 and 50 simulated milliseconds")
    (ROOT / "cache").mkdir(exist_ok=True)
    lock = (ROOT / "cache/brain.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    print("Loading pinned whole brain; first Cython compilation can take a minute...", flush=True)
    brain = WholeBrain(motivation_hz=args.motivation_hz)
    brain.store_baseline()
    brain.step({}, 1)  # compile before advertising readiness
    brain.reset()
    rclpy.init(args=[], signal_handler_options=SignalHandlerOptions.NO)
    node = Node("loonar_fly_brain")
    qos = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=1,
                     reliability=ReliabilityPolicy.BEST_EFFORT)
    output = node.create_publisher(String, "/loonar/fly/result", 1)
    halt = node.create_publisher(String, "/loonar/fly/halt", 1)
    worker_session = uuid.uuid4().hex
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True
        if rclpy.ok():
            halt.publish(String(data=worker_session))

    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, stop)
    health = node.create_publisher(String, "/loonar/fly/brain_status", 1)
    pending = []
    last_sequence = {}
    next_print = 0
    readout = WallTimeReadout()

    def receive(msg):
        try:
            if len(msg.data) > 10000:
                return
            packet = json.loads(msg.data)
            if packet["schema"] != 1 or type(packet["sequence"]) is not int or not isinstance(packet["session"], str):
                return
            rates = rates_from_features(packet, args.motivation_hz)
            pending[:] = [(packet, rates, time.monotonic())]
        except (ValueError, TypeError, KeyError):
            pass

    node.create_subscription(String, "/loonar/fly/input", receive, qos)
    node.create_timer(1, lambda: health.publish(String(data=json.dumps({
        "ready": True, "neurons": brain.neuron_count, "connections": brain.connection_count,
        "mode": "inference", "motivation_hz": args.motivation_hz,
        "simulated_step_ms": args.step_ms, "actuation_enabled": False}))))
    node.get_logger().info(f"READY: {brain.neuron_count} neurons, {brain.connection_count} connections; actuation controlled by Pi")
    def next_input():
        nonlocal last_sequence
        # Drain ready callbacks, including the status timer, without waiting.
        for _ in range(4):
            if rclpy.ok():
                rclpy.spin_once(node, timeout_sec=0)
        if not pending:
            return None
        packet, rates, received = pending.pop()
        session, sequence = packet["session"], packet["sequence"]
        if sequence <= last_sequence.get(session, 0) or time.monotonic() - received > .3:
            return None
        last_sequence = {session: sequence}
        return (packet, rates)

    def on_result(packet, result):
        nonlocal next_print
        control_hz = readout.update(result["population_hz"], time.monotonic())
        result.update(schema=1, session=packet["session"], sequence=packet["sequence"],
                      input_rates_hz=rates_from_features(packet, args.motivation_hz), motivation_hz=args.motivation_hz,
                      control_hz=control_hz,
                      candidate=decode_candidate(control_hz), actuation_enabled=False,
                      worker_session=worker_session)
        if not rclpy.ok() or stopping:
            return
        output.publish(String(data=json.dumps(result, allow_nan=False)))
        if time.monotonic() >= next_print:
            hz = result["smoothed_hz"]
            node.get_logger().info(
                f"BRAIN time={result['brain_time_ms']:.0f}ms "
                f"compute={result['compute_ms']:.0f}ms "
                f"DNa02 L/R={hz['DNa02_left']:.1f}/{hz['DNa02_right']:.1f}Hz "
                f"DNp09 L/R={hz['DNp09_left']:.1f}/{hz['DNp09_right']:.1f}Hz "
                f"camera={packet.get('camera_available', False)} actuation=Pi")
            next_print = time.monotonic() + 2

    try:
        brain.stream(next_input, on_result, lambda: stopping or not rclpy.ok(), args.step_ms)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if rclpy.ok():
            halt.publish(String(data=worker_session))
            # Allow the reliable halt to leave DDS before destroying its context.
            rclpy.spin_once(node, timeout_sec=.05)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        lock.close()


if __name__ == "__main__":
    main()
