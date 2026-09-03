#include <array>
#include <chrono>
#include <cmath>
#include <cstring>
#include <numbers>
#include <stdexcept>
#include <string>

#include <fcntl.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

#include <geometry_msgs/msg/twist.hpp>
#include <limo_msgs/msg/limo_status.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/imu.hpp>

#include "loonar/gateway/protocol.hpp"

namespace {
namespace protocol = loonar::gateway::protocol;
using loonar::gateway::MotionCommand;

std::array<double, 3> quaternion_to_rpy(double x, double y, double z, double w) {
  const double roll = std::atan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y));
  const double sin_pitch = 2.0 * (w * y - z * x);
  const double pitch = std::abs(sin_pitch) >= 1.0 ? std::copysign(std::numbers::pi / 2.0, sin_pitch)
                                                  : std::asin(sin_pitch);
  const double yaw = std::atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z));
  return {roll, pitch, yaw};
}

class LimoBackendNode final : public rclcpp::Node {
 public:
  LimoBackendNode() : Node("loonar_limo_backend") {
    socket_path_ = declare_parameter<std::string>("gateway_socket", "/run/loonar/vehicle-gateway/backend.sock");
    const auto cmd_topic = declare_parameter<std::string>("cmd_vel_topic", "/cmd_vel");
    const auto status_topic = declare_parameter<std::string>("status_topic", "/limo_status");
    const auto odom_topic = declare_parameter<std::string>("odom_topic", "/wheel/odom");
    const auto imu_topic = declare_parameter<std::string>("imu_topic", "/imu");
    const auto rate = declare_parameter<double>("publish_rate_hz", 20.0);
    if (rate <= 0.0) throw std::runtime_error("publish_rate_hz must be positive");
    publisher_ = create_publisher<geometry_msgs::msg::Twist>(cmd_topic, rclcpp::QoS(10));
    status_sub_ = create_subscription<limo_msgs::msg::LimoStatus>(status_topic, rclcpp::QoS(10),
      [this](const limo_msgs::msg::LimoStatus& message) {
        vehicle_status_.battery_voltage = message.battery_voltage;
        vehicle_status_.valid_flags |= loonar::gateway::kBatteryVoltageValid;
      });
    odom_sub_ = create_subscription<nav_msgs::msg::Odometry>(odom_topic, rclcpp::SensorDataQoS(),
      [this](const nav_msgs::msg::Odometry& message) {
        vehicle_status_.odom_x = message.pose.pose.position.x;
        vehicle_status_.odom_y = message.pose.pose.position.y;
        const auto& q = message.pose.pose.orientation;
        vehicle_status_.odom_yaw = quaternion_to_rpy(q.x, q.y, q.z, q.w)[2];
        vehicle_status_.linear_mps = message.twist.twist.linear.x;
        vehicle_status_.angular_radps = message.twist.twist.angular.z;
        vehicle_status_.valid_flags |= loonar::gateway::kOdometryPoseValid |
                                       loonar::gateway::kOdometryMotionValid;
      });
    imu_sub_ = create_subscription<sensor_msgs::msg::Imu>(imu_topic, rclcpp::SensorDataQoS(),
      [this](const sensor_msgs::msg::Imu& message) {
        const auto& q = message.orientation;
        const auto rpy = quaternion_to_rpy(q.x, q.y, q.z, q.w);
        vehicle_status_.imu_roll = rpy[0];
        vehicle_status_.imu_pitch = rpy[1];
        vehicle_status_.imu_yaw = rpy[2];
        vehicle_status_.valid_flags |= loonar::gateway::kImuOrientationValid;
      });
    const auto period = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::duration<double>(1.0 / rate));
    timer_ = create_wall_timer(period, [this] { tick(); });
    status_timer_ = create_wall_timer(std::chrono::seconds(1), [this] { send_vehicle_status(); });
  }

  ~LimoBackendNode() override { close_socket(); }

 private:
  void publish_zero() {
    geometry_msgs::msg::Twist command;
    publisher_->publish(command);
  }
  void publish(const MotionCommand& command) {
    geometry_msgs::msg::Twist twist;
    twist.linear.x = command.linear_mps;
    twist.angular.z = command.angular_radps;
    publisher_->publish(twist);
  }
  void close_socket() { if (socket_fd_ >= 0) close(socket_fd_); socket_fd_ = -1; }
  bool connect_socket() {
    if (socket_fd_ >= 0) return true;
    if (socket_path_.size() >= sizeof(sockaddr_un::sun_path)) return false;
    const int fd = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
    if (fd < 0) return false;
    sockaddr_un address{}; address.sun_family = AF_UNIX;
    std::strncpy(address.sun_path, socket_path_.c_str(), sizeof(address.sun_path) - 1);
    if (connect(fd, reinterpret_cast<const sockaddr*>(&address), sizeof(address)) < 0) { close(fd); return false; }
    const int flags = fcntl(fd, F_GETFL);
    if (flags < 0 || fcntl(fd, F_SETFL, flags | O_NONBLOCK) < 0) { close(fd); return false; }
    socket_fd_ = fd;
    const auto hello = protocol::encode({protocol::Type::kHello, {}});
    if (send(socket_fd_, hello.data(), hello.size(), MSG_NOSIGNAL) != static_cast<ssize_t>(hello.size())) { close_socket(); return false; }
    return true;
  }
  void receive_commands() {
    std::array<std::uint8_t, protocol::kMaxPacketSize> buffer{};
    while (socket_fd_ >= 0) {
      const auto count = recv(socket_fd_, buffer.data(), buffer.size(), MSG_DONTWAIT);
      if (count < 0) { if (errno == EAGAIN || errno == EWOULDBLOCK) return; close_socket(); return; }
      if (count == 0) { close_socket(); return; }
      const auto packet = protocol::decode(std::span<const std::uint8_t>(buffer.data(), static_cast<std::size_t>(count)));
      if (!packet) continue;
      const auto command = protocol::decode_motion(*packet);
      if (!command) continue;
      if (command->source == loonar::gateway::Source::kStop) publish_zero();
      else publish(*command);
    }
  }
  void send_vehicle_status() {
    if (!connect_socket()) return;
    vehicle_status_.timestamp_ms = static_cast<std::uint64_t>(get_clock()->now().nanoseconds() / 1000000LL);
    const auto packet = protocol::encode_vehicle_status(vehicle_status_);
    if (send(socket_fd_, packet.data(), packet.size(), MSG_NOSIGNAL) != static_cast<ssize_t>(packet.size())) {
      close_socket();
    }
  }
  void tick() {
    if (!connect_socket()) return;
    receive_commands();
  }

  std::string socket_path_;
  int socket_fd_{-1};
  rclcpp::Publisher<geometry_msgs::msg::Twist>::SharedPtr publisher_;
  rclcpp::Subscription<limo_msgs::msg::LimoStatus>::SharedPtr status_sub_;
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr odom_sub_;
  rclcpp::Subscription<sensor_msgs::msg::Imu>::SharedPtr imu_sub_;
  rclcpp::TimerBase::SharedPtr timer_;
  rclcpp::TimerBase::SharedPtr status_timer_;
  loonar::gateway::VehicleStatus vehicle_status_{};
};
}  // namespace

int main(int argc, char** argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<LimoBackendNode>());
  rclcpp::shutdown();
  return 0;
}
