#include "loonar/control/board_pins.h"
#include "loonar/control/motion_gate.hpp"
#include "loonar/control/roboclaw.hpp"
#include "loonar/control/wire_v2.hpp"
#include <cassert>
#include <iostream>
#include <limits>
#include <vector>
using namespace loonar::mcu;
static std::vector<std::uint8_t> written;
static bool write_packet(const std::uint8_t *p, std::size_t n) {
  written.assign(p, p + n);
  return true;
}
static std::uint16_t crc16(const std::vector<std::uint8_t> &p) {
  std::uint16_t c = 0;
  for (auto b : p) {
    c ^= std::uint16_t(b) << 8;
    for (int i = 0; i < 8; ++i)
      c = std::uint16_t((c << 1) ^ ((c & 0x8000) ? 0x1021 : 0));
  }
  return c;
}
static void parser_test() {
  const auto *check = reinterpret_cast<const std::uint8_t *>("123456789");
  assert(crc32c(check, 9) == 0xe3069283U);
  Frame a;
  a.role = Role::Payload;
  a.type = Type::Motion;
  a.boot = 7;
  a.session = 9;
  a.sequence = 11;
  a.stamp_us = 0x1122334455667788ULL;
  a.size = 16;
  put32(a.data.data(), 0x89abcdef);
  putFloat(a.data.data() + 4, 1.25F);
  std::uint8_t raw[kFrame];
  auto n = encode(a, raw);
  Parser parser;
  Frame out;
  int got = 0;
  for (std::size_t i = 0; i < n; ++i)
    if (parser.push(raw[i], out))
      ++got;
  assert(got == 1 && out.role == Role::Payload && out.sequence == 11 &&
         out.stamp_us == a.stamp_us && getFloat(out.data.data() + 4) == 1.25F);
  raw[n - 1] ^= 1;
  for (std::size_t i = 0; i < n; ++i)
    assert(!parser.push(raw[i], out));
  assert(parser.errors > 0);
  raw[n - 1] ^= 1;
  for (std::size_t i = 0; i < n; ++i)
    if (parser.push(raw[i], out))
      ++got;
  assert(got == 2);
  for (int i = 0; i < 15; ++i)
    parser.push(raw[i], out);
  parser.expire();
  for (std::size_t i = 0; i < n; ++i)
    if (parser.push(raw[i], out))
      ++got;
  assert(got == 3);
  // Maximum-sized frame split at every byte remains bounded.
  a.size = kPayload;
  n = encode(a, raw);
  for (std::size_t i = 0; i < n; ++i)
    if (parser.push(raw[i], out))
      ++got;
  assert(got == 4);
}
static void gate_test() {
  MotionGate g;
  g.session = true;
  assert(!g.motion(1, 1234, -5678, 200, 100));
  g.identity = true;
  assert(g.motion(1, 1234, -5678, 200, 100));
  g.step(110, 89.99F);
  // Direct command: no acceleration ramp, geometry or IMU dependency.
  assert(g.left == 1234 && g.right == -5678 && g.inhibit == 0);
  assert(!g.motion(1, 9999, 9999, 200, 230));
  assert(g.motion_ms == 100);
  g.step(299, 40);
  assert(g.left == 1234 && g.right == -5678);
  g.step(300, 40);
  assert(g.left == 0 && !g.motion_seen);
  assert(!g.motion(2, 1, 2, 201, 310));
  assert(g.motion(2, 1, 2, 200, 310));
  g.step(320, 90.0F);
  assert((g.inhibit & Overtemp) && g.left == 0 && g.right == 0);
  assert(!g.motion(3, 1, 2, 200, 330));
  g.step(340, 89.0F);
  assert(g.left == 0 && !g.motion_seen);
  assert(g.motion(3, 1000, 2000, 200, 340));
  g.step(350, 89.0F);
  assert(g.left == 1000 && g.right == 2000);
  g.step(360, 90.1F);
  assert(g.inhibit & Overtemp);
  g.step(370, 40);
  assert(g.motion(4, 1, 2, 200, 370));
  assert(g.motion(5, 3, 4, 200, 569));
  g.step(570, 40);
  assert(g.left == 3 && g.right == 4); // A new command renews the deadline.
  assert(g.motion(6, 100, 200, 200, 0xfffffff0U));
  g.step(183, 40); // 199 ms across millis() wrap.
  assert(g.left == 100);
  g.step(184, 40); // Exactly 200 ms across wrap.
  assert(g.inhibit & MotionExpired);
  g.resetSession();
  assert(!g.motion(1, 100, 200, 200, 200));
}
static void feedback_failure_does_not_stop_test() {
  MotionGate gate;
  gate.identity = gate.session = true;
  assert(gate.motion(1, 123, 456, 200, 20));
  RoboClaw driver(write_packet);
  driver.target(gate.left, gate.right);
  driver.tick(20);
  driver.receive(0xff, 21);
  driver.tick(22); // Start encoder query, then let its response time out.
  assert(written[1] == 78);
  driver.tick(32);
  assert(!driver.feedback.ack_seen && driver.feedback.failures == 1);
  gate.step(40, 40);
  assert(gate.inhibit == 0 && gate.left == 123 && gate.right == 456);
  driver.target(gate.left, gate.right);
  driver.tick(52); // After the serial quiet interval, resend the same speeds.
  assert(written[1] == 37);
  driver.receive(0xff, 53);
  assert(driver.feedback.sent[0] == 123 && driver.feedback.sent[1] == 456);
  driver.tick(54);
  for (int i = 0; i < 10; ++i)
    driver.receive(0, 55); // Deliberately invalid query CRC.
  assert(driver.feedback.failures == 2 && !driver.feedback.ack_seen);
  gate.step(60, 40);
  assert(gate.inhibit == 0 && gate.left == 123 && gate.right == 456);
  gate.step(220, 40); // Only motion expiry zeros this otherwise valid command.
  assert(gate.inhibit & MotionExpired);
  assert(gate.left == 0 && gate.right == 0);
}
static void driver_test() {
  RoboClaw d(write_packet);
  d.target(123, -456);
  d.tick(20);
  assert(written.size() == 12 && written[1] == 37);
  // left=123 goes to M2; right=-456 goes to M1, including signed encoding.
  assert(written[2] == 255 && written[3] == 255 && written[4] == 254 &&
         written[5] == 56 && written[6] == 0 && written[9] == 123);
  const auto c =
      crc16(std::vector<std::uint8_t>(written.begin(), written.end() - 2));
  assert(written[10] == (c >> 8) && written[11] == (c & 255));
  d.receive(0xff, 21);
  assert(d.feedback.ack_seen && d.feedback.sent[0] == 123 &&
         d.feedback.sent[1] == -456);
  d.target(0, 0);
  d.tick(22);
  assert(written[1] == 37);
  d.receive(0xff, 23);
  assert(d.feedback.sent[0] == 0);
  d.tick(24);
  assert(written[1] == 78);
  std::vector<std::uint8_t> r = {0x80, 78, 0, 0, 0, 1, 255, 255, 255, 254};
  const auto rc = crc16(r);
  for (std::size_t i = 2; i < r.size(); ++i)
    d.receive(r[i], 25);
  d.receive(std::uint8_t(rc >> 8), 25);
  d.receive(std::uint8_t(rc), 25);
  assert(d.feedback.counts[0] == -2 && d.feedback.counts[1] == 1 &&
         d.feedback.valid(25) & 1);
  d.tick(26);
  d.tick(36);
  assert(!d.feedback.ack_seen && d.feedback.failures == 1);
  // Late ACK in quarantine cannot validate a new write.
  d.receive(0xff, 38);
  d.tick(57);
  assert(!d.feedback.ack_seen);
  d.tick(58);
  assert(written[1] == 37);
  d.receive(0x00, 59);
  assert(d.feedback.failures == 2 && !d.feedback.ack_seen);
}
static void feedback_side_test() {
  RoboClaw d(write_packet);
  d.tick(20);
  d.receive(0xff, 21);
  // Complete one polling cycle. Replies arrive as M1/right, M2/left.
  // Keep the clock below the next speed-command deadline.
  for (unsigned i = 0; i < 16; ++i) {
    d.tick(22);
    const auto command = written[1];
    std::vector<std::uint8_t> reply = {0x80, command};
    if (command == 78 || command == 79)
      reply.insert(reply.end(), {0, 0, 0, 17, 255, 255, 255, 233});
    else if (command == 49 || command == 48)
      reply.insert(reply.end(), {0, 17, 255, 233});
    else if (command == 90)
      reply.insert(reply.end(), {0, 0, 0, 0});
    else
      reply.insert(reply.end(), {0, 0});
    const auto crc = crc16(reply);
    for (std::size_t j = 2; j < reply.size(); ++j)
      d.receive(reply[j], 23);
    d.receive(std::uint8_t(crc >> 8), 23);
    d.receive(std::uint8_t(crc), 23);
  }
  assert(d.feedback.counts[0] == -23 && d.feedback.counts[1] == 17);
  assert(d.feedback.speed[0] == -23 && d.feedback.speed[1] == 17);
  assert(d.feedback.current[0] == -23 && d.feedback.current[1] == 17);
  assert(d.feedback.pwm[0] == -23 && d.feedback.pwm[1] == 17);
}
int main(int argc, char **argv) {
  if (argc == 2) {
    Frame f;
    f.type = Type::Motion;
    f.role = Role::Control;
    f.boot = 7;
    f.session = 9;
    f.sequence = 11;
    f.stamp_us = 123456;
    f.size = 16;
    put32(f.data.data(), 42);
    put32(f.data.data() + 4, 123456);
    put32(f.data.data() + 8, std::uint32_t(-654321));
    put32(f.data.data() + 12, 150);
    std::uint8_t bytes[kFrame];
    auto n = encode(f, bytes);
    for (std::size_t i = 0; i < n; ++i)
      std::printf("%02x", bytes[i]);
    std::puts("");
    return 0;
  }
  (void)argv;
  parser_test();
  gate_test();
  driver_test();
  feedback_failure_does_not_stop_test();
  feedback_side_test();
  std::cout << "MCU v2 wire, motion lease and RoboClaw tests passed\n";
}
