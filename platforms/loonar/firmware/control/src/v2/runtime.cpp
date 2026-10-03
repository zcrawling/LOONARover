#include "loonar/control/board_pins.h"
#include "loonar/control/motion_gate.hpp"
#include "loonar/control/roboclaw.hpp"
#include "loonar/control/runtime_v2.hpp"
#include "loonar/control/wire_v2.hpp"
#include "loonar_board_config.h"
#include "loonar/control/bno055.hpp"
#include <Arduino.h>
#include <EEPROM.h>
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
  return Serial2.availableForWrite() >= int(size) &&
         Serial2.write(bytes, size) == size;
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
    Serial2.end();
    Serial2.setRX(pins::kRoboClawRx);
    Serial2.setTX(pins::kRoboClawTx);
    Serial2.begin(driver_baud);
    driver = RoboClaw(driver_write);
    driver.address = driver_address;
    config = driver_config;
  }
  driver.target(gate.left, gate.right);
  for (unsigned budget = 0; budget < 64 && Serial2.available() > 0; ++budget) {
    const int b = Serial2.read();
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
struct BnoUart {
  int available() { return Serial6.available(); }
  int read() { return Serial6.read(); }
  std::size_t write(const std::uint8_t *p, std::size_t n) { return Serial6.write(p,n); }
  std::uint32_t now() { return millis(); }
  void sleep(unsigned ms) { vTaskDelay(pdMS_TO_TICKS(ms)); }
};
void imu_task(void *) {
  if (!control || !gate.identity) { vTaskDelete(nullptr); return; }
  Serial6.setTX(pins::kBno055Tx);
  Serial6.setRX(pins::kBno055Rx);
  Serial6.begin(115200, SERIAL_8N1);
  BnoUart uart;
  loonar::control::Bno055<BnoUart> bno(uart);
  uart.sleep(5000);
  uart.sleep(250);
  std::uint8_t sequence=0;
  for (;;) {
    bool ready=false;
    for (unsigned attempt=0;attempt<5 && !ready;++attempt) {
      ready=bno.begin();
      if (!ready) uart.sleep(150);
    }
    if (!ready) { uart.sleep(2000); continue; }
    taskENTER_CRITICAL();
    ++imu_resets;
    taskEXIT_CRITICAL();
    const auto configured_at=millis();
    while (ready) {
      const auto poll_started=millis();
      std::uint8_t raw[51]{};
      if (!bno.read(0x08,raw,sizeof(raw))) break;
      const auto received=clock_us(); // UART receipt time; no sensor exposure timestamp
      const auto v=loonar::control::decodeBno055(raw);
      // SYS_STATUS=5 is fusion running; never publish reset/failed-fusion data.
      if (v.error) break;
      if (v.status!=5) {
        if (millis()-configured_at>2000) break;
        uart.sleep(20); continue;
      }
      const std::uint8_t ids[]={1,2,5,4,6}; // Existing wire-v2 report types
      const float *vectors[]={v.accel,v.gyro,v.quaternion,v.linear,v.gravity};
      const std::uint8_t quality[]={std::uint8_t((v.calibration>>2)&3),
        std::uint8_t((v.calibration>>4)&3),std::uint8_t((v.calibration>>6)&3),
        std::uint8_t((v.calibration>>2)&3),std::uint8_t((v.calibration>>2)&3)};
      taskENTER_CRITICAL();
      gyro_ms=millis();
      const auto resets=imu_resets;
      taskEXIT_CRITICAL();
      for (unsigned report=0;report<5;++report) {
        std::uint8_t p[36]{};
        p[0]=ids[report]; p[1]=quality[report]; p[2]=sequence;
        put64(p+4,received);
        for (unsigned i=0;i<(report==2?4U:3U);++i) putFloat(p+12+i*4,vectors[report][i]);
        put32(p+32,resets);
        sample(Type::Imu,p,sizeof(p),received);
        taskENTER_CRITICAL(); ++imu_progress; taskEXIT_CRITICAL();
      }
      ++sequence;
      const auto elapsed=millis()-poll_started;
      uart.sleep(elapsed<20?20-elapsed:1);
    }
    taskENTER_CRITICAL(); gyro_ms=0; taskEXIT_CRITICAL();
    uart.sleep(2000);
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
  const bool io_started = xTaskCreateStatic(io_task, "mcu-io", 4096, nullptr, 2, io_stack,
                           &task_store[0]) != nullptr;
#if defined(LOONAR_ENCODER_VERIFY)
#ifdef LOONAR_ENCODER_VERIFY
  static_assert(LOONAR_EXPECTED_UID != 0, "Set LOONAR_BOARD_UID for encoder verification");
#endif
  return io_started;
#else
  return io_started &&
         xTaskCreateStatic(imu_task, "bno055", 4096, nullptr, 1, imu_stack,
                           &task_store[1]);
#endif
}
} // namespace loonar::mcu
