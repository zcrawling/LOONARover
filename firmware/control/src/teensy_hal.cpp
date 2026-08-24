#include "loonar/control/teensy_hal.h"

#include <Arduino.h>
#include <Wire.h>

#include <cmath>
#include <cstddef>
#include <cstdint>

#include "loonar/control/board_pins.h"

namespace {

using namespace loonar::control;

std::uint8_t uart_rx_storage[256] = {};
std::uint8_t uart_tx_storage[64] = {};

constexpr std::uint8_t enable_level(bool enabled) {
  return enabled == pins::kMotorEnableActiveHigh ? HIGH : LOW;
}

void stop_motors() {
  analogWrite(pins::kLeftMotorPwm, 0);
  analogWrite(pins::kRightMotorPwm, 0);
  digitalWrite(pins::kLeftMotorEnable, enable_level(false));
  digitalWrite(pins::kRightMotorEnable, enable_level(false));
}

void write_motor(std::uint8_t pwm_pin,
                 std::uint8_t direction_pin,
                 std::uint8_t enable_pin,
                 float duty) {
  constexpr std::uint16_t kPwmMax =
      static_cast<std::uint16_t>((1U << pins::kMotorPwmBits) - 1U);
  if (!std::isfinite(duty) || duty == 0.0F) {
    analogWrite(pwm_pin, 0);
    digitalWrite(enable_pin, enable_level(false));
    return;
  }
  if (duty > 1.0F) {
    duty = 1.0F;
  } else if (duty < -1.0F) {
    duty = -1.0F;
  }
  digitalWrite(direction_pin, duty >= 0.0F ? HIGH : LOW);
  const float magnitude = duty >= 0.0F ? duty : -duty;
  analogWrite(pwm_pin, static_cast<int>(magnitude * static_cast<float>(kPwmMax)));
  digitalWrite(enable_pin, enable_level(true));
}

std::uint32_t monotonic_ms() {
  return millis();
}

std::int32_t board_temp_mdeg_c() {
  return static_cast<std::int32_t>(tempmonGetTemp() * 1000.0F);
}

bool uart_start() {
  Serial1.setRX(pins::kUartRx);
  Serial1.setTX(pins::kUartTx);
  Serial1.addMemoryForRead(uart_rx_storage, sizeof(uart_rx_storage));
  Serial1.addMemoryForWrite(uart_tx_storage, sizeof(uart_tx_storage));
  Serial1.begin(pins::kUartBaud);
  return true;
}

std::size_t uart_read(std::uint8_t *output, std::size_t capacity) {
  std::size_t count = 0;
  if (output == nullptr) {
    return 0;
  }
  while (count < capacity && Serial1.available() > 0) {
    const int value = Serial1.read();
    if (value < 0) {
      break;
    }
    output[count] = static_cast<std::uint8_t>(value);
    ++count;
  }
  return count;
}

bool uart_write(const std::uint8_t *data, std::size_t size) {
  return data != nullptr && Serial1.write(data, size) == size;
}

void apply_motor_duty(float left_duty, float right_duty) {
  write_motor(pins::kLeftMotorPwm, pins::kLeftMotorDirection, pins::kLeftMotorEnable,
              left_duty);
  write_motor(pins::kRightMotorPwm, pins::kRightMotorDirection, pins::kRightMotorEnable,
              right_duty);
}

const LnrControlHal kHal = {
    monotonic_ms,
    board_temp_mdeg_c,
    uart_start,
    uart_read,
    uart_write,
    apply_motor_duty,
};

}  // namespace

extern "C" void lnr_teensy_board_init(void) {
  using namespace loonar::control;

  pinMode(pins::kLeftMotorEnable, OUTPUT);
  pinMode(pins::kRightMotorEnable, OUTPUT);
  digitalWrite(pins::kLeftMotorEnable, enable_level(false));
  digitalWrite(pins::kRightMotorEnable, enable_level(false));

  pinMode(pins::kLeftMotorDirection, OUTPUT);
  pinMode(pins::kRightMotorDirection, OUTPUT);
  digitalWrite(pins::kLeftMotorDirection, LOW);
  digitalWrite(pins::kRightMotorDirection, LOW);

  pinMode(pins::kLeftMotorPwm, OUTPUT);
  pinMode(pins::kRightMotorPwm, OUTPUT);
  analogWriteResolution(pins::kMotorPwmBits);
  analogWriteFrequency(pins::kLeftMotorPwm, pins::kMotorPwmHz);
  analogWriteFrequency(pins::kRightMotorPwm, pins::kMotorPwmHz);
  stop_motors();

  pinMode(pins::kLeftEncoderA, INPUT);
  pinMode(pins::kLeftEncoderB, INPUT);
  pinMode(pins::kRightEncoderA, INPUT);
  pinMode(pins::kRightEncoderB, INPUT);

  pinMode(pins::kBno085Interrupt, INPUT_PULLUP);
  pinMode(pins::kBno085Reset, OUTPUT);
  digitalWrite(pins::kBno085Reset, HIGH);
  Wire.setSDA(pins::kBno085Sda);
  Wire.setSCL(pins::kBno085Scl);
  Wire.begin();
  Wire.setClock(pins::kBno085I2cHz);
}

extern "C" const LnrControlHal *lnr_teensy_control_hal(void) {
  return &kHal;
}
