#pragma once

#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>
#include <string>
#include <vector>

namespace loonar::ground_link {

constexpr std::uint32_t kMagic = 0x314B4E4CU;  // "LNK1" on the wire.
constexpr std::uint16_t kVersion = 1;
constexpr std::size_t kHeaderSize = 16;
constexpr std::size_t kMaxPayloadSize = 512;
constexpr std::size_t kMaxFrameSize = kHeaderSize + kMaxPayloadSize;

enum class Type : std::uint16_t {
  kStopCommand = 0x0001,
  kManualCommand = 0x0002,
  kAutoCommand = 0x0003,
  kPayloadCommand = 0x0004,
  kReactionCommand = 0x0005,
  kCommandResult = 0x8001,
  kGatewayStatus = 0x8002,
  kVehicleStatus = 0x8003,
  kLoonarMcuStatus = 0x8004,
  kDeviceStatus = 0x8005,
  kEvent = 0x8006,
};

struct Frame {
  Type type{};
  std::uint32_t sequence{};
  std::vector<std::uint8_t> payload{};
};

struct ManualCommand {
  double linear_mps{};
  double angular_radps{};
};

struct ActivityCommand {
  std::uint64_t request_id{};
  std::uint16_t opcode{};
  std::vector<std::uint8_t> parameters{};
};

struct CommandResult {
  std::uint32_t ground_sequence{};
  std::uint16_t command_type{};
  bool cfs_received{};
  bool adapter_forwarded{};
  std::uint8_t current_mode{};
  std::uint8_t result_code{};
};

struct GatewayStatus {
  std::uint8_t mode{};
  std::uint8_t last_source{};
  bool has_last_command{};
  std::uint8_t reason{};
  double last_linear_mps{};
  double last_angular_radps{};
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

struct McuStatus {
  std::uint64_t timestamp_ms{};
  std::uint64_t uptime_ms{};
  double board_temperature_c{};
  std::uint16_t mcu_state{};
  std::uint32_t inhibit_flags{};
  double applied_linear_mps{};
  double applied_angular_radps{};
  std::uint32_t rx_error_count{};
};

struct DeviceEntry {
  std::uint8_t state{};
  std::uint64_t last_update_ms{};
};

struct DeviceStatus {
  std::uint64_t timestamp_ms{};
  std::vector<DeviceEntry> devices{};
};

struct Event {
  std::uint64_t timestamp_ms{};
  std::uint8_t severity{};
  std::uint32_t code{};
  std::string source{};
  std::string text{};
};

std::vector<std::uint8_t> encode(const Frame& frame);
std::optional<Frame> decode(std::span<const std::uint8_t> bytes);
std::vector<std::uint8_t> encode_manual(const ManualCommand& command);
std::optional<ManualCommand> decode_manual(std::span<const std::uint8_t> payload);
std::vector<std::uint8_t> encode_activity(const ActivityCommand& command);
std::optional<ActivityCommand> decode_activity(std::span<const std::uint8_t> payload);
std::optional<CommandResult> decode_command_result(std::span<const std::uint8_t> payload);
std::optional<GatewayStatus> decode_gateway_status(std::span<const std::uint8_t> payload);
std::optional<VehicleStatus> decode_vehicle_status(std::span<const std::uint8_t> payload);
std::optional<McuStatus> decode_mcu_status(std::span<const std::uint8_t> payload);
std::optional<DeviceStatus> decode_device_status(std::span<const std::uint8_t> payload);
std::optional<Event> decode_event(std::span<const std::uint8_t> payload);

class StreamDecoder {
 public:
  bool append(std::span<const std::uint8_t> bytes);
  std::optional<Frame> next();
  [[nodiscard]] std::size_t buffered_size() const noexcept { return buffer_.size(); }

 private:
  std::vector<std::uint8_t> buffer_{};
};

}  // namespace loonar::ground_link
