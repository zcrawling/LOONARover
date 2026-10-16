#pragma once
#include <array>
#include <cstdint>
namespace loonar::control::pins {
// 261004 MCU_MOTOR PCB: J3 RoboClaw, J4 BNO055, J2 HAT.
// Pin 13 is routed to the legacy SPI connector, never a status LED.
inline constexpr std::uint8_t kRoboClawRx = 7, kRoboClawTx = 8;
inline constexpr std::uint8_t kBno055Rx = 15, kBno055Tx = 14;
// J4 pin 4 (B_G431B PWM) and J6 pin 2 (SERVO_PWM), 261004 PCB.
inline constexpr std::uint8_t kReactionEsc = 2, kReactionServo = 6;
// Non-USB build: Serial1 through the J2 full-duplex RS-422 transceiver.
inline constexpr std::uint8_t kPiUartRx = 0, kPiUartTx = 1;
inline constexpr std::array<std::uint8_t, 8> kAssignedPins = {
    kRoboClawRx, kRoboClawTx, kPiUartRx, kPiUartTx, kBno055Rx, kBno055Tx,
    kReactionEsc, kReactionServo};
constexpr bool unique() {
  for (unsigned i = 0; i < kAssignedPins.size(); ++i)
    for (unsigned j = i + 1; j < kAssignedPins.size(); ++j)
      if (kAssignedPins[i] == kAssignedPins[j])
        return false;
  return true;
}
static_assert(unique(), "Control pin collision");
} // namespace loonar::control::pins
