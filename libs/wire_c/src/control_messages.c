#include "loonar/wire/control_messages.h"

#include <math.h>

#include "loonar/wire/byte_codec.h"

static bool motion_is_valid(const LnrMotionCommand *message) {
  return message != NULL && isfinite(message->linear_velocity_mps) &&
         isfinite(message->yaw_rate_radps);
}

LnrWireStatus lnr_encode_mpu_health_payload(const LnrMpuHealth *message,
                                            uint8_t *output,
                                            size_t output_capacity,
                                            size_t *output_size) {
  LnrWriter writer;
  if (message == NULL || output == NULL || output_size == NULL) {
    return LNR_WIRE_STATUS_INVALID_ARGUMENT;
  }
  *output_size = 0U;
  if (output_capacity < LNR_MPU_HEALTH_PAYLOAD_SIZE) {
    return LNR_WIRE_STATUS_BUFFER_TOO_SMALL;
  }
  lnr_writer_init(&writer, output, output_capacity);
  if (!lnr_write_u32_le(&writer, message->uptime_ms)) {
    return LNR_WIRE_STATUS_BUFFER_TOO_SMALL;
  }
  *output_size = lnr_writer_size(&writer);
  return LNR_WIRE_STATUS_OK;
}

LnrWireStatus lnr_decode_mpu_health_payload(const uint8_t *data,
                                            size_t size,
                                            LnrMpuHealth *message) {
  LnrReader reader;
  if (data == NULL || message == NULL) {
    return LNR_WIRE_STATUS_INVALID_ARGUMENT;
  }
  if (size != LNR_MPU_HEALTH_PAYLOAD_SIZE) {
    return LNR_WIRE_STATUS_BAD_LENGTH;
  }
  lnr_reader_init(&reader, data, size);
  return lnr_read_u32_le(&reader, &message->uptime_ms) ? LNR_WIRE_STATUS_OK
                                                       : LNR_WIRE_STATUS_BAD_LENGTH;
}

LnrWireStatus lnr_encode_motion_command_payload(const LnrMotionCommand *message,
                                                uint8_t *output,
                                                size_t output_capacity,
                                                size_t *output_size) {
  LnrWriter writer;
  if (message == NULL || output == NULL || output_size == NULL) {
    return LNR_WIRE_STATUS_INVALID_ARGUMENT;
  }
  *output_size = 0U;
  if (!motion_is_valid(message)) {
    return LNR_WIRE_STATUS_BAD_PAYLOAD;
  }
  if (output_capacity < LNR_MOTION_COMMAND_PAYLOAD_SIZE) {
    return LNR_WIRE_STATUS_BUFFER_TOO_SMALL;
  }
  lnr_writer_init(&writer, output, output_capacity);
  if (!lnr_write_f32_le(&writer, message->linear_velocity_mps) ||
      !lnr_write_f32_le(&writer, message->yaw_rate_radps)) {
    return LNR_WIRE_STATUS_BUFFER_TOO_SMALL;
  }
  *output_size = lnr_writer_size(&writer);
  return LNR_WIRE_STATUS_OK;
}

LnrWireStatus lnr_decode_motion_command_payload(const uint8_t *data,
                                                size_t size,
                                                LnrMotionCommand *message) {
  LnrReader reader;
  if (data == NULL || message == NULL) {
    return LNR_WIRE_STATUS_INVALID_ARGUMENT;
  }
  if (size != LNR_MOTION_COMMAND_PAYLOAD_SIZE) {
    return LNR_WIRE_STATUS_BAD_LENGTH;
  }
  lnr_reader_init(&reader, data, size);
  if (!lnr_read_f32_le(&reader, &message->linear_velocity_mps) ||
      !lnr_read_f32_le(&reader, &message->yaw_rate_radps)) {
    return LNR_WIRE_STATUS_BAD_LENGTH;
  }
  return motion_is_valid(message) ? LNR_WIRE_STATUS_OK : LNR_WIRE_STATUS_BAD_PAYLOAD;
}

LnrWireStatus lnr_encode_mcu_status_payload(const LnrMcuStatus *message,
                                           uint8_t *output,
                                           size_t output_capacity,
                                           size_t *output_size) {
  LnrWriter writer;
  if (message == NULL || output == NULL || output_size == NULL) {
    return LNR_WIRE_STATUS_INVALID_ARGUMENT;
  }
  *output_size = 0U;
  if (message->state > (uint8_t)LNR_MCU_STATE_ACTIVE ||
      (message->inhibit_flags & (uint8_t)(~LNR_INHIBIT_KNOWN_MASK)) != 0U ||
      !isfinite(message->applied_linear_velocity_mps) ||
      !isfinite(message->applied_yaw_rate_radps)) {
    return LNR_WIRE_STATUS_BAD_PAYLOAD;
  }
  if (output_capacity < LNR_MCU_STATUS_PAYLOAD_SIZE) {
    return LNR_WIRE_STATUS_BUFFER_TOO_SMALL;
  }
  lnr_writer_init(&writer, output, output_capacity);
  if (!lnr_write_u32_le(&writer, message->uptime_ms) ||
      !lnr_write_u32_le(&writer, message->last_command_seq) ||
      !lnr_write_i32_le(&writer, message->board_temp_mdeg_c) ||
      !lnr_write_u8(&writer, message->state) ||
      !lnr_write_u8(&writer, message->inhibit_flags) ||
      !lnr_write_u16_le(&writer, 0U) ||
      !lnr_write_f32_le(&writer, message->applied_linear_velocity_mps) ||
      !lnr_write_f32_le(&writer, message->applied_yaw_rate_radps) ||
      !lnr_write_u32_le(&writer, message->rx_error_count)) {
    return LNR_WIRE_STATUS_BUFFER_TOO_SMALL;
  }
  *output_size = lnr_writer_size(&writer);
  return LNR_WIRE_STATUS_OK;
}

LnrWireStatus lnr_decode_mcu_status_payload(const uint8_t *data,
                                           size_t size,
                                           LnrMcuStatus *message) {
  LnrReader reader;
  uint16_t reserved = 0U;
  if (data == NULL || message == NULL) {
    return LNR_WIRE_STATUS_INVALID_ARGUMENT;
  }
  if (size != LNR_MCU_STATUS_PAYLOAD_SIZE) {
    return LNR_WIRE_STATUS_BAD_LENGTH;
  }
  lnr_reader_init(&reader, data, size);
  if (!lnr_read_u32_le(&reader, &message->uptime_ms) ||
      !lnr_read_u32_le(&reader, &message->last_command_seq) ||
      !lnr_read_i32_le(&reader, &message->board_temp_mdeg_c) ||
      !lnr_read_u8(&reader, &message->state) ||
      !lnr_read_u8(&reader, &message->inhibit_flags) ||
      !lnr_read_u16_le(&reader, &reserved) ||
      !lnr_read_f32_le(&reader, &message->applied_linear_velocity_mps) ||
      !lnr_read_f32_le(&reader, &message->applied_yaw_rate_radps) ||
      !lnr_read_u32_le(&reader, &message->rx_error_count)) {
    return LNR_WIRE_STATUS_BAD_LENGTH;
  }
  if (reserved != 0U || message->state > (uint8_t)LNR_MCU_STATE_ACTIVE ||
      (message->inhibit_flags & (uint8_t)(~LNR_INHIBIT_KNOWN_MASK)) != 0U ||
      !isfinite(message->applied_linear_velocity_mps) ||
      !isfinite(message->applied_yaw_rate_radps)) {
    return LNR_WIRE_STATUS_BAD_PAYLOAD;
  }
  return LNR_WIRE_STATUS_OK;
}
