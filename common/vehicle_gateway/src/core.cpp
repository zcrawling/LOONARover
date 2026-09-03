#include "loonar/gateway/core.hpp"

#include <cmath>

namespace loonar::gateway {

Action GatewayCore::ignored() const { return {.status = status_}; }

Action GatewayCore::stop() {
  status_.mode = Mode::kStop;
  status_.last_received = MotionCommand{Source::kStop, 0.0, 0.0};
  status_.reason = Reason::kOk;
  return {.send_zero = true, .status = status_};
}

Action GatewayCore::select_auto() {
  status_.mode = Mode::kAuto;
  status_.reason = Reason::kOk;
  return {.status = status_};
}

Action GatewayCore::submit(const MotionCommand& command) {
  if (!std::isfinite(command.linear_mps) || !std::isfinite(command.angular_radps)) {
    status_.reason = Reason::kNonFinite;
    return ignored();
  }
  status_.last_received = command;
  status_.reason = Reason::kOk;
  if (command.source == Source::kManual) {
    status_.mode = Mode::kManual;
    return {.motion = command, .status = status_};
  }
  if (command.source == Source::kAuto && status_.mode == Mode::kAuto) return {.motion = command, .status = status_};
  return ignored();
}

}  // namespace loonar::gateway
