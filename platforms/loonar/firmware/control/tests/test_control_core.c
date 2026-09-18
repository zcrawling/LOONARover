#include <math.h>
#include <stdint.h>

#include "loonar/control/control_core.h"
#include "loonar/control/controller_tbd.h"
#include "test_support.h"

int main(void) {
  LnrControlCore core;
  LnrControlOutput output;
  LnrMcuStatus status;
  LnrControllerTbd controller;
  LnrMotorDuty motor_duty;
  const LnrMotionCommand command = {0.7F, -0.2F};

  lnr_control_core_init(&core);
  output = lnr_control_core_step(&core, 0U, 25000);
  TEST_CHECK(output.state == (uint8_t)LNR_MCU_STATE_STOPPED);
  TEST_CHECK(output.inhibit_flags == LNR_INHIBIT_HEALTH_TIMEOUT);
  TEST_CHECK(output.linear_velocity_mps == 0.0F && output.yaw_rate_radps == 0.0F);

  lnr_control_core_on_motion(&core, 7U, &command);
  lnr_control_core_on_health(&core, 100U);
  output = lnr_control_core_step(&core, 600U, 94999);
  TEST_CHECK(output.state == (uint8_t)LNR_MCU_STATE_ACTIVE);
  TEST_CHECK(output.inhibit_flags == 0U);
  TEST_CHECK(fabsf(output.linear_velocity_mps - 0.7F) < 0.0001F);
  TEST_CHECK(fabsf(output.yaw_rate_radps + 0.2F) < 0.0001F);

  output = lnr_control_core_step(&core, 601U, 94999);
  TEST_CHECK(output.inhibit_flags == LNR_INHIBIT_HEALTH_TIMEOUT);
  TEST_CHECK(output.linear_velocity_mps == 0.0F);

  lnr_control_core_on_health(&core, 700U);
  output = lnr_control_core_step(&core, 700U, LNR_CONTROL_OVERTEMP_MDEG_C);
  TEST_CHECK(output.inhibit_flags == LNR_INHIBIT_OVERTEMP);
  TEST_CHECK(output.linear_velocity_mps == 0.0F);

  output = lnr_control_core_step(&core, 1201U, LNR_CONTROL_OVERTEMP_MDEG_C);
  TEST_CHECK(output.inhibit_flags ==
             (uint8_t)(LNR_INHIBIT_HEALTH_TIMEOUT | LNR_INHIBIT_OVERTEMP));

  lnr_control_core_on_health(&core, 1300U);
  output = lnr_control_core_step(&core, 1300U, 94999);
  TEST_CHECK(output.inhibit_flags == 0U);
  TEST_CHECK(fabsf(output.linear_velocity_mps - 0.7F) < 0.0001F);

  lnr_control_core_make_status(&core, 1300U, 42000, 9U, &status);
  TEST_CHECK(status.uptime_ms == 1300U);
  TEST_CHECK(status.last_command_seq == 7U);
  TEST_CHECK(status.board_temp_mdeg_c == 42000);
  TEST_CHECK(status.rx_error_count == 9U);
  TEST_CHECK(status.state == (uint8_t)LNR_MCU_STATE_ACTIVE);

  lnr_controller_tbd_init(&controller);
  motor_duty = lnr_controller_tbd_step(&controller, 0.7F, -0.2F);
  TEST_CHECK(motor_duty.left_duty == 0.0F);
  TEST_CHECK(motor_duty.right_duty == 0.0F);
  return 0;
}
