#include <cassert>
#include "loonar/gateway/protocol.hpp"
using loonar::gateway::Mode; using loonar::gateway::MotionCommand; using loonar::gateway::Source;
namespace protocol = loonar::gateway::protocol;
int main() {
  const MotionCommand command{Source::kManual, -0.25, 0.75};
  const auto packet = protocol::decode(protocol::encode_motion(protocol::Type::kMotion, command));
  assert(packet); const auto decoded = protocol::decode_motion(*packet);
  assert(decoded && decoded->source == Source::kManual && decoded->linear_mps == -0.25 && decoded->angular_radps == 0.75);
  loonar::gateway::Status status{Mode::kManual, command};
  const auto encoded_status = protocol::decode(protocol::encode_status(status));
  assert(encoded_status); const auto roundtrip = protocol::decode_status(*encoded_status);
  assert(roundtrip && roundtrip->mode == Mode::kManual && roundtrip->last_received);
  return 0;
}
