#include "loonar/control/control_rx.h"

#include "loonar/interface_ids.h"

static void increment_rejected(LnrControlRx *rx) {
  if (rx->rejected_messages != UINT32_MAX) {
    rx->rejected_messages += 1U;
  }
}

void lnr_control_rx_init(LnrControlRx *rx) {
  if (rx != NULL) {
    lnr_parser_init(&rx->parser, LNR_DEFAULT_PARTIAL_TIMEOUT_US);
    rx->rejected_messages = 0U;
  }
}

LnrControlRxResult lnr_control_rx_push(LnrControlRx *rx,
                                      const uint8_t *data,
                                      size_t size,
                                      uint32_t now_ms,
                                      size_t *consumed,
                                      LnrControlEvent *event) {
  LnrPacketView packet;
  LnrParseResult parse_result;
  LnrWireStatus decode_status = LNR_WIRE_STATUS_OK;

  if (rx == NULL || consumed == NULL || event == NULL || (size > 0U && data == NULL)) {
    return LNR_CONTROL_RX_INVALID_ARGUMENT;
  }
  event->type = LNR_CONTROL_EVENT_NONE;
  parse_result = lnr_parser_push(&rx->parser, data, size, (uint64_t)now_ms * UINT64_C(1000),
                                 consumed, &packet);
  if (parse_result == LNR_PARSE_INVALID_ARGUMENT) {
    return LNR_CONTROL_RX_INVALID_ARGUMENT;
  }
  if (parse_result == LNR_PARSE_NONE) {
    return LNR_CONTROL_RX_NONE;
  }

  event->sequence = packet.header.sequence;
  event->received_at_ms = now_ms;
  if (packet.header.msg_id == (uint8_t)LNR_MSG_MPU_HEALTH) {
    decode_status =
        lnr_decode_mpu_health_payload(packet.payload, packet.payload_size, &event->data.health);
    event->type = LNR_CONTROL_EVENT_HEALTH;
  } else if (packet.header.msg_id == (uint8_t)LNR_MSG_MOTION_CMD) {
    decode_status = lnr_decode_motion_command_payload(packet.payload, packet.payload_size,
                                                      &event->data.motion);
    event->type = LNR_CONTROL_EVENT_MOTION;
  } else {
    decode_status = LNR_WIRE_STATUS_BAD_PAYLOAD;
  }

  if (decode_status != LNR_WIRE_STATUS_OK) {
    event->type = LNR_CONTROL_EVENT_NONE;
    increment_rejected(rx);
    return LNR_CONTROL_RX_REJECTED;
  }
  return LNR_CONTROL_RX_EVENT;
}

void lnr_control_rx_expire(LnrControlRx *rx, uint32_t now_ms) {
  if (rx != NULL) {
    lnr_parser_expire_partial(&rx->parser, (uint64_t)now_ms * UINT64_C(1000));
  }
}

uint32_t lnr_control_rx_error_count(const LnrControlRx *rx) {
  const LnrParserStats *stats = NULL;
  uint64_t total = 0U;
  if (rx == NULL) {
    return 0U;
  }
  stats = lnr_parser_stats(&rx->parser);
  total = (uint64_t)rx->rejected_messages + (uint64_t)stats->frame_errors +
          (uint64_t)stats->crc_errors + (uint64_t)stats->overflows +
          (uint64_t)stats->partial_timeouts;
  return total > UINT32_MAX ? UINT32_MAX : (uint32_t)total;
}
