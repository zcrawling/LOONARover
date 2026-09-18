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
  loonar::gateway::VehicleStatus vehicle{1234, loonar::gateway::kBatteryVoltageValid | loonar::gateway::kOdometryPoseValid,
                                         11.7, 0.0, 1.0, 2.0, 0.5, 0.4, 1.0, 0.1, 0.2, 0.3};
  const auto vehicle_packet = protocol::decode(protocol::encode_vehicle_status(vehicle));
  assert(vehicle_packet); const auto vehicle_roundtrip = protocol::decode_vehicle_status(*vehicle_packet);
  assert(vehicle_roundtrip && vehicle_roundtrip->timestamp_ms == 1234 && vehicle_roundtrip->battery_voltage == 11.7 &&
         vehicle_roundtrip->odom_y == 2.0 && vehicle_roundtrip->imu_yaw == 0.3);
  return 0;
}
