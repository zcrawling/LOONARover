#pragma once
#include <cstdint>

namespace loonar::mcu {
enum Inhibit : std::uint32_t {
  Identity = 1U,
  NoSession = 2U,
  MotionExpired = 8U,
  DriverStale = 32U,
  Overtemp = 128U
};

// The Pi supplies left/right qpps. No IMU, vehicle geometry or acceleration
// policy here.
struct MotionGate {
  bool identity = false, session = false, motion_seen = false;
  std::uint32_t motion_ms = 0, command = 0, lease_ms = 0;
  std::int32_t left = 0, right = 0;
  std::uint32_t inhibit = Identity | NoSession;

  void stop() {
    motion_seen = false;
    left = right = 0;
  }
  void resetSession() {
    session = false;
    stop();
    command = 0;
  }
  bool motion(std::uint32_t id, std::int32_t l, std::int32_t r,
              std::uint32_t lease, std::uint32_t now) {
    if (!identity || !session || (inhibit & Overtemp) || id == 0 ||
        id <= command || lease < 20 || lease > 200)
      return false;
    command = id;
    motion_ms = now;
    lease_ms = lease;
    left = l;
    right = r;
    motion_seen = true;
    return true;
  }
  void step(std::uint32_t now, bool driver_ok, float temperature) {
    inhibit = (!identity ? std::uint32_t(Identity) : 0U) |
              (!session ? std::uint32_t(NoSession) : 0U) |
              (!motion_seen || now - motion_ms >= lease_ms
                   ? std::uint32_t(MotionExpired)
                   : 0U) |
              (!driver_ok ? std::uint32_t(DriverStale) : 0U) |
              (temperature >= 90.0F ? std::uint32_t(Overtemp) : 0U);
    if (inhibit)
      stop();
  }
};
} // namespace loonar::mcu
