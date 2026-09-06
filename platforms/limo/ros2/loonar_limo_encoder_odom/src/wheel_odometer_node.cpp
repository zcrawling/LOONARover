#include <cmath>
#include <optional>
#include <string>

#include <geometry_msgs/msg/quaternion.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include <tf2/LinearMath/Quaternion.h>

namespace {
class WheelOdometerNode final : public rclcpp::Node {
 public:
  WheelOdometerNode() : Node("loonar_limo_wheel_odometer") {
    const auto input = declare_parameter<std::string>("input_topic", "/wheel/odometer");
    const auto output = declare_parameter<std::string>("output_topic", "/wheel/odom");
    track_m_ = declare_parameter<double>("track_m", 0.172);
    odom_frame_ = declare_parameter<std::string>("odom_frame", "odom");
    base_frame_ = declare_parameter<std::string>("base_frame", "base_link");

    publisher_ = create_publisher<nav_msgs::msg::Odometry>(output, rclcpp::SensorDataQoS());
    subscription_ = create_subscription<sensor_msgs::msg::JointState>(
      input, rclcpp::SensorDataQoS(),
      [this](sensor_msgs::msg::JointState::ConstSharedPtr message) { on_odometer(*message); });
  }

 private:
  static double normalize(double value) {
    return std::atan2(std::sin(value), std::cos(value));
  }

  void on_odometer(const sensor_msgs::msg::JointState& message) {
    if (message.position.size() != 2U) {
      RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 5000,
                           "Expected left/right odometer positions, received %zu", message.position.size());
      return;
    }
    const auto stamp = rclcpp::Time(message.header.stamp);
    const Sample current{message.position[0], message.position[1], stamp};
    if (!previous_) {
      previous_ = current;
      return;
    }

    const double left_delta_m = current.left_m - previous_->left_m;
    const double right_delta_m = current.right_m - previous_->right_m;
    const double distance_m = (left_delta_m + right_delta_m) * 0.5;
    const double yaw_delta = (right_delta_m - left_delta_m) / track_m_;
    const double midpoint_yaw = yaw_ + yaw_delta * 0.5;
    x_ += distance_m * std::cos(midpoint_yaw);
    y_ += distance_m * std::sin(midpoint_yaw);
    yaw_ = normalize(yaw_ + yaw_delta);

    nav_msgs::msg::Odometry odom;
    odom.header.stamp = message.header.stamp;
    odom.header.frame_id = odom_frame_;
    odom.child_frame_id = base_frame_;
    odom.pose.pose.position.x = x_;
    odom.pose.pose.position.y = y_;
    tf2::Quaternion orientation;
    orientation.setRPY(0.0, 0.0, yaw_);
    odom.pose.pose.orientation.x = orientation.x();
    odom.pose.pose.orientation.y = orientation.y();
    odom.pose.pose.orientation.z = orientation.z();
    odom.pose.pose.orientation.w = orientation.w();

    const double elapsed = (current.stamp - previous_->stamp).seconds();
    if (elapsed > 0.0) {
      odom.twist.twist.linear.x = distance_m / elapsed;
      odom.twist.twist.angular.z = yaw_delta / elapsed;
    }
    odom.pose.covariance[0] = 0.01;
    odom.pose.covariance[7] = 0.01;
    odom.pose.covariance[35] = 0.02;
    // Initial LOONAR/LIMO baseline: sigma(vx) = 0.15 m/s.
    odom.twist.covariance[0] = 0.0225;
    // Flat-LIMO encoder-dominant yaw-rate test: sigma(wz) = 0.05 rad/s.
    // This is deliberately more trusted than the vendor gyro baseline below.
    odom.twist.covariance[35] = 0.0025;
    publisher_->publish(odom);
    previous_ = current;
  }

  struct Sample {
    double left_m;
    double right_m;
    rclcpp::Time stamp;
  };

  double track_m_{};
  double x_{};
  double y_{};
  double yaw_{};
  std::string odom_frame_;
  std::string base_frame_;
  std::optional<Sample> previous_;
  rclcpp::Publisher<nav_msgs::msg::Odometry>::SharedPtr publisher_;
  rclcpp::Subscription<sensor_msgs::msg::JointState>::SharedPtr subscription_;
};
}  // namespace

int main(int argc, char** argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<WheelOdometerNode>());
  rclcpp::shutdown();
  return 0;
}
