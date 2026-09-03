#include <cassert>
#include <cmath>
#include "loonar/gateway/core.hpp"
using loonar::gateway::GatewayCore; using loonar::gateway::Mode; using loonar::gateway::MotionCommand; using loonar::gateway::Reason; using loonar::gateway::Source;
int main() {
  GatewayCore core;
  // AUTO motion cannot release STOP.
  assert(!core.submit({Source::kAuto, 0.4, 1.0}).motion);
  assert(core.status().mode == Mode::kStop);
  assert(core.select_auto().status.mode == Mode::kAuto);
  assert(core.submit({Source::kAuto, 0.4, 1.0}).motion);
  // MANUAL takes precedence and subsequent ROS commands are recorded, not sent.
  assert(core.submit({Source::kManual, 0.1, 0.2}).motion);
  assert(core.status().mode == Mode::kManual);
  assert(!core.submit({Source::kAuto, 0.2, 0.3}).motion);
  assert(core.stop().send_zero && core.status().mode == Mode::kStop);
  assert(!core.submit({Source::kAuto, 0.2, 0.3}).motion);
  assert(!core.submit({Source::kManual, std::nan(""), 0.0}).motion);
  assert(core.status().reason == Reason::kNonFinite);
  return 0;
}
