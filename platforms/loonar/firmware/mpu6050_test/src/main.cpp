#include <Arduino.h>
#include <Wire.h>
#include "gyro_bias.hpp"

namespace {
constexpr uint8_t SDA_PIN = 18, SCL_PIN = 19;
uint8_t address = 0;
bool ready = false;
GyroBias calibration;

void startCalibration() {
  calibration.start(millis());
  Serial.println("CAL START: keep rover stationary; settle 3s + measure 5s. c=retry calibration");
}
uint32_t samples = 0, errors = 0, lastSample = 0, lastPrint = 0, lastStatus = 0;

bool readRegisters(uint8_t reg, uint8_t *out, uint8_t count) {
  Wire.beginTransmission(address);
  Wire.write(reg);
  const uint8_t result = Wire.endTransmission(false);
  if (result) { ++errors; return false; }
  const uint8_t received = Wire.requestFrom(address, count);
  if (received != count) {
    while (Wire.available()) Wire.read();
    ++errors; return false;
  }
  for (uint8_t i=0; i<count; ++i) out[i] = Wire.read();
  return true;
}
bool writeRegister(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(address);
  Wire.write(reg); Wire.write(value);
  const auto result = Wire.endTransmission();
  if (result) {
    ++errors;
    Serial.printf("WRITE FAIL addr=0x%02X reg=0x%02X I2C_error=%u\n", address, reg, result);
  }
  return result == 0;
}
void diagnoseWrites() {
  Serial.println("WRITE DIAG: no reset; compare immediate and 100ms readback");
  uint8_t original=0;
  const bool saved=readRegisters(0x19, &original, 1);
  if (!saved) { Serial.println("Cannot save reg19; diagnostic skipped"); return; }
  for (uint8_t value : {uint8_t(7), uint8_t(19)}) {
    const bool ack=writeRegister(0x19,value);
    uint8_t first=0xff, later=0xff;
    const bool r1=readRegisters(0x19,&first,1);
    delay(100);
    const bool r2=readRegisters(0x19,&later,1);
    Serial.printf("REG19 tx=0x%02X ack=%d immediate=0x%02X read_ok=%d after100ms=0x%02X read_ok=%d\n",
                  value,ack,first,r1,later,r2);
  }
  const bool restored=writeRegister(0x19,original);
  uint8_t restoredValue=0xff;
  const bool restoreRead=readRegisters(0x19,&restoredValue,1);
  Serial.printf("REG19 restore_ack=%d read_ok=%d matched=%d\n",restored,restoreRead,
                restored && restoreRead && restoredValue==original);
  const bool ack=writeRegister(0x6B,0);
  uint8_t first=0xff, later=0xff, divider=0xff;
  const bool r1=readRegisters(0x6B,&first,1);
  delay(100);
  const bool r2=readRegisters(0x6B,&later,1);
  const bool r3=readRegisters(0x19,&divider,1);
  Serial.printf("REG6B tx=0x00 ack=%d immediate=0x%02X read_ok=%d after100ms=0x%02X read_ok=%d reg19=0x%02X read_ok=%d\n",
                ack,first,r1,later,r2,divider,r3);
  Serial.println("Diagnostic only; initialization still FAILED. r=retry");
}
int16_t signedWord(const uint8_t *p) {
  const uint16_t word = (uint16_t(p[0]) << 8) | p[1];
  return word < 0x8000 ? int16_t(word) : int16_t(int32_t(word)-65536);
}
bool beginSensor() {
  calibration=GyroBias{};
  ready = false; samples = errors = lastSample = 0;
  for (unsigned attempt=1; attempt<=5; ++attempt) {
    Serial.printf("BEGIN %u/5\n", attempt);
    address = 0;
    for (uint8_t candidate : {uint8_t(0x68), uint8_t(0x69)}) {
      Wire.beginTransmission(candidate);
      const auto ack = Wire.endTransmission();
      Serial.printf("PROBE 0x%02X I2C_error=%u (0=ACK)\n", candidate, ack);
      if (ack) continue;
      address = candidate;
      uint8_t id=0;
      if (readRegisters(0x75, &id, 1)) {
        Serial.printf("WHO_AM_I=0x%02X (expected 0x68)\n", id);
        if (id==0x68) break;
      }
      address = 0;
    }
    bool ok = address && writeRegister(0x6B, 0x80); // Device reset.
    if (ok) {
      // Poll reset completion instead of assuming a fixed delay is enough.
      delay(100);
      bool resetDone = false;
      const uint32_t resetStart = millis();
      while (millis()-resetStart < 1000) {
        uint8_t power = 0xff;
        if (readRegisters(0x6B, &power, 1) && !(power & 0x80)) {
          Serial.printf("RESET bit clear (reset execution not proven) PWR_MGMT_1=0x%02X\n", power);
          resetDone = true;
          break;
        }
        delay(20);
      }
      if (!resetDone) Serial.println("RESET timeout");
      bool awake = false;
      for (unsigned wake=1; resetDone && wake<=5; ++wake) {
        // Wake on internal clock first, then select the gyro PLL below.
        const bool written = writeRegister(0x6B, 0x00);
        delay(100);
        uint8_t power=0xff;
        const bool read = readRegisters(0x6B, &power, 1);
        Serial.printf("WAKE %u/5 write_ack=%d read_ok=%d reg6B=0x%02X expected=0x00\n",
                      wake, written, read, power);
        if (written && read && power==0) { awake=true; break; }
        if (wake<5) delay(150);
      }
      ok = false;
      if (awake) {
        const bool pllAck=writeRegister(0x6B,0x01);
        delay(100);
        uint8_t pll=0xff;
        const bool pllRead=readRegisters(0x6B,&pll,1);
        Serial.printf("PLL write_ack=%d read_ok=%d reg6B=0x%02X expected=0x01\n",pllAck,pllRead,pll);
        ok = pllAck && pllRead && pll==1;
      } else {
        Serial.println("PLL skipped: wake failed");
      }
      ok = ok && writeRegister(0x6C, 0x00) && // All axes enabled.
           writeRegister(0x1A, 0x03) && // DLPF gyro 42Hz, accel 44Hz.
           writeRegister(0x19, 19) &&   // 1kHz / 20 = 50Hz.
           writeRegister(0x1B, 0x00) && // +/-250 deg/s, 131 LSB/(deg/s).
           writeRegister(0x1C, 0x00) && // +/-2g, 16384 LSB/g.
           writeRegister(0x38, 0x01);   // Data-ready status, INT wire not needed.
      const uint8_t regs[] = {0x6B,0x6C,0x1A,0x19,0x1B,0x1C,0x38};
      const uint8_t expected[] = {1,0,3,19,0,0,1};
      for (unsigned i=0; ok && i<sizeof(regs); ++i) {
        uint8_t value=0;
        ok = readRegisters(regs[i], &value, 1) && value==expected[i];
        if (!ok) Serial.printf("VERIFY FAIL reg=0x%02X value=0x%02X\n",regs[i],value);
      }
    }
    if (ok) {
      ready = true;
      Serial.printf("INIT OK addr=0x%02X; 50Hz; accel +/-2g; gyro +/-250deg/s\n",address);
      startCalibration();
      return true;
    }
    if (attempt<5) delay(150);
  }
  Serial.println("INIT FAILED. Check ACK/WHO_AM_I above; r=retry.");
  if (address) diagnoseWrites();
  return false;
}
}
void setup() {
  Serial.begin(115200);
  delay(5000);
  Wire.setSDA(SDA_PIN); Wire.setSCL(SCL_PIN);
  Wire.begin();
  // pinMode switches the Teensy mux to GPIO. Save Wire's mux/pad first.
  const uint32_t sdaMux = *portConfigRegister(SDA_PIN);
  const uint32_t sclMux = *portConfigRegister(SCL_PIN);
  const uint32_t sdaPad = *portControlRegister(SDA_PIN);
  const uint32_t sclPad = *portControlRegister(SCL_PIN);
  pinMode(18, INPUT_PULLUP);
  pinMode(19, INPUT_PULLUP);
  delay(1);
  Serial.printf("GPIO PULLUP CHECK SDA=%d SCL=%d (before restoring I2C)\n",
                digitalRead(SDA_PIN), digitalRead(SCL_PIN));
  constexpr uint32_t pullMask = IOMUXC_PAD_PKE | IOMUXC_PAD_PUE | IOMUXC_PAD_PUS(3);
  constexpr uint32_t pullUp = pullMask | IOMUXC_PAD_HYS;
  // Preserve Wire's open-drain configuration and re-enable the peripheral mux.
  *portControlRegister(SDA_PIN) = (sdaPad & ~pullMask) | pullUp;
  *portControlRegister(SCL_PIN) = (sclPad & ~pullMask) | pullUp;
  *portConfigRegister(SDA_PIN) = sdaMux;
  *portConfigRegister(SCL_PIN) = sclMux;
  Wire.setClock(100000);
  delay(250);
  Serial.println("MPU6050 standalone GYRO-CAL-v5 Teensy 4.1: VCC3.3V GND SDA18 SCL19; I2C100kHz");
  Serial.println("Boot=5000ms bus=250ms attempts=5 retry=150ms; r=retry");
  beginSensor();
}
void loop() {
  while (Serial.available()) {
    const int c=Serial.read();
    if (c=='r' || c=='R') beginSensor();
    if ((c=='c' || c=='C') && ready) startCalibration();
  }
  const auto oldCalState=calibration.state;
  calibration.tick(millis());
  uint8_t status=0, raw[14];
  const uint32_t beforeErrors=errors;
  if (ready && readRegisters(0x3A,&status,1) && (status&1) && readRegisters(0x3B,raw,14)) {
    ++samples; lastSample=millis();
    const double a[3]={signedWord(raw)/16384.0,signedWord(raw+2)/16384.0,signedWord(raw+4)/16384.0};
    const double g[3]={signedWord(raw+8)/131.0,signedWord(raw+10)/131.0,signedWord(raw+12)/131.0};
    calibration.add(lastSample,a,g);
    if (millis()-lastPrint >= 200) {
      lastPrint=millis();
      Serial.printf("A[g] %.3f %.3f %.3f | Graw[deg/s] %.3f %.3f %.3f | T=%.2fC | CAL=%s",
                    a[0],a[1],a[2],g[0],g[1],g[2],signedWord(raw+6)/340.0+36.53,calibration.name());
      if(calibration.state==GyroBias::Valid)
        Serial.printf(" | Gcorr[deg/s] %.3f %.3f %.3f",g[0]-calibration.bias[0],g[1]-calibration.bias[1],g[2]-calibration.bias[2]);
      Serial.println();
    }
  }
  if(errors!=beforeErrors) calibration.fail("I2C read error");
  if(calibration.state!=oldCalState) {
    Serial.printf("CAL %s: %s samples=%u\n",calibration.name(),calibration.reason,calibration.count);
    if(calibration.state==GyroBias::Valid)
      Serial.printf("BIAS[deg/s] X=%.5f Y=%.5f Z=%.5f (RAM only)\n",calibration.bias[0],calibration.bias[1],calibration.bias[2]);
    if(calibration.state==GyroBias::Failed) Serial.println("Keep stationary then type c; no correction applied.");
  }
  if (millis()-lastStatus>=1000) {
    lastStatus=millis();
    Serial.printf("STATUS initialized=%d samples=%lu errors=%lu age_ms=%lu CAL=%s cal_samples=%u\n",
      ready,(unsigned long)samples,(unsigned long)errors,
      (unsigned long)(samples ? millis()-lastSample : 0xffffffffUL),calibration.name(),calibration.count);
    if (ready && (!samples || millis()-lastSample>1000)) Serial.println("NO FRESH DATA; r=retry");
  }
  delay(2);
}
