#ifndef LOONAR_WIRE_CONTROL_MESSAGES_H
#define LOONAR_WIRE_CONTROL_MESSAGES_H

#include <stddef.h>
#include <stdint.h>

#include "loonar/wire/packet.h"

#ifdef __cplusplus
extern "C" {
#endif

#define LNR_MPU_HEALTH_PAYLOAD_SIZE ((size_t)4)
#define LNR_MOTION_COMMAND_PAYLOAD_SIZE ((size_t)8)
#define LNR_MCU_STATUS_PAYLOAD_SIZE ((size_t)28)

#define LNR_INHIBIT_HEALTH_TIMEOUT UINT8_C(0x01)
#define LNR_INHIBIT_OVERTEMP UINT8_C(0x02)
#define LNR_INHIBIT_KNOWN_MASK UINT8_C(0x03)

typedef enum {
  LNR_MCU_STATE_STOPPED = 0,
  LNR_MCU_STATE_ACTIVE = 1
} LnrMcuState;

typedef struct {
  uint32_t uptime_ms;
} LnrMpuHealth;

typedef struct {
  float linear_velocity_mps;
  float yaw_rate_radps;
} LnrMotionCommand;

typedef struct {
  uint32_t uptime_ms;
  uint32_t last_command_seq;
  int32_t board_temp_mdeg_c;
  uint8_t state;
  uint8_t inhibit_flags;
  float applied_linear_velocity_mps;
  float applied_yaw_rate_radps;
  uint32_t rx_error_count;
} LnrMcuStatus;

LnrWireStatus lnr_encode_mpu_health_payload(const LnrMpuHealth *message,
                                            uint8_t *output,
                                            size_t output_capacity,
                                            size_t *output_size);
LnrWireStatus lnr_decode_mpu_health_payload(const uint8_t *data,
                                            size_t size,
                                            LnrMpuHealth *message);
LnrWireStatus lnr_encode_motion_command_payload(const LnrMotionCommand *message,
                                                uint8_t *output,
                                                size_t output_capacity,
                                                size_t *output_size);
LnrWireStatus lnr_decode_motion_command_payload(const uint8_t *data,
                                                size_t size,
                                                LnrMotionCommand *message);
LnrWireStatus lnr_encode_mcu_status_payload(const LnrMcuStatus *message,
                                           uint8_t *output,
                                           size_t output_capacity,
                                           size_t *output_size);
LnrWireStatus lnr_decode_mcu_status_payload(const uint8_t *data,
                                           size_t size,
                                           LnrMcuStatus *message);

#ifdef __cplusplus
}
#endif

#endif
