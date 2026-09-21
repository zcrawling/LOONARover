#include "loonar/control/board_pins.h"
#include "loonar/control/motion_gate.hpp"
#include "loonar/control/roboclaw.hpp"
#include "loonar/control/runtime_v2.hpp"
#include "loonar/control/wire_v2.hpp"
#include "loonar_board_config.h"
#include <Adafruit_BNO08x.h>
#include <Arduino.h>
#include <EEPROM.h>
#include <SPI.h>
#include <Watchdog_t4.h>
#include <arduino_freertos.h>
#include <cmath>
#include <cstring>
#include <new>
#include <queue.h>

#ifndef LOONAR_EXPECTED_UID
#define LOONAR_EXPECTED_UID 0ULL
#endif

namespace loonar::mcu {
namespace {
namespace pins = loonar::control::pins;
constexpr Role role = Role(LOONAR_MCU_ROLE);
constexpr bool control = role == Role::Control;
static_assert(LOONAR_MCU_ROLE == 1 || LOONAR_MCU_ROLE == 2, "Invalid MCU role");
#ifdef LOONAR_CONTROL_USB_CDC
auto &link = Serial;
constexpr std::uint8_t transport = 1;
#else
auto &link = Serial3;
constexpr std::uint8_t transport = 2;
std::uint8_t uart_rx[8192], uart_tx[2048];
#endif
std::uint64_t uid = 0;
std::uint32_t boot = 0, session = 0;
MotionGate gate;
WDT_T4<WDT1> watchdog;
Parser parser;
struct Sample {
  std::uint32_t seq;
  std::uint16_t size;
  Type type;
  std::uint8_t reserved;
  std::uint64_t stamp;
  std::uint8_t data[64];
};
constexpr std::size_t capacity = 2048;
DMAMEM Sample samples[capacity];
std::size_t head = 0, count = 0;
std::uint32_t sample_sequence = 0, dropped = 0, high_dropped = 0, rejected = 0;
std::uint32_t gyro_ms = 0, imu_progress = 0, imu_resets = 0,
              driver_progress = 0, link_progress = 0;
DriverFeedback driver_state;
std::uint32_t driver_baud = 115200, driver_config = 0;
std::uint8_t driver_address = 0x80;
QueueHandle_t priority;
StaticQueue_t priority_store;
std::uint8_t priority_bytes[16 * sizeof(Frame)];
StaticTask_t task_store[2];
StackType_t io_stack[4096], imu_stack[4096];
std::uint64_t clock_us() {
  taskENTER_CRITICAL();
  static std::uint32_t previous = 0;
  static std::uint64_t high = 0;
  const auto now = micros();
  if (now < previous)
    high += 1ULL << 32;
  previous = now;
  const auto result = high + now;
  taskEXIT_CRITICAL();
  return result;
}
std::uint32_t age(std::uint32_t now, std::uint32_t last) {
  return last ? now - last : 0xffffffffU;
}
Frame response(Type type, std::uint32_t sequence = 0) {
  Frame f;
  f.role = role;
  f.type = type;
  f.boot = boot;
  taskENTER_CRITICAL();
  f.session = session;
  taskEXIT_CRITICAL();
  f.sequence = sequence;
  f.stamp_us = clock_us();
  return f;
}
void enqueue(const Frame &f) {
  if (xQueueSend(priority, &f, 0) != pdPASS) {
    taskENTER_CRITICAL();
    ++high_dropped;
    taskEXIT_CRITICAL();
  }
}
void sample(Type type, const std::uint8_t *data, std::uint16_t size,
            std::uint64_t stamp) {
  if (size > 64)
    return;
  taskENTER_CRITICAL();
  // Never reuse a sequence in this boot. A reboot/session renewal is required
  // at exhaustion.
  if (sample_sequence == 0xffffffffU) {
    ++dropped;
    taskEXIT_CRITICAL();
    return;
  }
  const auto seq = ++sample_sequence;
  if (count == capacity) {
    ++dropped;
    taskEXIT_CRITICAL();
    return;
  }
  auto &s = samples[(head + count) % capacity];
  s.seq = seq;
  s.type = type;
  s.size = size;
  s.stamp = stamp;
  std::memcpy(s.data, data, size);
  ++count;
  taskEXIT_CRITICAL();
}
void result(const Frame &request, std::uint8_t code) {
  auto f = response(Type::Result, request.sequence);
  f.size = 8;
  f.data[0] = std::uint8_t(request.type);
  f.data[1] = code;
  put32(f.data.data() + 4, request.sequence);
  enqueue(f);
}
void hello(std::uint32_t seq) {
  auto f = response(Type::Hello, seq);
  f.size = 28;
  put64(f.data.data(), uid);
  put64(f.data.data() + 8, LOONAR_EXPECTED_UID);
  taskENTER_CRITICAL();
  put32(f.data.data() + 16, count ? samples[head].seq : sample_sequence + 1);
  put32(f.data.data() + 20, sample_sequence);
  taskEXIT_CRITICAL();
  put32(f.data.data() + 24, (gate.identity ? 1U : 0U) | (control ? 16U : 0U));
  enqueue(f);
}
void health(std::uint32_t seq) {
  auto f = response(Type::Health, seq);
  f.size = 88;
  auto *p = f.data.data();
  const auto now = millis();
  put64(p, uid);
  put64(p + 8, clock_us() / 1000);
  putFloat(p + 16, tempmonGetTemp());
  put32(p + 20, gate.inhibit);
  put32(p + 24, gate.command);
  taskENTER_CRITICAL();
  put32(p + 28, link_progress);
  put32(p + 32, driver_progress);
  put32(p + 36, imu_progress);
  put32(p + 40, parser.errors);
  put32(p + 44, dropped);
  put32(p + 48, high_dropped);
  put32(p + 52, std::uint32_t(count));
  put32(p + 56, age(now, gyro_ms));
  put32(p + 60,
        driver_state.ack_seen ? age(now, driver_state.ack_ms) : 0xffffffffU);
  put32(p + 64, imu_resets);
  put32(p + 68, rejected);
  put32(p + 72, sample_sequence);
  p[76] = transport;
  p[77] = gate.identity ? 1 : 0;
  put32(p + 80, driver_state.failures);
  put32(p + 84, count ? samples[head].seq : sample_sequence + 1);
  taskEXIT_CRITICAL();
  enqueue(f);
}
std::uint32_t last_request_sequence = 0, sent_sample_sequence = 0;
void handle(const Frame &f) {
  if (f.role != role) {
    ++rejected;
    return;
  }
  if (f.type == Type::HelloRequest && f.size == 0) {
    hello(f.sequence);
    return;
  }
  if (f.boot != boot) {
    ++rejected;
    return;
  }
  if (f.type == Type::Session) {
    if (f.size != 8 || get64(f.data.data()) != uid || !gate.identity ||
        f.session == 0) {
      ++rejected;
      return;
    }
    if (f.session != session) {
      gate.resetSession();
      gate.session = true;
      session = f.session;
      last_request_sequence = 0;
    }
    result(f, 0);
    return;
  }
  if (!session || f.session != session || f.sequence == 0 ||
      f.sequence <= last_request_sequence) {
    ++rejected;
    return;
  }
  last_request_sequence = f.sequence;
  switch (f.type) {
  case Type::HealthRequest:
    if (f.size != 0)
      break;
    health(f.sequence);
    return;
  case Type::TimeRequest: {
    if (f.size != 8)
      break;
    auto reply = response(Type::Time, f.sequence);
    reply.size = 16;
    std::memcpy(reply.data.data(), f.data.data(), 8);
    put64(reply.data.data() + 8, reply.stamp_us);
    enqueue(reply);
    return;
  }
  case Type::Configure: {
    if (!control || f.size != 8 || gate.motion_seen)
      break;
    const auto baud = get32(f.data.data());
    if (f.data[4] < 0x80 || f.data[4] > 0x87 || f.data[5] || f.data[6] ||
        f.data[7] ||
        (baud != 38400 && baud != 57600 && baud != 115200 && baud != 230400 &&
         baud != 460800))
      break;
    driver_baud = baud;
    driver_address = f.data[4];
    ++driver_config;
    result(f, 0);
    return;
  }
  case Type::Motion: {
    if (!control || f.size != 16)
      break;
    std::int32_t left, right;
    const auto l = get32(f.data.data() + 4), r = get32(f.data.data() + 8);
    std::memcpy(&left, &l, 4);
    std::memcpy(&right, &r, 4);
    if (gate.motion(get32(f.data.data()), left, right,
                    get32(f.data.data() + 12), millis())) {
      result(f, 0);
      return;
    }
    break;
  }
  case Type::Stop:
    if (f.size != 0)
      break;
    gate.stop();
    result(f, 0);
    return;
  case Type::Ack: {
    if (f.size != 4)
      break;
    const auto ack = get32(f.data.data());
    taskENTER_CRITICAL();
    if (ack <= sent_sample_sequence) {
      while (count && samples[head].seq <= ack) {
        head = (head + 1) % capacity;
        --count;
      }
    } else
      ++rejected;
    taskEXIT_CRITICAL();
    return;
  }
  default:
    break;
  }
  ++rejected;
  result(f, 1);
}
void transmit() {
  static std::uint8_t bytes[kFrame];
  static std::size_t length = 0, offset = 0;
  static std::uint32_t cursor = 0, last_replay = 0, pending_sample = 0,
                       packet_started = 0, packet_session = 0;
  const auto active_session = session;
  if (offset == length) {
    Frame f;
    if (xQueueReceive(priority, &f, 0) == pdPASS) {
      length = encode(f, bytes);
      offset = 0;
      packet_session = f.session;
      packet_started = millis();
    } else if (active_session) {
      Sample s;
      bool found = false;
      taskENTER_CRITICAL();
      if (count) {
        if (millis() - last_replay >= 100) {
          cursor = samples[head].seq;
          last_replay = millis();
        }
        for (std::size_t i = 0; i < count && i < 128; ++i) {
          const auto &candidate = samples[(head + i) % capacity];
          if (candidate.seq >= cursor) {
            s = candidate;
            found = true;
            break;
          }
        }
      }
      taskEXIT_CRITICAL();
      if (found) {
        f = response(s.type, s.seq);
        f.stamp_us = s.stamp;
        f.size = s.size;
        std::memcpy(f.data.data(), s.data, s.size);
        length = encode(f, bytes);
        offset = 0;
        cursor = s.seq + 1;
        pending_sample = s.seq;
        packet_session = f.session;
        packet_started = millis();
      }
    }
  }
  if (offset < length) {
    // A partial frame abandoned after a long stall cannot block fresh health
    // indefinitely.
    if (packet_session != active_session || millis() - packet_started > 200) {
      offset = length;
      pending_sample = 0;
    } else {
#ifdef LOONAR_CONTROL_USB_CDC
      const int available = Serial ? Serial.availableForWrite() : 0;
#else
      const int available = link.availableForWrite();
#endif
      if (available > 0) {
        const auto n = std::min(length - offset, std::size_t(available));
        offset += link.write(bytes + offset, n);
      }
    }
  }
  if (offset == length && pending_sample) {
    sent_sample_sequence = std::max(sent_sample_sequence, pending_sample);
    pending_sample = 0;
  }
}
bool driver_write(const std::uint8_t *bytes, std::size_t size) {
  return Serial1.availableForWrite() >= int(size) &&
         Serial1.write(bytes, size) == size;
}
void motor_sample(const DriverFeedback &d, std::uint32_t now) {
  std::uint8_t p[64]{};
  put32(p, d.valid(now));
  for (unsigned i = 0; i < 2; ++i) {
    put32(p + 4 + i * 4, std::uint32_t(d.counts[i]));
    put32(p + 12 + i * 4, std::uint32_t(d.speed[i]));
    put32(p + 20 + i * 4, std::uint32_t(d.sent[i]));
    put16(p + 28 + i * 2, std::uint16_t(d.current[i]));
    put16(p + 32 + i * 2, std::uint16_t(d.pwm[i]));
  }
  put16(p + 36, d.main_voltage);
  put16(p + 38, d.logic_voltage);
  put16(p + 40, d.temperature);
  p[42] = d.ack_seen ? 1 : 0;
  put32(p + 44, d.error);
  put32(p + 48, age(now, d.ack_ms));
  put32(p + 52, d.failures);
  put32(p + 56, age(now, d.updated[0]));
  put32(p + 60, age(now, d.updated[1]));
  sample(Type::Motor, p, 64, clock_us());
}
void poll_driver(std::uint32_t now) {
  if (!control || !gate.identity)
    return;
  static RoboClaw driver(driver_write);
  static std::uint32_t config = 0xffffffffU, last_sample = 0;
  if (config != driver_config) {
    Serial1.end();
    Serial1.setRX(pins::kRoboClawRx);
    Serial1.setTX(pins::kRoboClawTx);
    Serial1.begin(driver_baud);
    driver = RoboClaw(driver_write);
    driver.address = driver_address;
    config = driver_config;
  }
  driver.target(gate.left, gate.right);
  for (unsigned budget = 0; budget < 64 && Serial1.available() > 0; ++budget) {
    const int b = Serial1.read();
    if (b >= 0)
      driver.receive(std::uint8_t(b), now);
  }
  driver.tick(now);
  driver_state = driver.feedback;
  ++driver_progress;
  if (now - last_sample >= 20) {
    motor_sample(driver_state, now);
    last_sample = now;
  }
}

void io_task(void *) {
  WDT_timings_t timing;
  timing.timeout = 2;
  timing.trigger = 1;
  watchdog.begin(timing);
  TickType_t wake = xTaskGetTickCount();
  std::uint32_t last_rx = millis(), last_step = millis();
  for (;;) {
    const auto now = millis();
    watchdog.feed();
    if (now - last_rx > 50)
      parser.expire();
    for (unsigned budget = 0; budget < 512 && link.available() > 0; ++budget) {
      const int byte = link.read();
      if (byte < 0)
        break;
      last_rx = now;
      Frame f;
      if (parser.push(std::uint8_t(byte), f))
        handle(f);
    }
    if (now - last_step >= 10) {
      ++link_progress;
      if (control) {
        gate.step(now, tempmonGetTemp());
      } else {
        const float temperature = tempmonGetTemp();
        gate.stop();
        gate.inhibit = (!gate.identity ? std::uint32_t(Identity) : 0U) |
                       (!gate.session ? std::uint32_t(NoSession) : 0U) |
                       (temperature >= 90.0F ? std::uint32_t(Overtemp) : 0U);
      }
      last_step = now;
    }
    poll_driver(now);
    transmit();
    vTaskDelayUntil(&wake, pdMS_TO_TICKS(1));
  }
}
void imu_task(void *) {
  if (!control || !gate.identity) {
    vTaskDelete(nullptr);
    return;
  }
  Adafruit_BNO08x bno(pins::kBnoReset);
  bool ready = false;
  std::uint32_t retry = 0, configured_at = 0;
  std::uint8_t previous[256]{};
  bool seen[256]{};
  for (;;) {
    if (!ready) {
      if (millis() - retry < 2000) {
        vTaskDelay(pdMS_TO_TICKS(10));
        continue;
      }
      retry = millis();
      SPI.setMOSI(pins::kBnoMosi);
      SPI.setMISO(pins::kBnoMiso);
      SPI.setSCK(pins::kBnoSck);
      ready = bno.begin_SPI(pins::kBnoCs, pins::kBnoInterrupt, &SPI);
      if (!ready)
        continue;
      bno.wasReset();
      configured_at = millis();
      std::memset(seen, 0, sizeof(seen));
      ready = bno.enableReport(SH2_GYROSCOPE_CALIBRATED, 5000) &&
              bno.enableReport(SH2_ACCELEROMETER, 5000) &&
              bno.enableReport(SH2_ROTATION_VECTOR, 10000) &&
              bno.enableReport(SH2_LINEAR_ACCELERATION, 20000) &&
              bno.enableReport(SH2_GRAVITY, 20000) &&
              bno.enableReport(SH2_MAGNETIC_FIELD_CALIBRATED, 50000);
      taskENTER_CRITICAL();
      ++imu_resets;
      gyro_ms = 0;
      taskEXIT_CRITICAL();
    }
    taskENTER_CRITICAL();
    const auto last_gyro = gyro_ms;
    taskEXIT_CRITICAL();
    if (ready && millis() - configured_at > 2000 &&
        age(millis(), last_gyro) > 2000) {
      ready = false;
      retry = millis();
      continue;
    }
    if (bno.wasReset()) {
      ready = false;
      retry = 0;
      continue;
    }
    sh2_SensorValue_t v;
    if (ready && bno.getSensorEvent(&v)) {
      const auto received = clock_us();
      float values[5]{};
      switch (v.sensorId) {
      case SH2_GYROSCOPE_CALIBRATED:
        values[0] = v.un.gyroscope.x;
        values[1] = v.un.gyroscope.y;
        values[2] = v.un.gyroscope.z;
        break;
      case SH2_ACCELEROMETER:
        values[0] = v.un.accelerometer.x;
        values[1] = v.un.accelerometer.y;
        values[2] = v.un.accelerometer.z;
        break;
      case SH2_LINEAR_ACCELERATION:
        values[0] = v.un.linearAcceleration.x;
        values[1] = v.un.linearAcceleration.y;
        values[2] = v.un.linearAcceleration.z;
        break;
      case SH2_GRAVITY:
        values[0] = v.un.gravity.x;
        values[1] = v.un.gravity.y;
        values[2] = v.un.gravity.z;
        break;
      case SH2_MAGNETIC_FIELD_CALIBRATED:
        values[0] = v.un.magneticField.x;
        values[1] = v.un.magneticField.y;
        values[2] = v.un.magneticField.z;
        break;
      case SH2_ROTATION_VECTOR:
        values[0] = v.un.rotationVector.i;
        values[1] = v.un.rotationVector.j;
        values[2] = v.un.rotationVector.k;
        values[3] = v.un.rotationVector.real;
        values[4] = v.un.rotationVector.accuracy;
        break;
      default:
        continue;
      }
      bool finite = true;
      for (float value : values)
        finite = finite && std::isfinite(value);
      if (!finite)
        continue;
      const auto id = std::uint8_t(v.sensorId);
      if (seen[id] && v.sequence == previous[id])
        continue;
      const auto lost =
          seen[id] ? std::uint8_t(v.sequence - previous[id] - 1) : 0;
      previous[id] = v.sequence;
      seen[id] = true;
      std::uint8_t p[36]{};
      p[0] = id;
      p[1] = v.status;
      p[2] = v.sequence;
      p[3] = lost;
      put64(p + 4, std::uint64_t(v.timestamp));
      for (unsigned i = 0; i < 5; ++i)
        putFloat(p + 12 + i * 4, values[i]);
      taskENTER_CRITICAL();
      ++imu_progress;
      if (id == SH2_GYROSCOPE_CALIBRATED)
        gyro_ms = millis();
      const auto resets = imu_resets;
      taskEXIT_CRITICAL();
      put32(p + 32, resets);
      sample(Type::Imu, p, 36, received);
    }
    vTaskDelay(pdMS_TO_TICKS(1));
  }
}
} // namespace
bool start() {
  uid = (std::uint64_t(HW_OCOTP_MAC1 & 0xffffU) << 32) | HW_OCOTP_MAC0;
  gate.identity = LOONAR_EXPECTED_UID != 0 && uid == LOONAR_EXPECTED_UID;
  // Boot sequence in EEPROM is diagnostic; session nonce is supplied freshly by
  // the Pi.
  boot = 1;
  if (gate.identity) {
    constexpr int slot = E2END - 7;
    std::uint32_t magic = 0;
    EEPROM.get(slot, magic);
    if (magic == 0x32424e4cU)
      EEPROM.get(slot + 4, boot);
    else
      boot = 0;
    boot = (boot == 0xffffffffU) ? 1 : boot + 1;
    if (!boot)
      boot = 1;
    EEPROM.put(slot, std::uint32_t(0x32424e4cU));
    EEPROM.put(slot + 4, boot);
  }
#ifdef LOONAR_CONTROL_USB_CDC
  Serial.begin(2000000);
#else
  Serial3.setRX(pins::kPiUartRx);
  Serial3.setTX(pins::kPiUartTx);
  Serial3.addMemoryForRead(uart_rx, sizeof(uart_rx));
  Serial3.addMemoryForWrite(uart_tx, sizeof(uart_tx));
  Serial3.begin(2000000);
#endif
  priority =
      xQueueCreateStatic(16, sizeof(Frame), priority_bytes, &priority_store);
  if (!priority)
    return false;
  return xTaskCreateStatic(io_task, "mcu-io", 4096, nullptr, 2, io_stack,
                           &task_store[0]) &&
         xTaskCreateStatic(imu_task, "bno085", 4096, nullptr, 1, imu_stack,
                           &task_store[1]);
}
} // namespace loonar::mcu
