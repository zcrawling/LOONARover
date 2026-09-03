#pragma once

#include <cstdint>
#include <optional>
#include <span>
#include <vector>

#include "loonar/gateway/types.hpp"

namespace loonar::gateway::protocol {

constexpr std::uint32_t kMagic = 0x4C4E5247U;  // "LNRG"
constexpr std::uint16_t kVersion = 1;
constexpr std::size_t kHeaderSize = 12;
constexpr std::size_t kMaxPacketSize = 256;

enum class Type : std::uint16_t {
  kHello = 1, kMotion = 2, kStop = 3, kSelectAuto = 4,
  kStatus = 5, kBackendMotion = 6
};

struct Packet { Type type{}; std::vector<std::uint8_t> payload{}; };

std::vector<std::uint8_t> encode(const Packet& packet);
std::optional<Packet> decode(std::span<const std::uint8_t> bytes);
std::vector<std::uint8_t> encode_motion(Type type, const MotionCommand& command);
std::optional<MotionCommand> decode_motion(const Packet& packet);
std::vector<std::uint8_t> encode_status(const Status& status);
std::optional<Status> decode_status(const Packet& packet);

}  // namespace loonar::gateway::protocol
