#include <math.h>
#include <stdint.h>

#include "loonar/control/control_core.h"
#include "loonar/control/control_rx.h"
#include "loonar/control/control_tx.h"
#include "loonar/interface_ids.h"
#include "loonar/wire/control_messages.h"
#include "loonar/wire/packet.h"
#include "test_support.h"

static size_t make_health_packet(uint32_t sequence, uint8_t *output) {
  const LnrMpuHealth health = {1234U};
  uint8_t payload[LNR_MPU_HEALTH_PAYLOAD_SIZE] = {0U};
  size_t payload_size = 0U;
  size_t output_size = 0U;
  LnrPacketHeader header = {(uint8_t)LNR_MSG_MPU_HEALTH,
                            (uint16_t)LNR_MPU_HEALTH_PAYLOAD_SIZE, sequence};
  TEST_CHECK(lnr_encode_mpu_health_payload(&health, payload, sizeof(payload), &payload_size) ==
             LNR_WIRE_STATUS_OK);
  TEST_CHECK(lnr_encode_packet(&header, payload, payload_size, output, LNR_WIRE_MAX_PACKET_SIZE,
                               &output_size) == LNR_WIRE_STATUS_OK);
  return output_size;
}

static size_t make_motion_packet(uint32_t sequence, uint8_t *output) {
  const LnrMotionCommand command = {0.4F, 0.1F};
  uint8_t payload[LNR_MOTION_COMMAND_PAYLOAD_SIZE] = {0U};
  size_t payload_size = 0U;
  size_t output_size = 0U;
  LnrPacketHeader header = {(uint8_t)LNR_MSG_MOTION_CMD,
                            (uint16_t)LNR_MOTION_COMMAND_PAYLOAD_SIZE, sequence};
  TEST_CHECK(lnr_encode_motion_command_payload(&command, payload, sizeof(payload),
                                                &payload_size) == LNR_WIRE_STATUS_OK);
  TEST_CHECK(lnr_encode_packet(&header, payload, payload_size, output, LNR_WIRE_MAX_PACKET_SIZE,
                               &output_size) == LNR_WIRE_STATUS_OK);
  return output_size;
}

static int feed_packet(LnrControlRx *rx,
                       LnrControlCore *core,
                       const uint8_t *packet,
                       size_t packet_size,
                       uint32_t now_ms) {
  size_t offset = 0U;
  while (offset < packet_size) {
    size_t consumed = 0U;
    const size_t chunk = packet_size - offset > 3U ? 3U : packet_size - offset;
    LnrControlEvent event;
    const LnrControlRxResult result =
        lnr_control_rx_push(rx, packet + offset, chunk, now_ms, &consumed, &event);
    TEST_CHECK(consumed > 0U);
    offset += consumed;
    if (result == LNR_CONTROL_RX_EVENT) {
      if (event.type == LNR_CONTROL_EVENT_HEALTH) {
        lnr_control_core_on_health(core, event.received_at_ms);
      } else if (event.type == LNR_CONTROL_EVENT_MOTION) {
        lnr_control_core_on_motion(core, event.sequence, &event.data.motion);
      }
    } else {
      TEST_CHECK(result == LNR_CONTROL_RX_NONE);
    }
  }
  return 0;
}

int main(void) {
  uint8_t health_packet[LNR_WIRE_MAX_PACKET_SIZE] = {0U};
  uint8_t motion_packet[LNR_WIRE_MAX_PACKET_SIZE] = {0U};
  uint8_t status_packet[LNR_WIRE_MAX_PACKET_SIZE] = {0U};
  size_t status_packet_size = 0U;
  const size_t health_size = make_health_packet(1U, health_packet);
  const size_t motion_size = make_motion_packet(2U, motion_packet);
  LnrControlRx rx;
  LnrControlCore core;
  LnrControlOutput output;
  LnrMcuStatus status;
  LnrMcuStatus decoded_status;
  LnrPacketView packet_view;

  lnr_control_rx_init(&rx);
  lnr_control_core_init(&core);
  TEST_CHECK(feed_packet(&rx, &core, health_packet, health_size, 100U) == 0);
  TEST_CHECK(feed_packet(&rx, &core, motion_packet, motion_size, 100U) == 0);
  output = lnr_control_core_step(&core, 100U, 40000);
  TEST_CHECK(output.state == (uint8_t)LNR_MCU_STATE_ACTIVE);
  TEST_CHECK(fabsf(output.linear_velocity_mps - 0.4F) < 0.0001F);

  motion_packet[LNR_WIRE_HEADER_SIZE] ^= UINT8_C(0x01);
  TEST_CHECK(feed_packet(&rx, &core, motion_packet, motion_size, 101U) == 0);
  TEST_CHECK(lnr_control_rx_error_count(&rx) == 1U);

  lnr_control_core_make_status(&core, 110U, 40000, lnr_control_rx_error_count(&rx), &status);
  TEST_CHECK(lnr_control_tx_encode_status(&status, 1U, status_packet, sizeof(status_packet),
                                          &status_packet_size) == LNR_WIRE_STATUS_OK);
  TEST_CHECK(lnr_decode_complete_packet(status_packet, status_packet_size, &packet_view) ==
             LNR_WIRE_STATUS_OK);
  TEST_CHECK(packet_view.header.msg_id == (uint8_t)LNR_MSG_MCU_STATUS);
  TEST_CHECK(lnr_decode_mcu_status_payload(packet_view.payload, packet_view.payload_size,
                                           &decoded_status) == LNR_WIRE_STATUS_OK);
  TEST_CHECK(decoded_status.last_command_seq == 2U);
  TEST_CHECK(decoded_status.rx_error_count == 1U);
  TEST_CHECK(fabsf(decoded_status.applied_linear_velocity_mps - 0.4F) < 0.0001F);
  return 0;
}
