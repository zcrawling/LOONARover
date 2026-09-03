#pragma once

#include <cstdint>
#include <optional>

namespace loonar::gateway {

// This is an operator-selected command path, not an authority lease.
enum class Mode : std::uint8_t { kAuto = 1, kManual = 2, kStop = 3 };
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

struct Action {
  bool send_zero{true};
  std::optional<MotionCommand> motion{};
  Status status{};
};

}  // namespace loonar::gateway
