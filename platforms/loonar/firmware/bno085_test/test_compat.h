#pragma once
#include <Arduino.h>
#include <SPI.h>
#include <stdarg.h>
#include <stdio.h>
inline void testPrintf(const char *format, ...) {
  char buffer[256];
  va_list args;
  va_start(args, format);
  vsnprintf(buffer, sizeof(buffer), format, args);
  va_end(args);
  Serial.print(buffer);
}
#ifdef BNO_MKR_SOFT_SPI
// Requested MKR ZERO wiring; mode 3, MSB first. GPIO overhead limits speed.
class BnoSoftSPI {
public:
  void begin() {
    pinMode(4, OUTPUT); digitalWrite(4, LOW);
    pinMode(11, INPUT);
    pinMode(12, OUTPUT); digitalWrite(12, HIGH);
  }
  void beginTransaction(const SPISettings &) { digitalWrite(12, HIGH); }
  void endTransaction() {}
  uint8_t transfer(uint8_t value) {
    uint8_t received = 0;
    for (unsigned bit = 0; bit < 8; ++bit) {
      digitalWrite(12, LOW);
      digitalWrite(4, (value & 0x80) ? HIGH : LOW);
      delayMicroseconds(1);
      digitalWrite(12, HIGH);
      delayMicroseconds(1);
      received = (received << 1) | (digitalRead(11) ? 1 : 0);
      value <<= 1;
    }
    return received;
  }
};
#endif
