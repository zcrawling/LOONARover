"""Display-only motor feedback conversion for rqt_plot during bag replay.

Headerless numeric topics intentionally use receipt time in rqt_plot, so old
bag timestamps and repeated loops do not put curves outside the visible range.
Original topics and files are unchanged. This node never publishes commands.
"""
import math


CHANNELS = {
    "current_a": (4, ("left_current_a", "right_current_a")),
    "speed_qpps": (2, ("left_speed_qpps", "right_speed_qpps")),
    "command_qpps": (0, ("left_command_qpps", "right_command_qpps")),
    "pwm_raw": (128, ("left_pwm_raw", "right_pwm_raw")),
    "voltage_v": (8, ("main_voltage_v",)),
}


def numeric_values(values):
    try:
        valid = int(values.get("valid_mask", "0"))
    except ValueError:
        valid = 0
    result = {}
    for topic, (bit, fields) in CHANNELS.items():
        row = []
        for field in fields:
            try:
                value = float(values[field]) if not bit or valid & bit else math.nan
                row.append(value if math.isfinite(value) else math.nan)
            except (KeyError, ValueError, TypeError):
                row.append(math.nan)
        result[topic] = row
    return result


def main():
    import rclpy
    from rclpy.node import Node
    from rclpy.executors import ExternalShutdownException
    from rclpy.qos import qos_profile_sensor_data
    from diagnostic_msgs.msg import DiagnosticArray
    from std_msgs.msg import Float64MultiArray
    rclpy.init()
    node = Node("loonar_rqt_motor_values")
    node.declare_parameter("display_prefix", "/loonar_replay")
    prefix = node.get_parameter("display_prefix").value.rstrip("/")
    publishers = {name: node.create_publisher(Float64MultiArray, prefix + "/" + name, 10)
                  for name in CHANNELS}

    def receive(msg):
        for status in msg.status:
            if status.name == "roboclaw":
                values = numeric_values({v.key: v.value for v in status.values})
                for name, row in values.items():
                    publishers[name].publish(Float64MultiArray(data=row))

    node.create_subscription(DiagnosticArray, "/motor/feedback", receive, qos_profile_sensor_data)
    print(f"rqt display topics: {prefix}/*; data[0]=left(M2), data[1]=right(M1)", flush=True)
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
