#include "loonar/control/control_core.h"

#include <string.h>

void lnr_control_core_init(LnrControlCore *core) {
  if (core != NULL) {
    memset(core, 0, sizeof(*core));
    core->output.state = (uint8_t)LNR_MCU_STATE_STOPPED;
    core->output.inhibit_flags = LNR_INHIBIT_HEALTH_TIMEOUT;
  }
}

void lnr_control_core_on_health(LnrControlCore *core, uint32_t received_at_ms) {
  if (core != NULL) {
    core->health_seen = true;
    core->last_health_ms = received_at_ms;
  }
}

void lnr_control_core_on_motion(LnrControlCore *core,
                                uint32_t sequence,
                                const LnrMotionCommand *command) {
  if (core != NULL && command != NULL) {
    core->requested_motion = *command;
    core->last_command_seq = sequence;
  }
}

LnrControlOutput lnr_control_core_step(LnrControlCore *core,
                                      uint32_t now_ms,
                                      int32_t board_temp_mdeg_c) {
  uint8_t inhibit_flags = 0U;
  if (core == NULL) {
    LnrControlOutput stopped = {0.0F, 0.0F, (uint8_t)LNR_MCU_STATE_STOPPED,
                                LNR_INHIBIT_HEALTH_TIMEOUT};
    return stopped;
  }

  if (!core->health_seen ||
      (uint32_t)(now_ms - core->last_health_ms) > LNR_CONTROL_HEALTH_TIMEOUT_MS) {
    inhibit_flags |= LNR_INHIBIT_HEALTH_TIMEOUT;
  }
  if (board_temp_mdeg_c >= LNR_CONTROL_OVERTEMP_MDEG_C) {
    inhibit_flags |= LNR_INHIBIT_OVERTEMP;
  }

  core->output.inhibit_flags = inhibit_flags;
  if (inhibit_flags == 0U) {
    core->output.state = (uint8_t)LNR_MCU_STATE_ACTIVE;
    core->output.linear_velocity_mps = core->requested_motion.linear_velocity_mps;
    core->output.yaw_rate_radps = core->requested_motion.yaw_rate_radps;
  } else {
    core->output.state = (uint8_t)LNR_MCU_STATE_STOPPED;
    core->output.linear_velocity_mps = 0.0F;
    core->output.yaw_rate_radps = 0.0F;
  }
  return core->output;
}

void lnr_control_core_make_status(const LnrControlCore *core,
                                  uint32_t now_ms,
                                  int32_t board_temp_mdeg_c,
                                  uint32_t rx_error_count,
                                  LnrMcuStatus *status) {
  if (core == NULL || status == NULL) {
    return;
  }
  status->uptime_ms = now_ms;
  status->last_command_seq = core->last_command_seq;
  status->board_temp_mdeg_c = board_temp_mdeg_c;
  status->state = core->output.state;
  status->inhibit_flags = core->output.inhibit_flags;
  status->applied_linear_velocity_mps = core->output.linear_velocity_mps;
  status->applied_yaw_rate_radps = core->output.yaw_rate_radps;
  status->rx_error_count = rx_error_count;
}
