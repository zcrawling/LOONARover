#include "loonar/control/runtime_v2.hpp"
#include <Arduino.h>
#include <arduino_freertos.h>
void setup() {
  if (loonar::mcu::start())
    vTaskStartScheduler();
  // Pin 13 belongs to BNO085 SPI. A failed boot remains inert.
  for (;;)
    delay(1000);
}
void loop() {}
