#include <Arduino.h>

// Teensy 4.1 Serial6: TX=24 -> BNO RX, RX=25 <- BNO TX.
// BNO055 PS1=HIGH, PS0=LOW before power-on; UART is 115200 8N1.
#ifndef BNO_MODE
#define BNO_MODE 0x0C  // NDOF; use 0x08 for IMUPLUS (no magnetic heading).
#endif
namespace {
HardwareSerial &bno = Serial6;
uint32_t errors = 0;
uint8_t lastError = 0;
bool ready = false;
uint8_t rxTrace[64];
size_t rxCount = 0;
uint32_t lastInit = 0, lastSample = 0;

bool byteUntil(uint8_t &value, uint32_t start) {
  while (!bno.available()) {
    if (uint32_t(millis() - start) >= 150) return false;
    yield();
  }
  value = uint8_t(bno.read());
  if (rxCount < sizeof(rxTrace)) rxTrace[rxCount++] = value;
  return true;
}

bool transaction(uint8_t reg, uint8_t *data, uint8_t length, bool read) {
  for (unsigned attempt = 0; attempt < 3; ++attempt) {
    // One outstanding request. On timeout allow the late reply to drain.
    unsigned stale = 0;
    while (bno.available() && stale < 256) { bno.read(); ++stale; }
    if (stale) Serial.printf("# discarded unsolicited/late bytes=%u\n", stale);
    rxCount = 0;
    const uint8_t cmd[] = {0xAA, uint8_t(read ? 1 : 0), reg, length};
    bno.write(cmd, sizeof(cmd));
    if (!read) bno.write(data, length);
    bno.flush();
    const uint32_t start = millis();
    uint8_t header = 0, status = 0;
    bool ok = byteUntil(header, start) && byteUntil(status, start);
    lastError = 0xFF;  // host timeout
    if (ok && header == 0xEE) {
      lastError = status;
      if (!read && status == 0x01) return true;
    } else if (ok && read && header == 0xBB && status == length) {
      for (uint8_t i = 0; i < length && ok; ++i) ok = byteUntil(data[i], start);
      if (ok) return true;
    } else if (ok) lastError = 0xFE; // malformed response
    Serial.printf("# %s reg=0x%02X len=%u attempt=%u TX=", read ? "READ" : "WRITE", reg, length, attempt+1);
    for (uint8_t x : cmd) Serial.printf("%02X ", x);
    if (!read) for (unsigned i=0; i<length; ++i) Serial.printf("%02X ", data[i]);
    Serial.printf("RX[%u]=", unsigned(rxCount));
    for (unsigned i=0; i<rxCount; ++i) Serial.printf("%02X ", rxTrace[i]);
    if (!rxCount) Serial.print("<none>");
    Serial.printf(" error=0x%02X RX25_level=%d\n", lastError, digitalRead(25));
    ++errors;
    delay(200);
  }
  return false;
}
bool readRegs(uint8_t reg, uint8_t *data, uint8_t n) { return transaction(reg, data, n, true); }
bool writeReg(uint8_t reg, uint8_t value) { return transaction(reg, &value, 1, false); }
int16_t signed16(const uint8_t *p) { return int16_t(uint16_t(p[0]) | (uint16_t(p[1]) << 8)); }

bool initialize() {
  // Read-only presence probe first; expected reply BB 01 A0 after power-on.
  uint8_t probe = 0;
  Serial.println("# probe READ ID: TX AA 01 00 01; expected RX BB 01 A0 on page0");
  if (!readRegs(0x00, &probe, 1)) return false;
  Serial.printf("# probe response=0x%02X (page may not yet be 0)\n", probe);
  if (!writeReg(0x07, 0)) return false;  // PAGE_ID
  uint8_t id = 0;
  if (!readRegs(0x00, &id, 1) || id != 0xA0) {
    Serial.printf("# CHIP_ID=0x%02X, expected 0xA0\n", id);
    return false;
  }
  if (!writeReg(0x3D, 0)) return false; // CONFIGMODE
  delay(30);
  if (!writeReg(0x3E, 0) || !writeReg(0x3B, 0)) return false; // normal power, m/s2, deg/s, degrees
  // Restore default axis map so an earlier application cannot change this test.
  if (!writeReg(0x41, 0x24) || !writeReg(0x42, 0)) return false;
  if (!writeReg(0x3D, BNO_MODE)) return false;
  delay(30);
  uint8_t mode = 0;
  if (!readRegs(0x3D, &mode, 1) || mode != BNO_MODE) return false;
  Serial.printf("# BNO055 ready: CHIP_ID=0x%02X mode=0x%02X TX24 RX25\n", id, mode);
  Serial.println("t_ms,ax,ay,az,gx_dps,gy_dps,gz_dps,heading_deg,roll_deg,pitch_deg,qw,qx,qy,qz,lin_ax,lin_ay,lin_az,grav_x,grav_y,grav_z,temp_c,cal_sys,cal_gyr,cal_acc,cal_mag,sys_status,sys_error,uart_errors");
  return true;
}
}

void setup() {
  Serial.begin(115200);
  const uint32_t start = millis();
  while (!Serial && millis() - start < 3000) {}
  Serial6.setTX(24);
  Serial6.setRX(25);
  bno.begin(115200, SERIAL_8N1);
  delay(1000); // BNO055 boot
  Serial.println("# BNO055 UART diagnostic v2; PS1=3.3V PS0=GND; units acceleration=m/s2.");
  ready = initialize();
  lastInit = millis();
}

void loop() {
  if (!ready) {
    if (uint32_t(millis() - lastInit) < 2000) return;
    Serial.printf("# retry initialization; UART error=0x%02X (FF timeout, FE unexpected response)\n", lastError);
    ready = initialize(); lastInit = millis(); return;
  }
  if (uint32_t(millis() - lastSample) < 20) return; // ~50Hz host polling
  lastSample = millis();
  uint8_t data[51]; // page0 0x08..0x3A: accel through SYS_ERR
  if (!readRegs(0x08, data, sizeof(data))) {
    Serial.printf("# read failed: error=0x%02X total=%lu\n", lastError, (unsigned long)errors);
    ready = false; lastInit = millis(); return;
  }
  Serial.printf("%lu", (unsigned long)millis()); // host receipt, not sensor exposure timestamp
  for (unsigned offset : {0u, 2u, 4u}) Serial.printf(",%.4f", signed16(data + offset) / 100.0);
  for (unsigned offset : {12u, 14u, 16u, 18u, 20u, 22u}) Serial.printf(",%.4f", signed16(data + offset) / 16.0);
  for (unsigned offset : {24u, 26u, 28u, 30u}) Serial.printf(",%.6f", signed16(data + offset) / 16384.0);
  for (unsigned offset : {32u, 34u, 36u, 38u, 40u, 42u}) Serial.printf(",%.4f", signed16(data + offset) / 100.0);
  const uint8_t cal = data[45];
  Serial.printf(",%d,%u,%u,%u,%u,%u,%u,%lu\n", int(int8_t(data[44])), (cal >> 6) & 3,
                (cal >> 4) & 3, (cal >> 2) & 3, cal & 3, data[49], data[50], (unsigned long)errors);
}
