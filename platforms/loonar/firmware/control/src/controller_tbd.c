#include "loonar/control/controller_tbd.h"

#include <stddef.h>

void lnr_controller_tbd_init(LnrControllerTbd *controller) {
  if (controller != NULL) {
    controller->reserved = 0U;
  }
}

LnrMotorDuty lnr_controller_tbd_step(LnrControllerTbd *controller,
                                     float linear_velocity_mps,
                                     float yaw_rate_radps) {
  const LnrMotorDuty stopped = {0.0F, 0.0F};
  (void)controller;
  (void)linear_velocity_mps;
  (void)yaw_rate_radps;
  return stopped;
}
