#include <cstring>
#include <deque>
#include <geometry_msgs/msg/vector3_stamped.hpp>
#include <grid_map_ros/GridMapRosConverter.hpp>
#include <loonar_msgs/action/build_terrain_map.hpp>
#include <loonar_msgs/msg/stationary.hpp>
#include <loonar_msgs/msg/terrain_map.hpp>
#include <loonar_terrain_core/geometry.hpp>
#include <map>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <sensor_msgs/msg/camera_info.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <sensor_msgs/point_cloud2_iterator.hpp>
#include <tf2_eigen/tf2_eigen.hpp>
#include <tf2_ros/buffer.h>
#include <tf2_ros/transform_broadcaster.h>
#include <tf2_ros/transform_listener.h>

using Image = sensor_msgs::msg::Image;
using Action = loonar_msgs::action::BuildTerrainMap;
using Handle = rclcpp_action::ServerGoalHandle<Action>;
class Perception : public rclcpp::Node {
  tf2_ros::Buffer tf_;
  tf2_ros::TransformListener listener_;
  tf2_ros::TransformBroadcaster broadcaster_;
  rclcpp_action::Server<Action>::SharedPtr server_;
  std::shared_ptr<Handle> goal_;
  rclcpp::Subscription<Image>::SharedPtr depth_sub_, amp_sub_;
  rclcpp::Subscription<sensor_msgs::msg::CameraInfo>::SharedPtr info_sub_;
  rclcpp::Subscription<geometry_msgs::msg::Vector3Stamped>::SharedPtr
      gravity_sub_;
  rclcpp::Subscription<loonar_msgs::msg::Stationary>::SharedPtr stationary_sub_;
  rclcpp::Publisher<loonar_msgs::msg::TerrainMap>::SharedPtr map_pub_;
  rclcpp::Publisher<grid_map_msgs::msg::GridMap>::SharedPtr grid_pub_;
  rclcpp::Publisher<sensor_msgs::msg::PointCloud2>::SharedPtr cloud_pub_;
  std::map<std::string,
           rclcpp::Publisher<sensor_msgs::msg::PointCloud2>::SharedPtr>
      layers_;
  rclcpp::Publisher<Image>::SharedPtr fused_pub_, confidence_pub_;
  rclcpp::TimerBase::SharedPtr timer_;
  OnSetParametersCallbackHandle::SharedPtr parameter_callback_;
  sensor_msgs::msg::CameraInfo::ConstSharedPtr info_;
  geometry_msgs::msg::Vector3Stamped::ConstSharedPtr gravity_;
  std::deque<geometry_msgs::msg::Vector3Stamped::ConstSharedPtr>
      gravity_history_;
  loonar_msgs::msg::Stationary::ConstSharedPtr stationary_;
  std::deque<Image::ConstSharedPtr> depths_, amps_;
  std::vector<std::vector<double>> samples_;
  std::vector<size_t> pixels_;
  std::vector<Eigen::Vector3d> rays_;
  Eigen::Affine3d base_from_camera_ = Eigen::Affine3d::Identity();
  Eigen::Matrix3d level_ = Eigen::Matrix3d::Identity();
  rclcpp::Time started_{0, 0, RCL_ROS_TIME}, last_{0, 0, RCL_ROS_TIME};
  std::array<double, 9> calibration_{};
  bool reserved_ = false;
  int count_ = 0;
  unsigned map_id_ = 0, width_ = 0, height_ = 0;
  double p(const std::string &k) { return get_parameter(k).as_double(); }
  int n(const std::string &k) { return get_parameter(k).as_int(); }
  bool fresh(const builtin_interfaces::msg::Time &stamp, double age) {
    double dt = (now() - rclcpp::Time(stamp)).seconds();
    return dt >= 0 && dt <= age;
  }
  bool stationary() {
    return stationary_ && stationary_->state == 2 &&
           fresh(stationary_->header.stamp, p("sensor_timeout"));
  }
  static float read(const Image &m, size_t pixel) {
    if (m.encoding != "32FC1" || m.step < m.width * 4 ||
        m.data.size() < size_t(m.step) * m.height)
      return loonar::nan();
    uint32_t bits;
    std::memcpy(&bits,
                &m.data[(pixel / m.width) * m.step + (pixel % m.width) * 4], 4);
#if __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
    if (m.is_bigendian)
      bits = __builtin_bswap32(bits);
#else
    if (!m.is_bigendian)
      bits = __builtin_bswap32(bits);
#endif
    float f;
    std::memcpy(&f, &bits, 4);
    return f;
  }
  void finish(bool ok, const std::string &status, float ratio = 0) {
    if (!goal_)
      return;
    auto result = std::make_shared<Action::Result>();
    result->success = ok;
    result->map_id = ok ? map_id_ : 0;
    result->valid_ratio = ratio;
    result->status = status;
    if (goal_->is_canceling())
      goal_->canceled(result);
    else if (ok)
      goal_->succeed(result);
    else
      goal_->abort(result);
    goal_.reset();
    reserved_ = false;
    samples_.clear();
    depths_.clear();
    amps_.clear();
  }
  void tick() {
    if (!goal_)
      return;
    if (goal_->is_canceling())
      return finish(false, "cancelled");
    if (!stationary())
      return finish(false, "stationarity lost or stale");
    double elapsed = (now() - started_).seconds();
    if (elapsed < 0 || elapsed > p("capture_timeout"))
      return finish(false, "capture timeout or ROS time reset");
    if (count_ == goal_->get_goal()->frame_count)
      build();
  }
  void collect() {
    if (!goal_ || count_ >= goal_->get_goal()->frame_count || !stationary())
      return;
    for (auto it = depths_.begin();
         it != depths_.end() && count_ < goal_->get_goal()->frame_count;) {
      const auto d = *it;
      rclcpp::Time stamp(d->header.stamp);
      if (stamp <= started_ || stamp <= last_) {
        it = depths_.erase(it);
        continue;
      }
      auto a = std::find_if(amps_.begin(), amps_.end(), [&](auto &m) {
        return rclcpp::Time(m->header.stamp) == stamp;
      });
      if (a == amps_.end()) {
        ++it;
        continue;
      }
      geometry_msgs::msg::Vector3Stamped::ConstSharedPtr matched_gravity;
      double nearest = p("sync_tolerance");
      for (const auto &sample : gravity_history_) {
        const auto delta =
            std::abs((stamp - rclcpp::Time(sample->header.stamp)).seconds());
        if (fresh(sample->header.stamp, p("sensor_timeout")) &&
            delta <= nearest) {
          nearest = delta;
          matched_gravity = sample;
        }
      }
      if (!fresh(d->header.stamp, p("sensor_timeout")) || !info_ ||
          !matched_gravity) {
        it = depths_.erase(it);
        continue;
      }
      if (d->encoding != "32FC1" || (*a)->encoding != "32FC1" ||
          d->width != (*a)->width || d->height != (*a)->height ||
          d->header.frame_id != (*a)->header.frame_id ||
          d->width != info_->width || d->height != info_->height ||
          d->header.frame_id != info_->header.frame_id || info_->k[0] <= 0 ||
          info_->k[4] <= 0 ||
          !std::all_of(info_->k.begin(), info_->k.end(),
                       [](double v) { return std::isfinite(v); }) ||
          !std::all_of(info_->d.begin(), info_->d.end(),
                       [](double v) {
                         return std::isfinite(v) && std::abs(v) < 1e-12;
                       }) ||
          !d->width || !d->height || d->width > 1920 || d->height > 1080)
        return finish(false, "image/calibration mismatch");
      try {
        auto cam = tf2::transformToEigen(
            tf_.lookupTransform("base_link", d->header.frame_id, stamp));
        auto imu = tf2::transformToEigen(
            tf_.lookupTransform("base_link", matched_gravity->header.frame_id,
                                rclcpp::Time(matched_gravity->header.stamp)));
        Eigen::Vector3d g =
            imu.linear() * Eigen::Vector3d(matched_gravity->vector.x,
                                           matched_gravity->vector.y,
                                           matched_gravity->vector.z);
        if (!g.allFinite() || g.norm() < p("gravity_magnitude_min") ||
            g.norm() > p("gravity_magnitude_max"))
          return finish(false, "invalid gravity");
        const double roll = std::atan2(g.y(), g.z()),
                     pitch = std::atan2(-g.x(), std::hypot(g.y(), g.z()));
        Eigen::Matrix3d level =
            (Eigen::AngleAxisd(pitch, Eigen::Vector3d::UnitY()) *
             Eigen::AngleAxisd(roll, Eigen::Vector3d::UnitX()))
                .toRotationMatrix();
        if (count_ == 0) {
          base_from_camera_ = cam;
          level_ = level;
          calibration_ = info_->k;
          width_ = d->width;
          height_ = d->height;
          pixels_.clear();
          rays_.clear();
          for (unsigned v = n("roi_top"); v < height_; v += n("pixel_stride"))
            for (unsigned u = 0; u < width_; u += n("pixel_stride")) {
              pixels_.push_back(v * width_ + u);
              rays_.emplace_back((u - info_->k[2]) / info_->k[0],
                                 (v - info_->k[5]) / info_->k[4], 1.);
            }
          samples_.resize(pixels_.size());
        } else if (info_->k != calibration_ || d->width != width_ ||
                   d->height != height_ ||
                   (level - level_).norm() > p("max_capture_tilt_change"))
          return finish(false, "capture geometry changed");
      } catch (const tf2::TransformException &) {
        it = depths_.erase(it);
        continue;
      }
      for (size_t i = 0; i < pixels_.size(); ++i) {
        double z = read(*d, pixels_[i]), a_value = read(**a, pixels_[i]);
        if (std::isfinite(z) && std::isfinite(a_value) && z >= p("min_range") &&
            z <= p("max_range") && a_value >= p("amplitude_threshold"))
          samples_[i].push_back(z);
      }
      ++count_;
      last_ = stamp;
      amps_.erase(a);
      it = depths_.erase(it);
      auto fb = std::make_shared<Action::Feedback>();
      fb->frames_collected = count_;
      fb->state = "CAPTURE";
      goal_->publish_feedback(fb);
    }
  }
  static Image float_image(unsigned w, unsigned h,
                           const std_msgs::msg::Header &header,
                           const std::vector<float> &values) {
    Image m;
    m.header = header;
    m.width = w;
    m.height = h;
    m.encoding = "32FC1";
    m.step = w * 4;
    m.is_bigendian = false;
    m.data.resize(values.size() * 4);
    std::memcpy(m.data.data(), values.data(), m.data.size());
    return m;
  }
  void build() {
    auto fb = std::make_shared<Action::Feedback>();
    fb->frames_collected = count_;
    fb->state = "BUILD_MAP";
    goal_->publish_feedback(fb);
    std::vector<Eigen::Vector3d> points;
    std::vector<float> confidence;
    std::vector<float> fused(width_ * height_, loonar::nan()),
        conf(width_ * height_, 0);
    for (size_t i = 0; i < samples_.size(); ++i) {
      auto f = loonar::fuse(samples_[i], n("min_valid_samples"), count_,
                            p("temporal_mad_limit"));
      fused[pixels_[i]] = f.depth;
      conf[pixels_[i]] = f.confidence;
    }
    auto filtered = fused;
    if (get_parameter("spatial_median").as_bool()) {
      for (size_t pixel : pixels_) {
        // Never fill missing pixels or raise their confidence.
        if (!std::isfinite(fused[pixel]))
          continue;
        std::vector<double> neighbors;
        int u = pixel % width_, v = pixel / width_, stride = n("pixel_stride");
        for (int dy = -stride; dy <= stride; dy += stride)
          for (int dx = -stride; dx <= stride; dx += stride)
            if (u + dx >= 0 && u + dx < int(width_) && v + dy >= 0 &&
                v + dy < int(height_)) {
              float z = fused[(v + dy) * width_ + u + dx];
              if (std::isfinite(z))
                neighbors.push_back(z);
            }
        filtered[pixel] = loonar::median(neighbors);
      }
    }
    for (size_t i = 0; i < pixels_.size(); ++i) {
      auto k = pixels_[i];
      if (!std::isfinite(filtered[k]) || conf[k] < p("min_confidence"))
        continue;
      Eigen::Vector3d b = base_from_camera_ * (rays_[i] * filtered[k]);
      if (b.x() >= -p("self_rear") && b.x() <= p("self_front") &&
          std::abs(b.y()) <= p("self_half_width") && b.z() >= p("self_z_min") &&
          b.z() <= p("self_z_max"))
        continue;
      points.push_back(level_ * b);
      confidence.push_back(conf[k]);
    }
    float ratio = pixels_.empty() ? 0.f : float(points.size()) / pixels_.size();
    if (ratio < p("min_valid_ratio"))
      return finish(false, "insufficient valid depth", ratio);
    loonar::Grid g;
    g.resolution = p("resolution");
    g.x_min = p("x_min");
    g.x_max = p("x_max");
    g.y_min = p("y_min");
    g.y_max = p("y_max");
    loonar::TerrainParams settings;
    settings.min_points = n("min_points_per_cell");
    settings.min_neighbors = n("min_plane_neighbors");
    settings.step_support = n("step_support");
    settings.plane_radius = p("plane_fit_radius");
    settings.step_noise = p("step_noise");
    settings.min_confidence = p("min_confidence");
    settings.max_slope = p("max_slope");
    settings.max_roughness = p("max_roughness");
    settings.max_step_up = p("max_step_up");
    settings.max_step_down = p("max_step_down");
    settings.max_drop_depth = p("max_drop_depth");
    loonar::build_grid(g, points, confidence, settings);
    if (!stationary())
      return finish(false, "stationary confirmation expired during map build");
    loonar_msgs::msg::TerrainMap out;
    out.header.stamp = last_;
    out.header.frame_id = "terrain_local";
    out.map_id = ++map_id_;
    out.resolution = g.resolution;
    out.x_min = g.x_min;
    out.y_min = g.y_min;
    out.size_x = g.nx;
    out.size_y = g.ny;
    geometry_msgs::msg::TransformStamped transform;
    transform.header.stamp = last_;
    transform.header.frame_id = "base_link";
    transform.child_frame_id = "terrain_local";
    Eigen::Quaterniond q(level_.transpose());
    transform.transform.rotation.x = q.x();
    transform.transform.rotation.y = q.y();
    transform.transform.rotation.z = q.z();
    transform.transform.rotation.w = q.w();
    broadcaster_.sendTransform(transform);
    grid_map::GridMap gm;
    gm.setFrameId(out.header.frame_id);
    gm.setTimestamp(last_.nanoseconds());
    gm.setGeometry(grid_map::Length(g.nx * g.resolution, g.ny * g.resolution),
                   g.resolution,
                   grid_map::Position(g.x_min + g.nx * g.resolution / 2,
                                      g.y_min + g.ny * g.resolution / 2));
    const std::vector<std::string> names = {
        "elevation",        "elevation_min",
        "elevation_max",    "elevation_variance",
        "elevation_mad",    "point_count",
        "confidence",       "slope",
        "gradient_x",       "gradient_y",
        "cross_slope",      "roughness",
        "step_up",          "step_down",
        "depression_depth", "drop_suspect",
        "observed",         "unknown",
        "traversability"};
    for (const auto &name : names)
      gm.add(name);
    for (size_t k = 0; k < g.cells.size(); ++k) {
      const auto &c = g.cells[k];
      loonar_msgs::msg::TerrainCell m;
#define COPY(field) m.field = c.field
      COPY(elevation);
      COPY(elevation_min);
      COPY(elevation_max);
      COPY(elevation_variance);
      COPY(elevation_mad);
      COPY(point_count);
      COPY(confidence);
      COPY(slope);
      COPY(gradient_x);
      COPY(gradient_y);
      COPY(cross_slope);
      COPY(roughness);
      COPY(step_up);
      COPY(step_down);
      COPY(depression_depth);
      COPY(drop_suspect);
      COPY(observed);
      COPY(unknown);
      COPY(traversability);
#undef COPY
      out.cells.push_back(m);
      auto xy = g.position(k);
      grid_map::Index index;
      gm.getIndex(xy, index);
      std::vector<float> values = {c.elevation,        c.elevation_min,
                                   c.elevation_max,    c.elevation_variance,
                                   c.elevation_mad,    float(c.point_count),
                                   c.confidence,       c.slope,
                                   c.gradient_x,       c.gradient_y,
                                   c.cross_slope,      c.roughness,
                                   c.step_up,          c.step_down,
                                   c.depression_depth, float(c.drop_suspect),
                                   float(c.observed),  float(c.unknown),
                                   c.traversability};
      for (size_t i = 0; i < names.size(); ++i)
        gm.at(names[i], index) = values[i];
    }
    map_pub_->publish(out);
    grid_pub_->publish(*grid_map::GridMapRosConverter::toMessage(gm));
    for (auto &[topic, publisher] : layers_) {
      auto layer = topic == "step"         ? "step_up"
                   : topic == "depression" ? "depression_depth"
                                           : topic;
      sensor_msgs::msg::PointCloud2 cloud;
      grid_map::GridMapRosConverter::toPointCloud(
          gm,
          layer == "elevation" ? std::vector<std::string>{"elevation"}
                               : std::vector<std::string>{"elevation", layer},
          "elevation", cloud);
      publisher->publish(cloud);
    }
    sensor_msgs::msg::PointCloud2 cloud;
    cloud.header = out.header;
    sensor_msgs::PointCloud2Modifier modifier(cloud);
    modifier.setPointCloud2FieldsByString(1, "xyz");
    modifier.resize(points.size());
    sensor_msgs::PointCloud2Iterator<float> px(cloud, "x"), py(cloud, "y"),
        pz(cloud, "z");
    for (const auto &point : points) {
      *px = point.x();
      *py = point.y();
      *pz = point.z();
      ++px;
      ++py;
      ++pz;
    }
    cloud_pub_->publish(cloud);
    auto image_header = info_->header;
    image_header.stamp = last_;
    fused_pub_->publish(float_image(width_, height_, image_header, fused));
    confidence_pub_->publish(float_image(width_, height_, image_header, conf));
    finish(true, "OK", ratio);
  }

public:
  Perception()
      : Node("loonar_terrain_perception"), tf_(get_clock()), listener_(tf_),
        broadcaster_(*this) {
    for (auto [k, v] :
         std::map<std::string, double>{{"sensor_timeout", .3},
                                       {"sync_tolerance", .06},
                                       {"capture_timeout", 3.},
                                       {"min_range", .15},
                                       {"max_range", 2.5},
                                       {"amplitude_threshold", 30.},
                                       {"temporal_mad_limit", .025},
                                       {"min_confidence", .6},
                                       {"min_valid_ratio", .1},
                                       {"max_capture_tilt_change", .025},
                                       {"gravity_magnitude_min", 8.},
                                       {"gravity_magnitude_max", 12.},
                                       {"resolution", .05},
                                       {"x_min", -.5},
                                       {"x_max", 2.},
                                       {"y_min", -1.},
                                       {"y_max", 1.},
                                       {"plane_fit_radius", .15},
                                       {"step_noise", .015},
                                       {"max_slope", .22},
                                       {"max_roughness", .012},
                                       {"max_step_up", .035},
                                       {"max_step_down", .035},
                                       {"max_drop_depth", .035},
                                       {"self_rear", .2},
                                       {"self_front", .16},
                                       {"self_half_width", .15},
                                       {"self_z_min", .02},
                                       {"self_z_max", .5}})
      declare_parameter(k, v);
    for (auto [k, v] : std::map<std::string, int>{{"pixel_stride", 4},
                                                  {"roi_top", 0},
                                                  {"min_valid_samples", 3},
                                                  {"min_points_per_cell", 3},
                                                  {"min_plane_neighbors", 6},
                                                  {"step_support", 2}})
      declare_parameter(k, v);
    declare_parameter("spatial_median", false);
    auto validate = [this](const std::vector<rclcpp::Parameter> &updates) {
      rcl_interfaces::msg::SetParametersResult result;
      result.successful = false;
      if (reserved_) {
        result.reason = "stop capture before parameter update";
        return result;
      }
      auto parameter = [&](const std::string &key) {
        for (const auto &v : updates)
          if (v.get_name() == key)
            return v;
        return get_parameter(key);
      };
      auto d = [&](const std::string &key) {
        return parameter(key).as_double();
      };
      auto integer = [&](const std::string &key) {
        return parameter(key).as_int();
      };
      try {
        for (const auto &name : list_parameters({}, 1).names) {
          auto value = parameter(name);
          if (value.get_type() == rclcpp::ParameterType::PARAMETER_DOUBLE) {
            double v = value.as_double();
            bool signed_value =
                name == "x_min" || name == "y_min" || name == "self_z_min";
            if (!std::isfinite(v) || (!signed_value && v <= 0)) {
              result.reason = "invalid threshold: " + name;
              return result;
            }
          }
          if (value.get_type() == rclcpp::ParameterType::PARAMETER_INTEGER &&
              value.as_int() < (name == "roi_top" ? 0 : 1)) {
            result.reason = "invalid count: " + name;
            return result;
          }
        }
        if (d("x_min") >= d("x_max") || d("y_min") >= d("y_max") ||
            d("min_range") >= d("max_range") ||
            d("self_z_min") >= d("self_z_max") ||
            d("gravity_magnitude_min") >= d("gravity_magnitude_max") ||
            d("min_confidence") > 1 || d("min_valid_ratio") > 1 ||
            integer("min_valid_samples") > 4 || integer("pixel_stride") > 64 ||
            integer("min_plane_neighbors") < 3 ||
            (d("x_max") - d("x_min")) / d("resolution") > 256 ||
            (d("y_max") - d("y_min")) / d("resolution") > 256) {
          result.reason = "inconsistent or excessive geometry/count parameters";
          return result;
        }
      } catch (const std::exception &e) {
        result.reason = e.what();
        return result;
      }
      result.successful = true;
      return result;
    };
    auto initial = validate({});
    if (!initial.successful)
      throw std::invalid_argument(initial.reason);
    parameter_callback_ = add_on_set_parameters_callback(validate);
    map_pub_ = create_publisher<loonar_msgs::msg::TerrainMap>(
        "/terrain/map", rclcpp::QoS(1).reliable());
    grid_pub_ = create_publisher<grid_map_msgs::msg::GridMap>(
        "/terrain/grid", rclcpp::QoS(1).reliable());
    cloud_pub_ =
        create_publisher<sensor_msgs::msg::PointCloud2>("/tof/fused_points", 1);
    fused_pub_ = create_publisher<Image>("/loonar/tof/fused_depth", 1);
    confidence_pub_ =
        create_publisher<Image>("/loonar/tof/fused_confidence", 1);
    for (auto key : {"elevation", "slope", "roughness", "step", "depression",
                     "traversability", "unknown", "drop_suspect"})
      layers_[key] = create_publisher<sensor_msgs::msg::PointCloud2>(
          std::string("/terrain/") + key, 1);
    auto qos = rclcpp::SensorDataQoS().keep_last(5);
    info_sub_ = create_subscription<sensor_msgs::msg::CameraInfo>(
        "/loonar/tof/camera_info", qos,
        [this](sensor_msgs::msg::CameraInfo::ConstSharedPtr m) { info_ = m; });
    gravity_sub_ = create_subscription<geometry_msgs::msg::Vector3Stamped>(
        "/imu/gravity", qos,
        [this](geometry_msgs::msg::Vector3Stamped::ConstSharedPtr m) {
          gravity_ = m;
          if (!gravity_history_.empty() &&
              rclcpp::Time(m->header.stamp) <
                  rclcpp::Time(gravity_history_.back()->header.stamp))
            gravity_history_.clear();
          gravity_history_.push_back(m);
          while (gravity_history_.size() > 64)
            gravity_history_.pop_front();
        });
    stationary_sub_ = create_subscription<loonar_msgs::msg::Stationary>(
        "/loonar/stationary", 10,
        [this](loonar_msgs::msg::Stationary::ConstSharedPtr m) {
          stationary_ = m;
        });
    depth_sub_ = create_subscription<Image>("/loonar/tof/depth", qos,
                                            [this](Image::ConstSharedPtr m) {
                                              depths_.push_back(m);
                                              while (depths_.size() > 5)
                                                depths_.pop_front();
                                              collect();
                                            });
    amp_sub_ = create_subscription<Image>("/loonar/tof/amplitude", qos,
                                          [this](Image::ConstSharedPtr m) {
                                            amps_.push_back(m);
                                            while (amps_.size() > 5)
                                              amps_.pop_front();
                                            collect();
                                          });
    server_ = rclcpp_action::create_server<Action>(
        this, "/loonar/build_terrain_map",
        [this](const auto &, auto goal) {
          if (reserved_ || !stationary() || goal->frame_count < 3 ||
              goal->frame_count > 4 ||
              n("min_valid_samples") > goal->frame_count)
            return rclcpp_action::GoalResponse::REJECT;
          reserved_ = true;
          return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
        },
        [](auto) { return rclcpp_action::CancelResponse::ACCEPT; },
        [this](auto goal) {
          goal_ = goal;
          count_ = 0;
          started_ = now();
          last_ = started_;
          samples_.clear();
          depths_.clear();
          amps_.clear();
        });
    timer_ =
        create_wall_timer(std::chrono::milliseconds(20), [this] { tick(); });
  }
};
int main(int argc, char **argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<Perception>());
  rclcpp::shutdown();
}
