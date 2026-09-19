#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace loonar::mcu {
constexpr std::size_t kHeader = 32, kPayload = 192,
                      kFrame = kHeader + kPayload + 4;
enum class Type : std::uint8_t {
  HelloRequest = 1,
  Hello = 2,
  Session = 3,
  HealthRequest = 4,
  Health = 5,
  Motion = 6,
  Stop = 7,
  Configure = 8,
  Ack = 9,
  Result = 10,
  TimeRequest = 11,
  Time = 12,
  Imu = 32,
  Motor = 33
};
enum class Role : std::uint8_t { Control = 1, Payload = 2 };
inline std::uint16_t get16(const std::uint8_t *p) {
  return std::uint16_t(p[0]) | std::uint16_t(p[1]) << 8;
}
inline std::uint32_t get32(const std::uint8_t *p) {
  std::uint32_t v = 0;
  for (unsigned i = 0; i < 4; ++i)
    v |= std::uint32_t(p[i]) << (i * 8);
  return v;
}
inline std::uint64_t get64(const std::uint8_t *p) {
  return get32(p) | (std::uint64_t(get32(p + 4)) << 32);
}
inline void put16(std::uint8_t *p, std::uint16_t v) {
  p[0] = std::uint8_t(v);
  p[1] = std::uint8_t(v >> 8);
}
inline void put32(std::uint8_t *p, std::uint32_t v) {
  for (unsigned i = 0; i < 4; ++i)
    p[i] = std::uint8_t(v >> (i * 8));
}
inline void put64(std::uint8_t *p, std::uint64_t v) {
  put32(p, std::uint32_t(v));
  put32(p + 4, std::uint32_t(v >> 32));
}
inline float getFloat(const std::uint8_t *p) {
  const auto bits = get32(p);
  float v;
  std::memcpy(&v, &bits, 4);
  return v;
}
inline void putFloat(std::uint8_t *p, float v) {
  std::uint32_t bits;
  std::memcpy(&bits, &v, 4);
  put32(p, bits);
}
inline std::uint32_t crc32c(const std::uint8_t *p, std::size_t n) {
  std::uint32_t crc = 0xffffffffU;
  for (std::size_t i = 0; i < n; ++i) {
    crc ^= p[i];
    for (unsigned b = 0; b < 8; ++b)
      crc = (crc >> 1) ^ ((crc & 1) ? 0x82f63b78U : 0U);
  }
  return ~crc;
}
struct Frame {
  Role role = Role::Control;
  Type type = Type::HelloRequest;
  std::uint32_t boot = 0, session = 0, sequence = 0;
  std::uint64_t stamp_us = 0;
  std::uint16_t size = 0;
  std::array<std::uint8_t, kPayload> data{};
};
inline std::size_t encode(const Frame &f, std::uint8_t *out) {
  if (f.size > kPayload)
    return 0;
  std::memset(out, 0, kHeader);
  std::memcpy(out, "LNR2", 4);
  out[4] = 2;
  out[5] = std::uint8_t(f.role);
  out[6] = std::uint8_t(f.type);
  put32(out + 8, f.boot);
  put32(out + 12, f.session);
  put32(out + 16, f.sequence);
  put64(out + 20, f.stamp_us);
  put16(out + 28, f.size);
  std::memcpy(out + kHeader, f.data.data(), f.size);
  put32(out + kHeader + f.size, crc32c(out, kHeader + f.size));
  return kHeader + f.size + 4;
}
class Parser {
public:
  std::uint32_t errors = 0;
  bool push(std::uint8_t byte, Frame &f) {
    if (used_ == bytes_.size()) {
      discard();
      ++errors;
    }
    bytes_[used_++] = byte;
    for (;;) {
      if (used_ < 4)
        return false;
      if (std::memcmp(bytes_.data(), "LNR2", 4) != 0) {
        discard();
        continue;
      }
      if (used_ < kHeader)
        return false;
      const auto length = get16(bytes_.data() + 28);
      if (bytes_[4] != 2 || bytes_[7] != 0 || get16(bytes_.data() + 30) != 0 ||
          (bytes_[5] != 1 && bytes_[5] != 2) || length > kPayload) {
        discard();
        ++errors;
        continue;
      }
      const auto total = kHeader + length + 4;
      if (used_ < total)
        return false;
      if (crc32c(bytes_.data(), total - 4) !=
          get32(bytes_.data() + total - 4)) {
        discard();
        ++errors;
        continue;
      }
      f.role = Role(bytes_[5]);
      f.type = Type(bytes_[6]);
      f.boot = get32(bytes_.data() + 8);
      f.session = get32(bytes_.data() + 12);
      f.sequence = get32(bytes_.data() + 16);
      f.stamp_us = get64(bytes_.data() + 20);
      f.size = length;
      std::memcpy(f.data.data(), bytes_.data() + kHeader, length);
      used_ -= total;
      std::memmove(bytes_.data(), bytes_.data() + total, used_);
      return true;
    }
  }
  void expire() {
    if (used_) {
      used_ = 0;
      ++errors;
    }
  }

private:
  void discard() {
    --used_;
    std::memmove(bytes_.data(), bytes_.data() + 1, used_);
  }
  std::array<std::uint8_t, kFrame> bytes_{};
  std::size_t used_ = 0;
};
} // namespace loonar::mcu
