#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace loonar::mcu {
// Packet serial transaction engine. No retry loop or blocking read on the MCU.
// Wire commands follow Basicmicro's published RoboClaw packet serial API.
struct DriverFeedback {
  // All paired fields use rover order [left, right]: M2, M1.
  std::int32_t counts[2]{}, speed[2]{}, sent[2]{};
  std::int16_t current[2]{}, pwm[2]{};
  std::uint16_t main_voltage = 0, logic_voltage = 0, temperature = 0;
  std::uint32_t error = 0, updated[8]{}, ack_ms = 0, failures = 0;
  bool ack_seen = false;
  std::uint32_t valid(std::uint32_t now) const {
    std::uint32_t mask = 0;
    for (unsigned i = 0; i < 8; ++i)
      if (updated[i] && now - updated[i] < 500)
        mask |= 1U << i;
    return mask;
  }
};
class RoboClaw {
public:
  using Write = bool (*)(const std::uint8_t *, std::size_t);
  explicit RoboClaw(Write writer) : write_(writer) {}
  DriverFeedback feedback{};
  std::uint8_t address = 0x80;
  void target(std::int32_t left, std::int32_t right) {
    target_[0] = left;
    target_[1] = right;
  }
  void tick(std::uint32_t now) {
    if (waiting_) {
      if (now - started_ >= 10) {
        waiting_ = false;
        quiet_ = true;
        quiet_since_ = now;
        ++feedback.failures;
        feedback.ack_seen = false;
      }
      return;
    }
    if (quiet_) {
      if (now - quiet_since_ < 20)
        return;
      quiet_ = false;
    }
    if (now - last_command_ >= 20 || (!target_[0] && !target_[1] &&
                                      (feedback.sent[0] || feedback.sent[1]))) {
      std::uint8_t tx[12] = {address, 37};
      // Physical wiring is fixed: M1 = right, M2 = left.
      be32(tx + 2, std::uint32_t(target_[1]));
      be32(tx + 6, std::uint32_t(target_[0]));
      const auto crc = checksum(tx, 10);
      tx[10] = std::uint8_t(crc >> 8);
      tx[11] = std::uint8_t(crc);
      if (!write_(tx, sizeof(tx)))
        return;
      pending_[0] = target_[0];
      pending_[1] = target_[1];
      last_command_ = now;
      begin(37, 1, now);
      return;
    }
    static constexpr std::uint8_t commands[] = {78, 79, 49, 78, 79, 24, 78, 79,
                                                25, 78, 79, 82, 78, 79, 90, 48};
    const auto cmd = commands[poll_index_];
    const std::uint8_t tx[] = {address, cmd};
    if (!write_(tx, 2))
      return;
    poll_index_ = (poll_index_ + 1) % sizeof(commands);
    const std::size_t data_len = (cmd == 78 || cmd == 79)                ? 8
                                 : (cmd == 49 || cmd == 90 || cmd == 48) ? 4
                                                                         : 2;
    begin(cmd, data_len + 2, now);
    crc_ = checksum(tx, 2);
  }
  void receive(std::uint8_t value, std::uint32_t now) {
    if (!waiting_) {
      quiet_since_ = now;
      return;
    }
    rx_[received_++] = value;
    if (received_ < expected_)
      return;
    waiting_ = false;
    if (command_ == 37) {
      if (value == 0xff) {
        feedback.ack_ms = now;
        feedback.ack_seen = true;
        feedback.sent[0] = pending_[0];
        feedback.sent[1] = pending_[1];
      } else
        fail(now);
      return;
    }
    const auto n = expected_ - 2;
    for (std::size_t i = 0; i < n; ++i)
      crc_ = update(crc_, rx_[i]);
    if (crc_ != u16(rx_ + n)) {
      fail(now);
      return;
    }
    unsigned group = 0;
    switch (command_) {
    case 78:
      feedback.counts[1] = i32(rx_);
      feedback.counts[0] = i32(rx_ + 4);
      group = 0;
      break;
    case 79:
      feedback.speed[1] = i32(rx_);
      feedback.speed[0] = i32(rx_ + 4);
      group = 1;
      break;
    case 49:
      feedback.current[1] = std::int16_t(u16(rx_));
      feedback.current[0] = std::int16_t(u16(rx_ + 2));
      group = 2;
      break;
    case 24:
      feedback.main_voltage = u16(rx_);
      group = 3;
      break;
    case 25:
      feedback.logic_voltage = u16(rx_);
      group = 4;
      break;
    case 82:
      feedback.temperature = u16(rx_);
      group = 5;
      break;
    case 90:
      feedback.error = u32(rx_);
      group = 6;
      break;
    case 48:
      feedback.pwm[1] = std::int16_t(u16(rx_));
      feedback.pwm[0] = std::int16_t(u16(rx_ + 2));
      group = 7;
      break;
    default:
      return;
    }
    feedback.updated[group] = now;
  }

private:
  static std::uint16_t update(std::uint16_t crc, std::uint8_t b) {
    crc ^= std::uint16_t(b) << 8;
    for (unsigned i = 0; i < 8; ++i)
      crc = std::uint16_t((crc << 1) ^ ((crc & 0x8000) ? 0x1021 : 0));
    return crc;
  }
  static std::uint16_t checksum(const std::uint8_t *p, std::size_t n) {
    std::uint16_t c = 0;
    for (std::size_t i = 0; i < n; ++i)
      c = update(c, p[i]);
    return c;
  }
  static void be32(std::uint8_t *p, std::uint32_t v) {
    for (unsigned i = 0; i < 4; ++i)
      p[i] = std::uint8_t(v >> (24 - i * 8));
  }
  static std::uint16_t u16(const std::uint8_t *p) {
    return (std::uint16_t(p[0]) << 8) | p[1];
  }
  static std::uint32_t u32(const std::uint8_t *p) {
    return (std::uint32_t(u16(p)) << 16) | u16(p + 2);
  }
  static std::int32_t i32(const std::uint8_t *p) {
    const auto u = u32(p);
    std::int32_t v;
    std::memcpy(&v, &u, 4);
    return v;
  }
  void begin(std::uint8_t cmd, std::size_t n, std::uint32_t now) {
    command_ = cmd;
    expected_ = n;
    received_ = 0;
    started_ = now;
    waiting_ = true;
  }
  void fail(std::uint32_t now) {
    ++feedback.failures;
    feedback.ack_seen = false;
    quiet_ = true;
    quiet_since_ = now;
  }
  Write write_;
  bool waiting_ = false, quiet_ = false;
  std::uint32_t started_ = 0, last_command_ = 0, quiet_since_ = 0;
  std::uint8_t command_ = 0, rx_[10]{};
  std::size_t expected_ = 0, received_ = 0, poll_index_ = 0;
  std::uint16_t crc_ = 0;
  std::int32_t target_[2]{}, pending_[2]{};
};
} // namespace loonar::mcu
