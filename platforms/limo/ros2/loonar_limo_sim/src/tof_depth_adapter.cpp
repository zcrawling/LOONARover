#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include <string>

#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/camera_info.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <sensor_msgs/msg/point_cloud2.hpp>

namespace {
class TofDepthAdapter final : public rclcpp::Node {
 public:
  TofDepthAdapter() : Node("loonar_sim_tof_adapter") {
    // gazebo_ros_camera with camera_name=tof publishes these Humble topics.
    const auto input_depth = declare_parameter<std::string>("input_depth_topic", "/tof/sim/tof/depth/image_raw");
    const auto input_info = declare_parameter<std::string>("input_camera_info_topic", "/tof/sim/tof/depth/camera_info");
    const auto input_points = declare_parameter<std::string>("input_points_topic", "/tof/sim/tof/points");
    const auto output_depth = declare_parameter<std::string>("output_depth_topic", "/tof/depth/image_raw");
    const auto output_info = declare_parameter<std::string>("output_camera_info_topic", "/tof/depth/camera_info");
    const auto output_points = declare_parameter<std::string>("output_points_topic", "/tof/depth/points");

    const auto qos = rclcpp::SensorDataQoS();
    depth_pub_ = create_publisher<sensor_msgs::msg::Image>(output_depth, qos);
    info_pub_ = create_publisher<sensor_msgs::msg::CameraInfo>(output_info, qos);
    points_pub_ = create_publisher<sensor_msgs::msg::PointCloud2>(output_points, qos);
    depth_sub_ = create_subscription<sensor_msgs::msg::Image>(input_depth, qos,
      [this](sensor_msgs::msg::Image::ConstSharedPtr message) { publish_depth(*message); });
    info_sub_ = create_subscription<sensor_msgs::msg::CameraInfo>(input_info, qos,
      [this](sensor_msgs::msg::CameraInfo::ConstSharedPtr message) { info_pub_->publish(*message); });
    points_sub_ = create_subscription<sensor_msgs::msg::PointCloud2>(input_points, qos,
      [this](sensor_msgs::msg::PointCloud2::ConstSharedPtr message) { points_pub_->publish(*message); });
  }

 private:
  void publish_depth(const sensor_msgs::msg::Image& input) {
    if (input.encoding == "16UC1") {
      depth_pub_->publish(input);
      return;
    }
    if (input.encoding != "32FC1" || input.step < input.width * static_cast<std::uint32_t>(sizeof(float)) ||
        input.data.size() < static_cast<std::size_t>(input.step) * input.height) {
      RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 5000,
                           "Expected Gazebo 32FC1 or 16UC1 depth image, received '%s'", input.encoding.c_str());
      return;
    }

    sensor_msgs::msg::Image output;
    output.header = input.header;
    output.height = input.height;
    output.width = input.width;
    output.encoding = "16UC1";
    output.is_bigendian = false;
    output.step = input.width * sizeof(std::uint16_t);
    output.data.resize(static_cast<std::size_t>(output.step) * output.height);

    for (std::uint32_t row = 0; row < input.height; ++row) {
      const auto* source = input.data.data() + static_cast<std::size_t>(row) * input.step;
      auto* destination = output.data.data() + static_cast<std::size_t>(row) * output.step;
      for (std::uint32_t column = 0; column < input.width; ++column) {
        float metres{};
        std::memcpy(&metres, source + static_cast<std::size_t>(column) * sizeof(float), sizeof(float));
        const auto millimetres = (std::isfinite(metres) && metres > 0.0F)
          ? static_cast<std::uint16_t>(std::min(65535.0F, std::round(metres * 1000.0F)))
          : 0U;
        std::memcpy(destination + static_cast<std::size_t>(column) * sizeof(std::uint16_t),
                    &millimetres, sizeof(millimetres));
      }
    }
    depth_pub_->publish(output);
  }

  rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr depth_pub_;
  rclcpp::Publisher<sensor_msgs::msg::CameraInfo>::SharedPtr info_pub_;
  rclcpp::Publisher<sensor_msgs::msg::PointCloud2>::SharedPtr points_pub_;
  rclcpp::Subscription<sensor_msgs::msg::Image>::SharedPtr depth_sub_;
  rclcpp::Subscription<sensor_msgs::msg::CameraInfo>::SharedPtr info_sub_;
  rclcpp::Subscription<sensor_msgs::msg::PointCloud2>::SharedPtr points_sub_;
};
}  // namespace

int main(int argc, char** argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<TofDepthAdapter>());
  rclcpp::shutdown();
  return 0;
}
