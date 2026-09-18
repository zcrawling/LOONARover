#ifndef LOONAR_CONTROL_BOARD_PINS_H
#define LOONAR_CONTROL_BOARD_PINS_H

#include <array>
#include <cstddef>
#include <cstdint>

#if !defined(ARDUINO_TEENSY41)
#error "This pin map is only for Teensy 4.1"
#endif

namespace loonar::control::pins {

inline constexpr std::uint8_t kStatusLed = 13;

// MPU full-duplex RS-485 link: Teensy Serial1 primary pins.
inline constexpr std::uint8_t kUartRx = 0;
inline constexpr std::uint8_t kUartTx = 1;

// Quadrature motor encoders.
inline constexpr std::uint8_t kLeftEncoderA = 2;
inline constexpr std::uint8_t kLeftEncoderB = 3;
inline constexpr std::uint8_t kRightEncoderA = 4;
inline constexpr std::uint8_t kRightEncoderB = 5;

// Two PWM + direction + enable motor-driver channels.
inline constexpr std::uint8_t kLeftMotorPwm = 6;
inline constexpr std::uint8_t kLeftMotorDirection = 7;
inline constexpr std::uint8_t kLeftMotorEnable = 8;
inline constexpr std::uint8_t kRightMotorPwm = 9;
inline constexpr std::uint8_t kRightMotorDirection = 10;
inline constexpr std::uint8_t kRightMotorEnable = 11;

// BNO085 on Teensy Wire (I2C0).
inline constexpr std::uint8_t kBno085Sda = 18;
inline constexpr std::uint8_t kBno085Scl = 19;
inline constexpr std::uint8_t kBno085Interrupt = 20;
inline constexpr std::uint8_t kBno085Reset = 21;

inline constexpr std::uint32_t kUartBaud = 2'000'000;
inline constexpr std::uint32_t kBno085I2cHz = 400'000;
inline constexpr std::uint32_t kMotorPwmHz = 20'000;
inline constexpr std::uint8_t kMotorPwmBits = 12;
inline constexpr bool kMotorEnableActiveHigh = true;

inline constexpr std::array<std::uint8_t, 17> kAssignedPins = {
    kStatusLed,
    kUartRx,
    kUartTx,
    kLeftEncoderA,
    kLeftEncoderB,
    kRightEncoderA,
    kRightEncoderB,
    kLeftMotorPwm,
    kLeftMotorDirection,
    kLeftMotorEnable,
    kRightMotorPwm,
    kRightMotorDirection,
    kRightMotorEnable,
    kBno085Sda,
    kBno085Scl,
    kBno085Interrupt,
    kBno085Reset,
};

constexpr bool assigned_pins_are_unique() {
  for (std::size_t left = 0; left < kAssignedPins.size(); ++left) {
    for (std::size_t right = left + 1; right < kAssignedPins.size(); ++right) {
      if (kAssignedPins[left] == kAssignedPins[right]) {
        return false;
      }
    }
  }
  return true;
}

static_assert(assigned_pins_are_unique(), "Control MCU pin assignments overlap");

}  // namespace loonar::control::pins

#endif
