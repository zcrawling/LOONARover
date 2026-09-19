#pragma once
#include <array>
#include <cstdint>
namespace loonar::control::pins {
// User-confirmed wiring. Pin 13 is SPI SCK, never a status LED.
inline constexpr std::uint8_t kRoboClawRx = 0, kRoboClawTx = 1;
inline constexpr std::uint8_t kBnoReset = 8, kBnoInterrupt = 9;
inline constexpr std::uint8_t kBnoCs = 10, kBnoMosi = 11, kBnoMiso = 12,
                              kBnoSck = 13;
// Serial3 is a software option; verify HAT wiring before selecting UART.
inline constexpr std::uint8_t kPiUartRx = 15, kPiUartTx = 14;
inline constexpr std::array<std::uint8_t, 10> kAssignedPins = {
    kRoboClawRx, kRoboClawTx, kBnoReset, kBnoInterrupt, kBnoCs,
    kBnoMosi,    kBnoMiso,    kBnoSck,   kPiUartRx,     kPiUartTx};
constexpr bool unique() {
  for (unsigned i = 0; i < kAssignedPins.size(); ++i)
    for (unsigned j = i + 1; j < kAssignedPins.size(); ++j)
      if (kAssignedPins[i] == kAssignedPins[j])
        return false;
  return true;
}
static_assert(unique(), "Control pin collision");
} // namespace loonar::control::pins
