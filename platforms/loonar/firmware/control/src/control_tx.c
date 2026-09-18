#include "loonar/control/control_tx.h"

#include "loonar/interface_ids.h"
#include "loonar/wire/packet.h"

LnrWireStatus lnr_control_tx_encode_status(const LnrMcuStatus *status,
                                           uint32_t sequence,
                                           uint8_t *output,
                                           size_t output_capacity,
                                           size_t *output_size) {
  uint8_t payload[LNR_MCU_STATUS_PAYLOAD_SIZE] = {0U};
  size_t payload_size = 0U;
  LnrPacketHeader header = {(uint8_t)LNR_MSG_MCU_STATUS,
                            (uint16_t)LNR_MCU_STATUS_PAYLOAD_SIZE, sequence};
  LnrWireStatus wire_status = lnr_encode_mcu_status_payload(
      status, payload, sizeof(payload), &payload_size);
  if (wire_status != LNR_WIRE_STATUS_OK) {
    return wire_status;
  }
  return lnr_encode_packet(&header, payload, payload_size, output, output_capacity, output_size);
}
