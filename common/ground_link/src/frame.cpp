#include "loonar/ground_link/frame.hpp"

#include <array>
#include <bit>
#include <limits>

namespace loonar::ground_link {
namespace {
void put16(std::vector<std::uint8_t>& out, std::uint16_t value) {
  out.push_back(static_cast<std::uint8_t>(value));
  out.push_back(static_cast<std::uint8_t>(value >> 8U));
}
void put32(std::vector<std::uint8_t>& out, std::uint32_t value) {
  for (unsigned shift = 0; shift < 32; shift += 8) out.push_back(static_cast<std::uint8_t>(value >> shift));
}
void put64(std::vector<std::uint8_t>& out, std::uint64_t value) {
  for (unsigned shift = 0; shift < 64; shift += 8) out.push_back(static_cast<std::uint8_t>(value >> shift));
}
std::optional<std::uint16_t> get16(std::span<const std::uint8_t> in, std::size_t& at) {
  if (at + 2 > in.size()) return std::nullopt;
  const auto value = static_cast<std::uint16_t>(in[at]) |
                     static_cast<std::uint16_t>(static_cast<std::uint16_t>(in[at + 1]) << 8U);
  at += 2; return value;
}
std::optional<std::uint32_t> get32(std::span<const std::uint8_t> in, std::size_t& at) {
  if (at + 4 > in.size()) return std::nullopt;
  std::uint32_t value{};
  for (unsigned shift = 0; shift < 32; shift += 8) value |= static_cast<std::uint32_t>(in[at++]) << shift;
  return value;
}
std::optional<std::uint64_t> get64(std::span<const std::uint8_t> in, std::size_t& at) {
  if (at + 8 > in.size()) return std::nullopt;
  std::uint64_t value{};
  for (unsigned shift = 0; shift < 64; shift += 8) value |= static_cast<std::uint64_t>(in[at++]) << shift;
  return value;
}
void put_double(std::vector<std::uint8_t>& out, double value) { put64(out, std::bit_cast<std::uint64_t>(value)); }
std::optional<double> get_double(std::span<const std::uint8_t> in, std::size_t& at) {
  const auto bits = get64(in, at); if (!bits) return std::nullopt; return std::bit_cast<double>(*bits);
}
bool known_type(Type type) {
  switch (type) {
    case Type::kStopCommand: case Type::kManualCommand: case Type::kAutoCommand:
    case Type::kPayloadCommand: case Type::kReactionCommand: case Type::kCommandResult:
    case Type::kGatewayStatus: case Type::kVehicleStatus: case Type::kLoonarMcuStatus:
    case Type::kDeviceStatus: case Type::kEvent: return true;
  }
  return false;
}
}  // namespace

std::vector<std::uint8_t> encode(const Frame& frame) {
  if (!known_type(frame.type) || frame.payload.size() > kMaxPayloadSize) return {};
  std::vector<std::uint8_t> out; out.reserve(kHeaderSize + frame.payload.size());
  put32(out, kMagic); put16(out, kVersion); put16(out, static_cast<std::uint16_t>(frame.type));
  put32(out, frame.sequence); put32(out, static_cast<std::uint32_t>(frame.payload.size()));
  out.insert(out.end(), frame.payload.begin(), frame.payload.end()); return out;
}

std::optional<Frame> decode(std::span<const std::uint8_t> bytes) {
  if (bytes.size() < kHeaderSize || bytes.size() > kMaxFrameSize) return std::nullopt;
  std::size_t at{}; const auto magic=get32(bytes,at); const auto version=get16(bytes,at);
  const auto raw_type=get16(bytes,at); const auto sequence=get32(bytes,at); const auto length=get32(bytes,at);
  if (!magic || !version || !raw_type || !sequence || !length || *magic != kMagic || *version != kVersion ||
      *length > kMaxPayloadSize || bytes.size() != kHeaderSize + *length) return std::nullopt;
  const auto type=static_cast<Type>(*raw_type); if (!known_type(type)) return std::nullopt;
  return Frame{type,*sequence,{bytes.begin()+static_cast<std::ptrdiff_t>(at),bytes.end()}};
}

std::vector<std::uint8_t> encode_manual(const ManualCommand& command) {
  std::vector<std::uint8_t> out; out.reserve(16); put_double(out,command.linear_mps); put_double(out,command.angular_radps); return out;
}
std::optional<ManualCommand> decode_manual(std::span<const std::uint8_t> payload) {
  if (payload.size() != 16) return std::nullopt;
  std::size_t at{};
  const auto linear = get_double(payload, at);
  const auto angular = get_double(payload, at);
  if (!linear || !angular) return std::nullopt;
  return ManualCommand{*linear, *angular};
}
std::vector<std::uint8_t> encode_activity(const ActivityCommand& command) {
  if (command.parameters.size() > kMaxPayloadSize - 12) return {};
  std::vector<std::uint8_t> out; put64(out,command.request_id); put16(out,command.opcode);
  put16(out,static_cast<std::uint16_t>(command.parameters.size())); out.insert(out.end(),command.parameters.begin(),command.parameters.end()); return out;
}
std::optional<ActivityCommand> decode_activity(std::span<const std::uint8_t> payload) {
  if (payload.size() < 12) return std::nullopt;
  std::size_t at{};
  const auto request = get64(payload, at);
  const auto opcode = get16(payload, at);
  const auto length = get16(payload, at);
  if (!request || !opcode || !length || payload.size() != 12U + static_cast<std::size_t>(*length)) {
    return std::nullopt;
  }
  return ActivityCommand{*request, *opcode,
                         {payload.begin() + static_cast<std::ptrdiff_t>(at), payload.end()}};
}

std::optional<CommandResult> decode_command_result(std::span<const std::uint8_t> payload) {
  if (payload.size() != 10) return std::nullopt;
  std::size_t at{};
  const auto sequence = get32(payload, at);
  const auto command = get16(payload, at);
  if (!sequence || !command) return std::nullopt;
  return CommandResult{*sequence, *command, payload[6] != 0, payload[7] != 0, payload[8], payload[9]};
}

std::optional<GatewayStatus> decode_gateway_status(std::span<const std::uint8_t> payload) {
  if (payload.size() != 20) return std::nullopt;
  std::size_t at = 4;
  const auto linear = get_double(payload, at);
  const auto angular = get_double(payload, at);
  if (!linear || !angular) return std::nullopt;
  return GatewayStatus{payload[0], payload[1], payload[2] != 0, payload[3], *linear, *angular};
}

std::optional<VehicleStatus> decode_vehicle_status(std::span<const std::uint8_t> payload) {
  if (payload.size() != 92) return std::nullopt;
  std::size_t at{};
  const auto timestamp = get64(payload, at);
  const auto valid = get32(payload, at);
  std::array<double, 10> values{};
  for (auto& value : values) {
    const auto decoded = get_double(payload, at);
    if (!decoded) return std::nullopt;
    value = *decoded;
  }
  return VehicleStatus{*timestamp, *valid, values[0], values[1], values[2], values[3], values[4],
                       values[5], values[6], values[7], values[8], values[9]};
}

std::optional<McuStatus> decode_mcu_status(std::span<const std::uint8_t> payload) {
  if (payload.size() != 50) return std::nullopt;
  std::size_t at{};
  const auto timestamp = get64(payload, at);
  const auto uptime = get64(payload, at);
  const auto temperature = get_double(payload, at);
  const auto state = get16(payload, at);
  const auto inhibits = get32(payload, at);
  const auto linear = get_double(payload, at);
  const auto angular = get_double(payload, at);
  const auto errors = get32(payload, at);
  if (!timestamp || !uptime || !temperature || !state || !inhibits || !linear || !angular || !errors) return std::nullopt;
  return McuStatus{*timestamp, *uptime, *temperature, *state, *inhibits, *linear, *angular, *errors};
}

std::optional<DeviceStatus> decode_device_status(std::span<const std::uint8_t> payload) {
  if (payload.size() < 9) return std::nullopt;
  std::size_t at{};
  const auto timestamp = get64(payload, at);
  if (!timestamp) return std::nullopt;
  const auto count = payload[at++];
  if (payload.size() != 9U + static_cast<std::size_t>(count) * 9U) return std::nullopt;
  DeviceStatus status{*timestamp, {}};
  status.devices.reserve(count);
  for (std::uint8_t i = 0; i < count; ++i) {
    const auto state = payload[at++];
    const auto updated = get64(payload, at);
    if (!updated) return std::nullopt;
    status.devices.push_back({state, *updated});
  }
  return status;
}

std::optional<Event> decode_event(std::span<const std::uint8_t> payload) {
  if (payload.size() < 16) return std::nullopt;
  std::size_t at{};
  const auto timestamp = get64(payload, at);
  if (!timestamp) return std::nullopt;
  const auto severity = payload[at++];
  const auto code = get32(payload, at);
  if (!code) return std::nullopt;
  const auto source_length = payload[at++];
  const auto text_length = get16(payload, at);
  if (!text_length || at + source_length + *text_length != payload.size()) return std::nullopt;
  const std::string source(reinterpret_cast<const char*>(payload.data() + at), source_length);
  at += source_length;
  const std::string text(reinterpret_cast<const char*>(payload.data() + at), *text_length);
  return Event{*timestamp, severity, *code, source, text};
}
bool StreamDecoder::append(std::span<const std::uint8_t> bytes) {
  if (bytes.size() > 2*kMaxFrameSize || buffer_.size() > 2*kMaxFrameSize-bytes.size()) { buffer_.clear(); return false; }
  buffer_.insert(buffer_.end(),bytes.begin(),bytes.end()); return true;
}
std::optional<Frame> StreamDecoder::next() {
  if (buffer_.size()<kHeaderSize) return std::nullopt;
  std::size_t at=12; const auto length=get32(buffer_,at);
  if (!length || *length>kMaxPayloadSize) { buffer_.clear(); return std::nullopt; }
  const auto total=kHeaderSize+static_cast<std::size_t>(*length); if (buffer_.size()<total) return std::nullopt;
  auto frame=decode(std::span<const std::uint8_t>(buffer_.data(),total));
  buffer_.erase(buffer_.begin(),buffer_.begin()+static_cast<std::ptrdiff_t>(total)); return frame;
}
}  // namespace loonar::ground_link
