#ifndef LOONAR_CONTROL_TEENSY_HAL_H
#define LOONAR_CONTROL_TEENSY_HAL_H

#include "loonar/control/freertos_app.h"

#ifdef __cplusplus
extern "C" {
#endif

void lnr_teensy_board_init(void);
const LnrControlHal *lnr_teensy_control_hal(void);

#ifdef __cplusplus
}
#endif

#endif
