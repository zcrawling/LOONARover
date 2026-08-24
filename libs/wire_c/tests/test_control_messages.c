#include <math.h>
#include <stdint.h>
#include <string.h>

#include "loonar/wire/control_messages.h"
#include "test_support.h"

int main(void) {
  uint8_t bytes[LNR_WIRE_MAX_PAYLOAD_SIZE] = {0U};
  size_t size = 0U;
  LnrMpuHealth health = {UINT32_C(0x12345678)};
  LnrMpuHealth decoded_health;
  LnrMotionCommand command = {0.5F, -0.25F};
  LnrMotionCommand decoded_command;
  LnrMcuStatus status = {1000U, 7U, 42000, (uint8_t)LNR_MCU_STATE_ACTIVE, 0U,
                         0.5F, -0.25F, 3U};
  LnrMcuStatus decoded_status;

  TEST_CHECK(lnr_encode_mpu_health_payload(&health, bytes, sizeof(bytes), &size) ==
             LNR_WIRE_STATUS_OK);
  TEST_CHECK(size == LNR_MPU_HEALTH_PAYLOAD_SIZE);
  TEST_CHECK(memcmp(bytes, "\x78\x56\x34\x12", 4U) == 0);
  TEST_CHECK(lnr_decode_mpu_health_payload(bytes, size, &decoded_health) ==
             LNR_WIRE_STATUS_OK);
  TEST_CHECK(decoded_health.uptime_ms == health.uptime_ms);

  TEST_CHECK(lnr_encode_motion_command_payload(&command, bytes, sizeof(bytes), &size) ==
             LNR_WIRE_STATUS_OK);
  TEST_CHECK(size == LNR_MOTION_COMMAND_PAYLOAD_SIZE);
  TEST_CHECK(lnr_decode_motion_command_payload(bytes, size, &decoded_command) ==
             LNR_WIRE_STATUS_OK);
  TEST_CHECK(fabsf(decoded_command.linear_velocity_mps - 0.5F) < 0.0001F);
  TEST_CHECK(fabsf(decoded_command.yaw_rate_radps + 0.25F) < 0.0001F);
  command.linear_velocity_mps = NAN;
  TEST_CHECK(lnr_encode_motion_command_payload(&command, bytes, sizeof(bytes), &size) ==
             LNR_WIRE_STATUS_BAD_PAYLOAD);

  TEST_CHECK(lnr_encode_mcu_status_payload(&status, bytes, sizeof(bytes), &size) ==
             LNR_WIRE_STATUS_OK);
  TEST_CHECK(size == LNR_MCU_STATUS_PAYLOAD_SIZE);
  TEST_CHECK(lnr_decode_mcu_status_payload(bytes, size, &decoded_status) ==
             LNR_WIRE_STATUS_OK);
  TEST_CHECK(decoded_status.last_command_seq == status.last_command_seq);
  TEST_CHECK(decoded_status.board_temp_mdeg_c == status.board_temp_mdeg_c);
  TEST_CHECK(decoded_status.state == (uint8_t)LNR_MCU_STATE_ACTIVE);
  bytes[14] = 1U;
  TEST_CHECK(lnr_decode_mcu_status_payload(bytes, size, &decoded_status) ==
             LNR_WIRE_STATUS_BAD_PAYLOAD);
  return 0;
}
