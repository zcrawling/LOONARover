#include "loonar/gateway/protocol.hpp"

#include <bit>
#include <cstring>

namespace loonar::gateway::protocol {
namespace {
void put16(std::vector<std::uint8_t>& out, std::uint16_t value) {
  out.push_back(static_cast<std::uint8_t>(value & 0xFFU));
  out.push_back(static_cast<std::uint8_t>((value >> 8U) & 0xFFU));
}
void put32(std::vector<std::uint8_t>& out, std::uint32_t value) {
  for (unsigned shift = 0; shift < 32; shift += 8) out.push_back(static_cast<std::uint8_t>(value >> shift));
}
void put64(std::vector<std::uint8_t>& out, std::uint64_t value) {
  for (unsigned shift = 0; shift < 64; shift += 8) out.push_back(static_cast<std::uint8_t>(value >> shift));
}
std::optional<std::uint16_t> get16(std::span<const std::uint8_t> in, std::size_t& at) {
  if (at + 2 > in.size()) return std::nullopt;
  const auto value = static_cast<std::uint16_t>(in[at]) | (static_cast<std::uint16_t>(in[at + 1]) << 8U);
  at += 2; return value;
}
std::optional<std::uint32_t> get32(std::span<const std::uint8_t> in, std::size_t& at) {
  if (at + 4 > in.size()) return std::nullopt;
  std::uint32_t value{}; for (unsigned shift = 0; shift < 32; shift += 8) value |= static_cast<std::uint32_t>(in[at++]) << shift;
  return value;
}
std::optional<std::uint64_t> get64(std::span<const std::uint8_t> in, std::size_t& at) {
  if (at + 8 > in.size()) return std::nullopt;
  std::uint64_t value{}; for (unsigned shift = 0; shift < 64; shift += 8) value |= static_cast<std::uint64_t>(in[at++]) << shift;
  return value;
}
void put_double(std::vector<std::uint8_t>& out, double value) { put64(out, std::bit_cast<std::uint64_t>(value)); }
std::optional<double> get_double(std::span<const std::uint8_t> in, std::size_t& at) {
  const auto bits = get64(in, at); if (!bits) return std::nullopt; return std::bit_cast<double>(*bits);
}
}  // namespace

std::vector<std::uint8_t> encode(const Packet& packet) {
  std::vector<std::uint8_t> out; out.reserve(kHeaderSize + packet.payload.size());
  put32(out, kMagic); put16(out, kVersion); put16(out, static_cast<std::uint16_t>(packet.type));
  put32(out, static_cast<std::uint32_t>(packet.payload.size()));
  out.insert(out.end(), packet.payload.begin(), packet.payload.end()); return out;
}

std::optional<Packet> decode(std::span<const std::uint8_t> bytes) {
  if (bytes.size() < kHeaderSize || bytes.size() > kMaxPacketSize) return std::nullopt;
  std::size_t at{}; const auto magic = get32(bytes, at); const auto version = get16(bytes, at);
  const auto type = get16(bytes, at); const auto length = get32(bytes, at);
  if (!magic || !version || !type || !length || *magic != kMagic || *version != kVersion ||
      *length != bytes.size() - kHeaderSize) return std::nullopt;
  return Packet{static_cast<Type>(*type), {bytes.begin() + static_cast<std::ptrdiff_t>(at), bytes.end()}};
}

std::vector<std::uint8_t> encode_motion(Type type, const MotionCommand& command) {
  Packet packet{type, {}}; auto& p = packet.payload; p.reserve(17);
  p.push_back(static_cast<std::uint8_t>(command.source));
  put_double(p, command.linear_mps); put_double(p, command.angular_radps);
  return encode(packet);
}

std::optional<MotionCommand> decode_motion(const Packet& packet) {
  if ((packet.type != Type::kMotion && packet.type != Type::kBackendMotion) || packet.payload.size() != 17) return std::nullopt;
  std::size_t at{}; std::span<const std::uint8_t> p(packet.payload);
  const auto source = static_cast<Source>(p[at++]);
  if (source != Source::kAuto && source != Source::kManual && !(packet.type == Type::kBackendMotion && source == Source::kStop)) return std::nullopt;
  const auto linear = get_double(p, at); const auto angular = get_double(p, at);
  if (!linear || !angular) return std::nullopt;
  return MotionCommand{source, *linear, *angular};
}

std::vector<std::uint8_t> encode_status(const Status& status) {
  Packet packet{Type::kStatus, {}};
  packet.payload.push_back(static_cast<std::uint8_t>(status.mode));
  packet.payload.push_back(status.last_received.has_value() ? static_cast<std::uint8_t>(status.last_received->source) : 0U);
  put_double(packet.payload, status.last_received ? status.last_received->linear_mps : 0.0);
  put_double(packet.payload, status.last_received ? status.last_received->angular_radps : 0.0);
  packet.payload.push_back(static_cast<std::uint8_t>(status.reason));
  return encode(packet);
}

std::optional<Status> decode_status(const Packet& packet) {
  if (packet.type != Type::kStatus || packet.payload.size() != 19) return std::nullopt;
  const auto mode = static_cast<Mode>(packet.payload[0]);
  if (mode != Mode::kAuto && mode != Mode::kManual && mode != Mode::kStop) return std::nullopt;
  std::size_t at = 1; const auto raw_source = packet.payload[at++]; std::optional<MotionCommand> last;
  if (raw_source != 0U) {
    const auto parsed = static_cast<Source>(raw_source);
    if (parsed != Source::kAuto && parsed != Source::kManual && parsed != Source::kStop) return std::nullopt;
    const auto linear = get_double(packet.payload, at); const auto angular = get_double(packet.payload, at);
    if (!linear || !angular) return std::nullopt;
    last = MotionCommand{parsed, *linear, *angular};
  } else {
    at += 16;
  }
  if (at + 1 != packet.payload.size()) return std::nullopt;
  const auto reason = static_cast<Reason>(packet.payload[at++]);
  if (reason != Reason::kOk && reason != Reason::kNonFinite) return std::nullopt;
  return Status{mode, last, reason};
}

}  // namespace loonar::gateway::protocol
