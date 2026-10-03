#include <Arduino.h>
#include <cmath>
#include <SPI.h>
#include <Adafruit_BNO08x.h>
#include "test_compat.h"

void bno_diag_dump();
#ifdef BNO_TEENSY_UART
void bno_uart_dump();
static uint8_t uartRxExtra[8192];
#endif
// // Buffered trace from the generated diagnostic driver.

namespace {
#ifdef BNO_MKR_SOFT_SPI
constexpr uint8_t CS = 3, MOSI_PIN = 4, MISO_PIN = 11, SCK_PIN = 12;
constexpr uint8_t RST = 5, INT_PIN = 2;
#else
constexpr uint8_t CS = 10, MOSI_PIN = 11, MISO_PIN = 12, SCK_PIN = 13;
constexpr uint8_t RST = 8, INT_PIN = 9;
#endif
Adafruit_BNO08x bno(RST);
bool opened = false, ready = false;
sh2_SensorValue_t sensorEvent{}; // Persistent target for callbacks during report setup.
float gx=NAN, gy=NAN, gz=NAN, ax=NAN, ay=NAN, az=NAN;
uint32_t events = 0, gyro = 0, accel = 0, rotation = 0;
uint32_t lastEvent = 0, lastStatus = 0, lastPrint = 0;

void pins() {
  testPrintf("pins: INT=%d RST=%d CS=%d (logic levels, not a wiring test)\n",
                digitalRead(INT_PIN), digitalRead(RST), digitalRead(CS));
}

bool initialize() {
  ready = false;
  gx=gy=gz=ax=ay=az=NAN;
  for (unsigned attempt = 1; attempt <= 5; ++attempt) {
    // Pinned BusIO hardware SPI begin always succeeds. This program is the
    // only SH2 owner; even failed product-ID queries occupy its single slot.
    if (opened) sh2_close();
    opened = true;
    testPrintf("BEGIN %u/5 t=%lu ms\n", attempt, (unsigned long)millis());
    pins();
    const uint32_t start = millis();
#ifdef BNO_TEENSY_UART
    const bool found = bno.begin_UART(&Serial1);
#else
    const bool found = bno.begin_SPI(CS, INT_PIN, &SPI);
#endif
    const uint32_t elapsed = millis() - start;
    if (found) {
      bno.wasReset();
      // enableReport services incoming events too: install a live decode target
      // before enabling the first report, avoiding the library's null target.
      bno.getSensorEvent(&sensorEvent);
      // Start with moderate 50 Hz gyro/accel and 20 Hz rotation reports.
      const bool g = bno.enableReport(SH2_GYROSCOPE_CALIBRATED, 20000);
      const bool a = bno.enableReport(SH2_ACCELEROMETER, 20000);
      const bool q = bno.enableReport(SH2_ROTATION_VECTOR, 50000);
      bno_diag_dump();
      testPrintf("begin=OK duration=%lums\n", (unsigned long)elapsed);
      testPrintf("reports: gyro=%d accel=%d rotation=%d\n", g, a, q);
      ready = g && a && q;
      if (ready) {
        lastEvent = millis();
        Serial.println("INIT OK. Waiting for actual sensor events.");
        return true;
      }
    }
    if (!found) { bno_diag_dump(); testPrintf("begin=FAIL duration=%lums\n", (unsigned long)elapsed); }
    pins();
    if (attempt < 5) delay(150);
  }
  // Retain no occupied SHTP slot after the final failure.
  sh2_close();
  opened = false;
  Serial.println("INIT FAILED after 5 attempts. Check power/SPI mode/wiring; type r to retry.");
  return false;
}
}

void setup() {
  // Assert reset before USB/SPI setup. Reset does not discharge the supply.
  pinMode(RST, OUTPUT);
  digitalWrite(RST, LOW);
  delay(100);
  pinMode(INT_PIN, INPUT_PULLUP);
  pinMode(CS, OUTPUT);
  digitalWrite(CS, HIGH);
  digitalWrite(RST, HIGH);
  delay(200);
  Serial.begin(115200);
  #if defined(BNO_TEENSY_UART)
  Serial1.setRX(0); Serial1.setTX(1);
  Serial1.addMemoryForRead(uartRxExtra, sizeof(uartRxExtra));
  Serial1.begin(3000000);
  const uint32_t usbStart=millis();
  while (!Serial && millis()-usbStart<3000) delay(1);
  #elif defined(BNO_MKR_SOFT_SPI)
  BnoSoftSPI bus;
  bus.begin();
  const uint32_t usbStart = millis();
  while (!Serial && millis() - usbStart < 3000) delay(1);
  #else
  SPI.setMOSI(MOSI_PIN);
  SPI.setMISO(MISO_PIN);
  SPI.setSCK(SCK_PIN);
  SPI.begin();
  #endif
  delay(250);
  #if defined(BNO_TEENSY_UART)
  Serial.println("BNO085 UART-SHTP Teensy 4.1: SDA->RX0 SCL<-TX1 RST8 INT9; PS0=LOW PS1=HIGH");
  #elif defined(BNO_MKR_SOFT_SPI)
  Serial.println("BNO085 MKR ZERO software SPI: CS3 DI4 SDA11 SCL12 RST5 INT2");
  Serial.println("INT2 level polling; IRQ edge trace unavailable on this core pin.");
  #else
  testPrintf("BNO085 standalone SPI test FIX-v5: Teensy 4.1; SPI0 CS%d DI%d SDA%d SCL%d RST%d INT%d\n",
                CS, MOSI_PIN, MISO_PIN, SCK_PIN, RST, INT_PIN);
  #endif
  Serial.println("Reset LOW=100ms, after release=200ms (setup and each begin); bus wait=250ms.");
  Serial.println("Extra boot wait=0ms; attempts=5, retry wait=150ms. r=retry");
  #if defined(BNO_TEENSY_UART)
  Serial.println("UART=3000000 8N1; startup=2000ms; nonblocking receive; r=retry");
  #elif defined(BNO_MKR_SOFT_SPI)
  Serial.println("Software SPI mode3 (below 500kHz); startup=2000ms; INT level check.");
  #else
  Serial.println("SPI=1MHz mode3; startup=2000ms; INT level check; edges are diagnostic only.");
  #endif
  initialize();
}

void loop() {
  while (Serial.available()) {
    const int c = Serial.read();
    if (c == 'r' || c == 'R') initialize();
  }
  if (ready && bno.wasReset()) {
    Serial.println("SENSOR RESET observed; reinitializing (up to 5 attempts).");
    initialize();
  }
  auto &v = sensorEvent;
  if (ready && bno.getSensorEvent(&v)) {
    ++events;
    lastEvent = millis();
    if (v.sensorId == SH2_GYROSCOPE_CALIBRATED) {
      ++gyro; gx=v.un.gyroscope.x; gy=v.un.gyroscope.y; gz=v.un.gyroscope.z;
    }
    if (v.sensorId == SH2_ACCELEROMETER) {
      ++accel; ax=v.un.accelerometer.x; ay=v.un.accelerometer.y; az=v.un.accelerometer.z;
    }
    if (v.sensorId == SH2_ROTATION_VECTOR) ++rotation;
  }
  if (ready && millis() - lastPrint >= 200) {
    lastPrint = millis();
    testPrintf("G[rad/s] %.3f %.3f %.3f | A[m/s2] %.2f %.2f %.2f | age=%lums\n",
                  gx,gy,gz,ax,ay,az,(unsigned long)(millis()-lastEvent));
  }
  if (millis() - lastStatus >= 1000) {
    lastStatus = millis();
    testPrintf("STATUS ready=%d total=%lu gyro=%lu accel=%lu quat=%lu age_ms=%lu\n",
                  ready, (unsigned long)events, (unsigned long)gyro,
                  (unsigned long)accel, (unsigned long)rotation,
                  (unsigned long)(events ? millis() - lastEvent : 0xffffffffUL));
    if (!ready) pins();
#ifdef BNO_TEENSY_UART
    bno_uart_dump();
#endif
    if (ready && millis() - lastEvent > 3000)
      Serial.println("NO EVENTS for >3s; type r to reinitialize.");
  }
  delay(1);
}
