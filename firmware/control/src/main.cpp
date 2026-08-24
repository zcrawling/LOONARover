#include <Arduino.h>
#include <arduino_freertos.h>

#include "loonar/control/board_pins.h"
#include "loonar/control/freertos_app.h"
#include "loonar/control/teensy_hal.h"

namespace {

[[noreturn]] void startup_failed() {
  pinMode(loonar::control::pins::kStatusLed, arduino::OUTPUT);
  for (;;) {
    digitalToggleFast(loonar::control::pins::kStatusLed);
    delay(100);
  }
}

}  // namespace

void setup() {
  lnr_teensy_board_init();
  if (!lnr_control_freertos_start(lnr_teensy_control_hal())) {
    startup_failed();
  }
  vTaskStartScheduler();
  startup_failed();
}

void loop() {}
