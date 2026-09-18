#ifndef LOONAR_CONTROL_CONTROL_CORE_H
#define LOONAR_CONTROL_CONTROL_CORE_H

#include <stdbool.h>
#include <stdint.h>

#include "loonar/wire/control_messages.h"

#ifdef __cplusplus
extern "C" {
#endif

#define LNR_CONTROL_HEALTH_TIMEOUT_MS UINT32_C(500)
#define LNR_CONTROL_OVERTEMP_MDEG_C INT32_C(95000)

typedef struct {
  float linear_velocity_mps;
  float yaw_rate_radps;
  uint8_t state;
  uint8_t inhibit_flags;
} LnrControlOutput;

typedef struct {
  bool health_seen;
  uint32_t last_health_ms;
  uint32_t last_command_seq;
  LnrMotionCommand requested_motion;
  LnrControlOutput output;
} LnrControlCore;

void lnr_control_core_init(LnrControlCore *core);
void lnr_control_core_on_health(LnrControlCore *core, uint32_t received_at_ms);
void lnr_control_core_on_motion(LnrControlCore *core,
                                uint32_t sequence,
                                const LnrMotionCommand *command);
LnrControlOutput lnr_control_core_step(LnrControlCore *core,
                                      uint32_t now_ms,
                                      int32_t board_temp_mdeg_c);
void lnr_control_core_make_status(const LnrControlCore *core,
                                  uint32_t now_ms,
                                  int32_t board_temp_mdeg_c,
                                  uint32_t rx_error_count,
                                  LnrMcuStatus *status);

#ifdef __cplusplus
}
#endif

#endif
