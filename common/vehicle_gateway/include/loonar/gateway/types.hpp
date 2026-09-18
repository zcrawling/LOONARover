#pragma once

#include <cstdint>
#include <optional>

namespace loonar::gateway {

// This is an operator-selected command path, not an authority lease.
enum class Mode : std::uint8_t {
  kAuto = 1,
  kManual = 2,
  kStop = 3,
  kPayload = 4,
  kReaction = 5,
};
enum class Source : std::uint8_t { kAuto = 1, kManual = 2, kStop = 3 };
enum class Reason : std::uint8_t { kOk = 0, kNonFinite = 1 };

struct MotionCommand {
  Source source{Source::kAuto};
  double linear_mps{};
  double angular_radps{};
};

struct Status {
  Mode mode{Mode::kStop};
  std::optional<MotionCommand> last_received{};
  Reason reason{Reason::kOk};
};

enum VehicleStatusField : std::uint32_t {
  kBatteryVoltageValid = 1U << 0U,
  kBatteryPercentValid = 1U << 1U,
  kOdometryPoseValid = 1U << 2U,
  kOdometryMotionValid = 1U << 3U,
  kImuOrientationValid = 1U << 4U,
};

struct VehicleStatus {
  std::uint64_t timestamp_ms{};
  std::uint32_t valid_flags{};
  double battery_voltage{};
  double battery_percent{};
  double odom_x{};
  double odom_y{};
  double odom_yaw{};
  double linear_mps{};
  double angular_radps{};
  double imu_roll{};
  double imu_pitch{};
  double imu_yaw{};
};

struct Action {
  bool send_zero{false};
  std::optional<MotionCommand> motion{};
  Status status{};
};

}  // namespace loonar::gateway
