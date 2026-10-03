#include <Arduino.h>
#include <SPI.h>
#include <Wire.h>
#include <EEPROM.h>

#include <Adafruit_LIS3MDL.h>
#include <Adafruit_MAX31865.h>
#include <Adafruit_MLX90614.h>
#include "model_params.h"
static_assert(loonar_pca::kGroundModel,
              "USB desk trial accepts ground-data models only");

namespace {
// Teensy 4.1 default hardware buses.
constexpr uint8_t PIN_MAX31865_CS = 10;
constexpr uint8_t BOARD_SPI_MOSI = 11;
constexpr uint8_t BOARD_SPI_MISO = 12;
constexpr uint8_t BOARD_SPI_SCK = 13;
constexpr uint8_t PIN_LIS3MDL_SDA = 25;
constexpr uint8_t PIN_LIS3MDL_SCL = 24;
constexpr uint8_t PIN_MLX90614_SDA = 17;
constexpr uint8_t PIN_MLX90614_SCL = 16;
constexpr uint32_t MAX31865_SPI_CLOCK_HZ = 1000000;
constexpr uint8_t MAX31865_SPI_MODE = SPI_MODE1;

constexpr uint8_t MLX90614_ADDRESS = 0x5A;
constexpr uint32_t I2C_CLOCK_HZ = 50000;
constexpr uint32_t MLX90614_I2C_CLOCK_HZ = 50000;
constexpr uint32_t POWER_STABILIZE_MS = 5000;
constexpr uint32_t BUS_STABILIZE_MS = 250;
constexpr uint32_t WIRE_STABILIZE_MS = 500;
constexpr uint32_t BEGIN_RETRY_DELAY_MS = 150;
constexpr uint8_t BEGIN_MAX_ATTEMPTS = 5;
constexpr uint32_t SAMPLE_INTERVAL_MS = 500;
constexpr uint32_t RETRY_INTERVAL_MS = 2000;
constexpr uint32_t MLX90614_COOLDOWN_MS = 10000;
constexpr uint32_t PERIODIC_REINIT_INTERVAL_MS = 5UL * 60UL * 1000UL;

constexpr float RTD_NOMINAL_OHM = 1000.0f;  // PT1000
constexpr float RTD_REFERENCE_OHM = 4630.0f;

Adafruit_LIS3MDL magnetometer;
Adafruit_MLX90614 infrared;
// Adafruit_MAX31865 v1.6.2 configures this hardware SPI device for
// 1 MHz, MSB first, SPI_MODE1. Pass &SPI explicitly so Teensy uses SPI0.
Adafruit_MAX31865 rtd(PIN_MAX31865_CS, &SPI);

bool magnetometerReady = false;
bool infraredReady = false;
bool rtdReady = false;
uint8_t magnetometerAddress = 0;
uint32_t lastSampleMs = 0;
uint32_t lastRetryMs = 0;
uint32_t mlxNextRetryMs = 0;
uint8_t mlxRuntimeFailures = 0;
uint32_t lastPeriodicReinitMs = 0;
bool nanRecoveryArmed = true;

// Match data_io.py's station features: median of valid per-row magnetic
// magnitudes, IR object temperatures and RTD temperatures. A score is emitted
// only with >=5 valid triples and >=80% valid rows in a manual station interval.
constexpr uint32_t PCA_STATION_MS = 5000;
constexpr uint8_t PCA_MAX_SAMPLES = 120;
uint32_t stationId = 1;
uint32_t stationStartMs = 0;
bool stationActive = false;
bool stationStopRequested = false;
char stationCommand[80] = {};
bool commandOverflow = false;
bool initializing = false;
uint8_t initStage = 0, initAttempt = 0;
uint32_t initDue = 0, bootId = 0, sampleSequence = 0;
uint8_t sampleValidMask = 0;
uint32_t lastDataMs = 0;
bool startPending = false;
char startRequest[21] = {}, stopRequest[21] = {};
String lastResult;
uint32_t lastResultStation = 0;
struct ReplyCache { char id[21] = {}; char operation[6] = {}; String reply; };
ReplyCache replies[8];
uint8_t replyNext = 0;
char boardId[17];
void pollStationCommand();
void completeCommand(const char*, const char*, uint32_t);
uint8_t stationCommandLength = 0;
uint8_t stationSamples = 0;
uint8_t stationValid = 0;
bool stationOverflow = false;
float stationMag[PCA_MAX_SAMPLES] = {};
float stationIr[PCA_MAX_SAMPLES] = {};
float stationRtd[PCA_MAX_SAMPLES] = {};

float medianOf(const float* values, uint8_t count) {
  float ordered[PCA_MAX_SAMPLES];
  for (uint8_t i = 0; i < count; ++i) {
    ordered[i] = values[i];
    uint8_t j = i;
    while (j > 0 && ordered[j - 1] > ordered[j]) {
      ordered[j] = ordered[j - 1];
      --j;
    }
    ordered[j] = values[i];
  }
  const uint8_t middle = count / 2;
  return (count & 1) ? ordered[middle]
                     : (ordered[middle - 1] + ordered[middle]) * 0.5f;
}

void finishStation(uint32_t endMs) {
  const bool usable = !stationOverflow && stationValid >= 5 &&
                      stationValid * 5 >= stationSamples * 4;
  float features[3] = {NAN, NAN, NAN};
  if (usable) {
    features[0] = medianOf(stationMag, stationValid);
    features[1] = medianOf(stationIr, stationValid);
    features[2] = medianOf(stationRtd, stationValid);
  }
  struct ResultPrint : Print {
    String value;
    size_t write(uint8_t c) override { value += static_cast<char>(c); return 1; }
  } result;
  result.print("PCA,");
  result.print(loonar_pca::kModelId);
  result.print(','); result.print(stationId);
  result.print(','); result.print(stationStartMs);
  result.print(','); result.print(endMs);
  result.print(','); result.print(stationSamples);
  result.print(','); result.print(stationValid);
  result.print(','); result.print(usable ? 1 : 0);
  for (float feature : features) {
    result.print(',');
    if (usable) result.print(feature, 6);
    else result.print("nan");
  }
  if (usable) {
    const loonar_pca::PcaResult score =
        loonar_pca::score(loonar_pca::kModel, features);
    result.print(','); result.print(score.q_residual, 6);
    result.print(','); result.print(score.t2_distance, 6);
    result.print(','); result.print(score.novelty, 6);
    result.print(','); result.print(score.candidate ? 1 : 0);
    result.println(loonar_pca::kDemoModel ? ",DEMO_ONLY" : ",TRAINED_MODEL");
  } else {
    result.println(",nan,nan,nan,0,INVALID_STATION");
  }
  lastResult = result.value;
  lastResultStation = stationId;
  Serial.print(lastResult);
  ++stationId;
  stationStartMs = endMs;
  stationSamples = stationValid = 0;
  stationOverflow = false;
}

void addStationSample(uint32_t now, float magNorm, float irObject,
                      float rtdTemp, bool valid) {
  if (stationSamples == 255) {
    stationOverflow = true;
    return;
  }
  ++stationSamples;
  if (!valid) return;
  if (stationValid == PCA_MAX_SAMPLES) {
    stationOverflow = true;
    return;
  }
  stationMag[stationValid] = magNorm;
  stationIr[stationValid] = irObject;
  stationRtd[stationValid] = rtdTemp;
  ++stationValid;
}

void printHexByte(uint8_t value) {
  if (value < 0x10) Serial.print('0');
  Serial.print(value, HEX);
}

void printFloatOrNan(float value, uint8_t digits) {
  if (isfinite(value)) Serial.print(value, digits);
  else Serial.print("nan");
}

void printLis3mdlLineState(const char* phase) {
  const int sda = digitalRead(PIN_LIS3MDL_SDA);
  const int scl = digitalRead(PIN_LIS3MDL_SCL);

  Serial.print("# LIS3MDL BUS STATE phase=");
  Serial.print(phase);
  Serial.print(" SDA25=");
  Serial.print(sda);
  Serial.print(" SCL24=");
  Serial.print(scl);
  Serial.print(" state=");
  if (sda == HIGH && scl == HIGH) Serial.println("IDLE_HIGH");
  else if (sda == LOW && scl == HIGH) Serial.println("SDA_STUCK_LOW");
  else if (sda == HIGH && scl == LOW) Serial.println("SCL_STUCK_LOW");
  else Serial.println("BOTH_STUCK_LOW");
}

void diagnoseLis3mdlBus(const char* reason) {
  // Capture the electrical state before any recovery or begin() call changes
  // the I2C peripheral or generates additional clocks.
  const int sda = digitalRead(PIN_LIS3MDL_SDA);
  const int scl = digitalRead(PIN_LIS3MDL_SCL);

  Serial.print("# LIS3MDL BUS DIAG reason=");
  Serial.print(reason);
  Serial.print(" SDA25=");
  Serial.print(sda);
  Serial.print(" SCL24=");
  Serial.print(scl);
  Serial.print(" state=");
  if (sda == HIGH && scl == HIGH) Serial.println("IDLE_HIGH");
  else if (sda == LOW && scl == HIGH) Serial.println("SDA_STUCK_LOW");
  else if (sda == HIGH && scl == LOW) Serial.println("SCL_STUCK_LOW");
  else Serial.println("BOTH_STUCK_LOW");

  // Only issue a real register transaction when the bus is electrically idle.
  // This is not an address-only scanner probe.
  if (sda != HIGH || scl != HIGH || magnetometerAddress == 0) return;

  constexpr uint8_t WHO_AM_I_REG = 0x0F;
  Wire2.beginTransmission(magnetometerAddress);
  Wire2.write(WHO_AM_I_REG);
  const uint8_t txError = Wire2.endTransmission(false);
  uint8_t rxCount = 0;
  int whoAmI = -1;
  if (txError == 0) {
    rxCount = Wire2.requestFrom(magnetometerAddress, static_cast<uint8_t>(1),
                                static_cast<uint8_t>(true));
    if (rxCount == 1 && Wire2.available()) whoAmI = Wire2.read();
  }

  Serial.print("# LIS3MDL REG DIAG address=0x");
  printHexByte(magnetometerAddress);
  Serial.print(" tx_error=");
  Serial.print(txError);
  Serial.print(" rx_count=");
  Serial.print(rxCount);
  Serial.print(" who_am_i=");
  if (whoAmI < 0) Serial.println("none");
  else {
    Serial.print("0x");
    printHexByte(static_cast<uint8_t>(whoAmI));
    Serial.println(whoAmI == 0x3D ? " OK" : " INVALID");
  }
}

bool beginMagnetometer() {
  printLis3mdlLineState("before_sensor_begin");
  if (magnetometer.begin_I2C(0x1C, &Wire2)) {
    magnetometerAddress = 0x1C;
  } else if (magnetometer.begin_I2C(0x1E, &Wire2)) {
    magnetometerAddress = 0x1E;
  } else {
    Wire2.setClock(I2C_CLOCK_HZ);
    // Preserve the last known address until diagnostics are complete.
    diagnoseLis3mdlBus("begin_failed");
    Serial.println("# LIS3MDL FAIL: no response at 0x1C or 0x1E");
    return false;
  }

  printLis3mdlLineState("after_sensor_begin");
  Wire2.setClock(I2C_CLOCK_HZ);
  magnetometer.setPerformanceMode(LIS3MDL_MEDIUMMODE);
  magnetometer.setOperationMode(LIS3MDL_CONTINUOUSMODE);
  magnetometer.setDataRate(LIS3MDL_DATARATE_20_HZ);
  magnetometer.setRange(LIS3MDL_RANGE_4_GAUSS);
  printLis3mdlLineState("after_sensor_config");
  Serial.print("# LIS3MDL READY at 0x");
  printHexByte(magnetometerAddress);
  Serial.println();
  return true;
}

bool beginInfrared() {
  // No scanner or address-only pre-probe. begin() performs library detection,
  // then real temperature registers are read to verify communication.
  if (!infrared.begin(MLX90614_ADDRESS, &Wire1)) {
    Wire1.setClock(MLX90614_I2C_CLOCK_HZ);
    Serial.println("# MLX90614 FAIL: library initialization failed");
    return false;
  }

  // Adafruit_I2CDevice::begin() calls Wire1.begin(), restoring 100 kHz.
  Wire1.setClock(MLX90614_I2C_CLOCK_HZ);
  const float ambient = infrared.readAmbientTempC();
  const float object = infrared.readObjectTempC();
  if (!isfinite(ambient) || !isfinite(object) || ambient <= -70.0f ||
      ambient >= 390.0f || object <= -70.0f || object >= 390.0f) {
    Serial.println("# MLX90614 FAIL: temperature register verification failed");
    return false;
  }
  Serial.println("# MLX90614 READY at 0x5A; registers verified");
  return true;
}

void recoverMlxBus() {
  Serial.print("# MLX90614 Wire1 recovery begin SDA=");
  Serial.print(digitalRead(PIN_MLX90614_SDA));
  Serial.print(" SCL=");
  Serial.println(digitalRead(PIN_MLX90614_SCL));

  Wire1.end();
  pinMode(PIN_MLX90614_SDA, INPUT_PULLUP);
  pinMode(PIN_MLX90614_SCL, INPUT_PULLUP);
  delayMicroseconds(10);

  uint8_t pulses = 0;
  while (digitalRead(PIN_MLX90614_SDA) == LOW && pulses < 9) {
    pinMode(PIN_MLX90614_SCL, OUTPUT);
    digitalWrite(PIN_MLX90614_SCL, LOW);
    delayMicroseconds(5);
    pinMode(PIN_MLX90614_SCL, INPUT_PULLUP);
    delayMicroseconds(5);
    ++pulses;
  }

  // STOP condition: SDA low, release SCL, then release SDA. Neither line is
  // ever driven HIGH, preserving open-drain operation.
  pinMode(PIN_MLX90614_SDA, OUTPUT);
  digitalWrite(PIN_MLX90614_SDA, LOW);
  delayMicroseconds(5);
  pinMode(PIN_MLX90614_SCL, INPUT_PULLUP);
  delayMicroseconds(5);
  pinMode(PIN_MLX90614_SDA, INPUT_PULLUP);
  delayMicroseconds(5);

  Wire1.setSDA(PIN_MLX90614_SDA);
  Wire1.setSCL(PIN_MLX90614_SCL);
  Wire1.begin();
  Wire1.setClock(MLX90614_I2C_CLOCK_HZ);
  delay(WIRE_STABILIZE_MS);

  Serial.print("# MLX90614 Wire1 recovery end pulses=");
  Serial.print(pulses);
  Serial.print(" SDA=");
  Serial.print(digitalRead(PIN_MLX90614_SDA));
  Serial.print(" SCL=");
  Serial.println(digitalRead(PIN_MLX90614_SCL));
}

bool beginRtd() {
  if (!rtd.begin(MAX31865_3WIRE)) {
    Serial.println("# MAX31865 FAIL: begin failed");
    return false;
  }

  constexpr uint16_t TEST_LOW = 0x2468;
  constexpr uint16_t TEST_HIGH = 0x5A5A;
  rtd.setThresholds(TEST_LOW, TEST_HIGH);
  const uint16_t lowReadback = rtd.getLowerThreshold();
  const uint16_t highReadback = rtd.getUpperThreshold();
  rtd.setThresholds(0x0000, 0xFFFF);

  if (lowReadback != TEST_LOW || highReadback != TEST_HIGH) {
    Serial.print("# MAX31865 FAIL: SPI readback LOW=0x");
    Serial.print(lowReadback, HEX);
    Serial.print(" HIGH=0x");
    Serial.println(highReadback, HEX);
    return false;
  }
  Serial.println("# MAX31865 READY (3-wire PT1000)");
  return true;
}

void printCsvHeader();

// One sensor begin per loop iteration; retry and bus delays never block USB polling.
void reinitializeSensors(const char* reason) {
  Serial.print("# INIT "); Serial.println(reason);
  initializing = true;
  initStage = initAttempt = 0;
  initDue = millis();
}

void serviceInitialization() {
  if (!initializing || static_cast<int32_t>(millis() - initDue) < 0) return;
  if (initStage == 0) {
    pinMode(PIN_MAX31865_CS, OUTPUT); digitalWrite(PIN_MAX31865_CS, HIGH);
    SPI.begin();
    Wire2.setSDA(PIN_LIS3MDL_SDA); Wire2.setSCL(PIN_LIS3MDL_SCL);
    Wire2.begin(); Wire2.setClock(I2C_CLOCK_HZ);
    Wire1.setSDA(PIN_MLX90614_SDA); Wire1.setSCL(PIN_MLX90614_SCL);
    Wire1.begin(); Wire1.setClock(MLX90614_I2C_CLOCK_HZ);
    magnetometerReady = infraredReady = rtdReady = false;
    sampleValidMask = 0;
    initStage = 1; initDue = millis() + WIRE_STABILIZE_MS;
    return;
  }
  bool ok = initStage == 1 ? beginMagnetometer() :
            initStage == 2 ? beginInfrared() : beginRtd();
  if (initStage == 1) magnetometerReady = ok;
  if (initStage == 2) infraredReady = ok;
  if (initStage == 3) rtdReady = ok;
  if (ok || ++initAttempt >= BEGIN_MAX_ATTEMPTS) { ++initStage; initAttempt = 0; }
  initDue = millis() + BEGIN_RETRY_DELAY_MS;
  if (initStage <= 3) return;
  initializing = false;
  mlxRuntimeFailures = 0;
  lastRetryMs = lastSampleMs = lastPeriodicReinitMs = millis();
  mlxNextRetryMs = infraredReady ? 0 : millis() + MLX90614_COOLDOWN_MS;
  printCsvHeader();
  if (startPending) {
    startPending = false; stationActive = true; stationStartMs = millis();
    completeCommand(startRequest, "START", stationId);
  }
}

const char* measurementState() {
  if (startPending) return "STARTING";
  if (stationStopRequested) return "STOPPING";
  if (initializing) return "INITIALIZING";
  return stationActive ? "MEASURING" : "IDLE";
}
void completeCommand(const char* id, const char* op, uint32_t station) {
  if (!id[0]) { Serial.print("CTRL,"); Serial.print(op); Serial.print(','); Serial.println(station); return; }
  String line = String("DONE,") + id + "," + op + "," + station;
  for (auto &r : replies) if (!strcmp(r.id, id)) r.reply = line;
  Serial.println(line);
}
void executeCommand(char* line) {
  if (!strcmp(line, "HELLO")) {
    Serial.print("HELLO,1,PAYLOAD,"); Serial.print(boardId);
    Serial.print(",payload-1,"); Serial.println(bootId); return;
  }
  if (!strncmp(line, "STATUS,", 7)) {
    const char* id = line + 7;
    if (!*id || strlen(id) > 20 || strspn(id, "0123456789") != strlen(id)) return;
    Serial.print("HEALTH,1,"); Serial.print(id); Serial.print(','); Serial.print(boardId);
    Serial.print(','); Serial.print(bootId); Serial.print(','); Serial.print(measurementState());
    Serial.print(','); Serial.print(stationId); Serial.print(','); Serial.print(millis());
    Serial.print(','); Serial.print(sampleSequence ? sampleValidMask :
      (magnetometerReady | (infraredReady << 1) | (rtdReady << 2)));
    Serial.print(','); Serial.print(sampleSequence ? millis() - lastDataMs : UINT32_MAX);
    Serial.print(','); Serial.print(sampleSequence); Serial.println(",payload-1"); return;
  }
  char* id = nullptr; char* op = line;
  if (!strncmp(line, "CMD,", 4)) {
    id = line + 4; op = strchr(id, ',');
    if (!op) return;
    *op++ = 0;
    if (!*id || strlen(id) > 20 || strspn(id, "0123456789") != strlen(id)) return;
    if (strcmp(op,"START") && strcmp(op,"STOP") && strcmp(op,"RESULT")) {
      Serial.print("ERROR,"); Serial.print(id); Serial.println(",unknown_command"); return;
    }
    for (auto &r : replies) if (!strcmp(r.id, id)) {
      if (strcmp(r.operation, op)) { Serial.print("ERROR,"); Serial.print(id); Serial.println(",request_conflict"); }
      else Serial.println(r.reply);
      return;
    }
    if (!strcmp(op,"RESULT")) {
      if (lastResult.length()) {
        Serial.print(lastResult); completeCommand(id,"RESULT",lastResultStation);
      } else { Serial.print("ERROR,"); Serial.print(id); Serial.println(",no_result"); }
      return;
    }
    auto &r = replies[replyNext++ % 8];
    strncpy(r.id,id,sizeof(r.id)); strncpy(r.operation,op,sizeof(r.operation));
    r.reply = String("ACK,") + id + "," + op;
  }
  auto error = [&](const char* why) {
    String reply = id ? String("ERROR,") + id + "," + why : String("CTRL,ERROR,") + why;
    if (id) for (auto &r : replies) if (!strcmp(r.id,id)) r.reply = reply;
    Serial.println(reply);
  };
  if (!strcmp(op,"START")) {
    if (stationActive || startPending || initializing) { error("busy"); return; }
    strncpy(startRequest,id ? id : "",sizeof(startRequest));
    stationSamples = stationValid = 0; stationOverflow = false; stationStopRequested = false;
    startPending = true;
    if (id) { Serial.print("ACK,"); Serial.print(id); Serial.println(",START"); }
    reinitializeSensors("station_start");
  } else if (!strcmp(op,"STOP")) {
    if (id) { Serial.print("ACK,"); Serial.print(id); Serial.println(",STOP"); }
    if (startPending) {
      startPending = initializing = false;
      if (startRequest[0]) {
        String reply = String("ERROR,") + startRequest + ",cancelled";
        for (auto &r : replies) if (!strcmp(r.id,startRequest)) r.reply = reply;
        Serial.println(reply);
      }
      completeCommand(id ? id : "","STOP",0); return;
    }
    if (!stationActive) { completeCommand(id ? id : "","STOP",0); return; }
    if (stationStopRequested) { error("stop_pending"); return; }
    strncpy(stopRequest,id ? id : "",sizeof(stopRequest)); stationStopRequested = true;
    // Stop must remain possible even while recovering a failed sensor.
    initializing = false;
  } else error("unknown_command");
}
void pollStationCommand() {
  unsigned budget = 256;
  while (budget-- && Serial.available() > 0) {
    const char ch = Serial.read();
    if (ch == '\r') continue;
    if (ch == '\n') {
      stationCommand[stationCommandLength] = 0;
      if (!commandOverflow && stationCommandLength) executeCommand(stationCommand);
      else if (commandOverflow) Serial.println("CTRL,ERROR,command_too_long");
      stationCommandLength = 0; commandOverflow = false;
    } else if (!commandOverflow && stationCommandLength < sizeof(stationCommand)-1)
      stationCommand[stationCommandLength++] = ch;
    else commandOverflow = true; // discard the entire line, never execute its suffix
  }
}

void retryMissingSensors(uint32_t now) {
  if (now - lastRetryMs < RETRY_INTERVAL_MS) return;
  lastRetryMs = now;
  if (!magnetometerReady)
    magnetometerReady = beginMagnetometer();
  if (!rtdReady) rtdReady = beginRtd();
}

bool retryInfrared(uint32_t now) {
  if (infraredReady || static_cast<int32_t>(now - mlxNextRetryMs) < 0)
    return false;

  Serial.print("# MLX90614 runtime begin attempt ");
  Serial.print(mlxRuntimeFailures + 1);
  Serial.println("/5");
  infraredReady = beginInfrared();
  if (infraredReady) {
    mlxRuntimeFailures = 0;
    return true;
  }

  ++mlxRuntimeFailures;
  if (mlxRuntimeFailures >= BEGIN_MAX_ATTEMPTS) {
    recoverMlxBus();
    mlxRuntimeFailures = 0;
    mlxNextRetryMs = millis() + MLX90614_COOLDOWN_MS;
    Serial.println("# MLX90614 cooldown 10s after 5 failed attempts");
  } else {
    mlxNextRetryMs = now + RETRY_INTERVAL_MS;
  }
  return true;
}

void printCsvHeader() {
  Serial.println(
      "time_ms,mag_x_uT,mag_y_uT,mag_z_uT,mag_norm_uT,"
      "ir_ambient_C,ir_object_C,rtd_raw,rtd_ohm,rtd_C,"
      "mag_valid,ir_valid,rtd_valid,rtd_fault");
}
}  // namespace

void setup() {
  Serial.begin(115200);
  snprintf(boardId,sizeof(boardId),"%08lx%08lx",(unsigned long)HW_OCOTP_CFG0,(unsigned long)HW_OCOTP_CFG1);
  uint32_t magic = 0; const int base = EEPROM.length()-8;
  EEPROM.get(base,magic); EEPROM.get(base+4,bootId);
  bootId = magic == 0x504C4431 ? bootId + 1 : 1;
  if (!bootId) bootId = 1;
  EEPROM.put(base,(uint32_t)0x504C4431); EEPROM.put(base+4,bootId);
  reinitializeSensors("boot");
  initDue = millis() + POWER_STABILIZE_MS;
}

void loop() {
  pollStationCommand();
  serviceInitialization();
  if (initializing || !stationActive) return;
  const uint32_t now = millis();
  if (!stationStopRequested && now - lastPeriodicReinitMs >= PERIODIC_REINIT_INTERVAL_MS) {
    reinitializeSensors("periodic_5min");
    return;
  }
  // Do not read other sensors while MLX90614 initialization is running.
  if (!stationStopRequested) {
    if (retryInfrared(now)) return;
    retryMissingSensors(now);
  }
  if (now - lastSampleMs < SAMPLE_INTERVAL_MS) return;
  lastSampleMs = now;

  float magX = NAN, magY = NAN, magZ = NAN, magNorm = NAN;
  float irAmbientC = NAN, irObjectC = NAN;
  uint16_t rtdRaw = 0;
  float rtdOhm = NAN, rtdC = NAN;
  uint8_t rtdFault = 0;
  bool magValid = false, irValid = false, rtdValid = false;

  if (magnetometerReady) {
    magValid = magnetometer.readMagneticField(magX, magY, magZ);
    if (magValid) {
      magNorm = sqrtf(magX * magX + magY * magY + magZ * magZ);
    } else {
      diagnoseLis3mdlBus("read_failed");
      Serial.println("# LIS3MDL read failed; scheduling reinitialization");
      magnetometerReady = false;
    }
  }

  if (infraredReady) {
    irAmbientC = infrared.readAmbientTempC();
    irObjectC = infrared.readObjectTempC();
    irValid = isfinite(irAmbientC) && isfinite(irObjectC) &&
              irAmbientC > -70.0f && irAmbientC < 390.0f &&
              irObjectC > -70.0f && irObjectC < 390.0f;
    if (!irValid) {
      Serial.println("# MLX90614 read failed; scheduling isolated retry");
      infraredReady = false;
      mlxRuntimeFailures = 0;
      mlxNextRetryMs = now + RETRY_INTERVAL_MS;
    }
  }

  if (rtdReady) {
    rtdRaw = rtd.readRTD();
    rtdFault = rtd.readFault();
    rtdOhm = (static_cast<float>(rtdRaw) / 32768.0f) * RTD_REFERENCE_OHM;
    rtdC = rtd.calculateTemperature(rtdRaw, RTD_NOMINAL_OHM,
                                    RTD_REFERENCE_OHM);
    rtdValid = rtdFault == 0 && rtdRaw > 0 && rtdRaw < 32767 &&
               isfinite(rtdC) && rtdC >= -100.0f && rtdC <= 500.0f;
    if (rtdFault != 0) rtd.clearFault();
  }

  Serial.print(now);
  Serial.print(','); printFloatOrNan(magX, 3);
  Serial.print(','); printFloatOrNan(magY, 3);
  Serial.print(','); printFloatOrNan(magZ, 3);
  Serial.print(','); printFloatOrNan(magNorm, 3);
  Serial.print(','); printFloatOrNan(irAmbientC, 2);
  Serial.print(','); printFloatOrNan(irObjectC, 2);
  Serial.print(','); Serial.print(rtdRaw);
  Serial.print(','); printFloatOrNan(rtdOhm, 2);
  Serial.print(','); printFloatOrNan(rtdC, 2);
  Serial.print(','); Serial.print(magValid ? 1 : 0);
  Serial.print(','); Serial.print(irValid ? 1 : 0);
  Serial.print(','); Serial.print(rtdValid ? 1 : 0);
  Serial.print(",0x"); printHexByte(rtdFault);
  Serial.println();

  ++sampleSequence;
  lastDataMs = now;
  sampleValidMask = magValid | (irValid << 1) | ((rtdValid && rtdFault == 0) << 2);
  Serial.print("SAMPLE_META,"); Serial.print(sampleSequence); Serial.print(','); Serial.println(now);
  addStationSample(now, magNorm, irObjectC, rtdC,
                   magValid && irValid && rtdValid && rtdFault == 0 &&
                   isfinite(magNorm) && isfinite(irObjectC) && isfinite(rtdC));

  if (stationStopRequested && now - stationStartMs >= PCA_STATION_MS) {
    const uint32_t completedStation = stationId;
    finishStation(now);
    stationActive = false;
    stationStopRequested = false;
    completeCommand(stopRequest, "STOP", completedStation);
    return;
  }

  const bool sampleHasNan = !isfinite(magX) || !isfinite(magY) ||
                            !isfinite(magZ) || !isfinite(magNorm) ||
                            !isfinite(irAmbientC) || !isfinite(irObjectC) ||
                            !isfinite(rtdOhm) || !isfinite(rtdC);
  if (sampleHasNan && nanRecoveryArmed) {
    nanRecoveryArmed = false;
    reinitializeSensors("nan_detected");
  } else if (!sampleHasNan) {
    nanRecoveryArmed = true;
  }
}
