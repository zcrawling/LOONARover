#pragma once
#include <cstdint>

namespace loonar::mcu {
// All pulse widths are microseconds; all durations are milliseconds.
struct ReactionConfig {
  std::uint16_t esc_neutral = 1488, servo_neutral = 1500;
  std::uint16_t left_first_offset = 25, left_second_offset = 50;
  std::uint16_t right_first_offset = 25, right_second_offset = 50;
  std::uint16_t servo_left = 800, servo_right = 2200;
  std::uint32_t left_first_ms = 5000, right_first_ms = 10000;
  std::uint32_t second_ms = 10000, servo_delay_ms = 10, servo_hold_ms = 3000;
  std::uint32_t prepare_ms = 5000;
  bool valid() const {
    return esc_neutral >= 1148 && esc_neutral <= 1832 &&
      servo_neutral >= 800 && servo_neutral <= 2200 &&
      servo_left >= 800 && servo_left <= 2200 &&
      servo_right >= 800 && servo_right <= 2200 &&
      left_first_offset > 0 && left_first_offset <= left_second_offset &&
      right_first_offset > 0 && right_first_offset <= right_second_offset &&
      left_second_offset <= 1832 - esc_neutral &&
      right_second_offset <= esc_neutral - 1148 &&
      left_first_ms > 0 && left_first_ms <= 60000 &&
      right_first_ms > 0 && right_first_ms <= 60000 &&
      second_ms > 0 && second_ms <= 60000 &&
      servo_delay_ms >= 10 && servo_delay_ms <= 10000 &&
      servo_hold_ms > 0 && servo_hold_ms <= 10000 &&
      prepare_ms >= 5000 && prepare_ms <= 60000;
  }
};

class ReactionWheel {
public:
  enum class State : std::uint8_t { Preparing, Ready, First, Second, NeutralWait, ServoHold };
  ReactionConfig config;
  State state = State::Preparing;
  std::uint16_t esc_us = 1488, servo_us = 1500;
  std::uint8_t direction = 0;
  std::uint32_t since = 0;
  bool active() const { return state != State::Preparing && state != State::Ready; }
  void neutral() { esc_us = config.esc_neutral; servo_us = config.servo_neutral; }
  void begin(std::uint32_t now) { state = State::Preparing; since = now; direction = 0; neutral(); }
  void stop() { neutral(); direction = 0; if (state != State::Preparing) state = State::Ready; }
  bool configure(const ReactionConfig &value) {
    if (active() || !value.valid()) return false;
    config = value; neutral(); return true;
  }
  bool start(std::uint8_t side, std::uint32_t now) {
    if (state != State::Ready || (side != 1 && side != 2)) return false;
    direction = side; servo_us = config.servo_neutral;
    esc_us = side == 1 ? config.esc_neutral + config.left_first_offset :
                        config.esc_neutral - config.right_first_offset;
    state = State::First; since = now; return true;
  }
  void tick(std::uint32_t now, bool permitted) {
    if (!permitted && active()) { stop(); return; }
    const auto elapsed = std::uint32_t(now - since);
    switch (state) {
    case State::Preparing:
      if (elapsed >= config.prepare_ms) state = State::Ready;
      break;
    case State::Ready: break;
    case State::First:
      if (elapsed >= (direction == 1 ? config.left_first_ms : config.right_first_ms)) {
        esc_us = direction == 1 ? config.esc_neutral + config.left_second_offset :
                                 config.esc_neutral - config.right_second_offset;
        state = State::Second; since = now;
      }
      break;
    case State::Second:
      if (elapsed >= config.second_ms) {
        esc_us = config.esc_neutral; state = State::NeutralWait; since = now;
      }
      break;
    case State::NeutralWait:
      if (elapsed >= config.servo_delay_ms) {
        servo_us = direction == 1 ? config.servo_left : config.servo_right;
        state = State::ServoHold; since = now;
      }
      break;
    case State::ServoHold:
      if (elapsed >= config.servo_hold_ms) stop();
      break;
    }
  }
};
} // namespace loonar::mcu
