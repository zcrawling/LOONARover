#include <stdint.h>
#include <string.h>

#include "loonar/interface_ids.h"
#include "loonar/wire/packet.h"
#include "test_support.h"

int main(void) {
  const uint8_t payload[] = {0x78U, 0x56U, 0x34U, 0x12U};
  const uint8_t golden[] = {0x5AU, 0xA5U, 0x01U, 0x10U, 0x04U, 0x00U,
                            0x01U, 0x00U, 0x00U, 0x00U, 0x78U, 0x56U,
                            0x34U, 0x12U, 0xFDU, 0x8EU, 0x28U, 0x7BU};
  uint8_t bytes[LNR_WIRE_MAX_PACKET_SIZE] = {0U};
  size_t size = 0U;
  LnrPacketHeader header = {(uint8_t)LNR_MSG_MPU_HEALTH, (uint16_t)sizeof(payload), 1U};
  LnrPacketView packet;

  TEST_CHECK(lnr_encode_packet(&header, payload, sizeof(payload), bytes, sizeof(bytes), &size) ==
             LNR_WIRE_STATUS_OK);
  TEST_CHECK(size == sizeof(golden));
  TEST_CHECK(memcmp(bytes, golden, sizeof(golden)) == 0);
  TEST_CHECK(lnr_decode_complete_packet(bytes, size, &packet) == LNR_WIRE_STATUS_OK);
  TEST_CHECK(packet.header.msg_id == (uint8_t)LNR_MSG_MPU_HEALTH);
  TEST_CHECK(packet.header.sequence == 1U);
  TEST_CHECK(packet.payload_size == sizeof(payload));
  TEST_CHECK(memcmp(packet.payload, payload, sizeof(payload)) == 0);

  bytes[LNR_WIRE_HEADER_SIZE] ^= UINT8_C(0x80);
  TEST_CHECK(lnr_decode_complete_packet(bytes, size, &packet) == LNR_WIRE_STATUS_BAD_CRC);
  bytes[LNR_WIRE_HEADER_SIZE] ^= UINT8_C(0x80);

  bytes[2] = 2U;
  TEST_CHECK(lnr_decode_complete_packet(bytes, size, &packet) == LNR_WIRE_STATUS_BAD_VERSION);
  bytes[2] = LNR_WIRE_VERSION;
  header.payload_len = (uint16_t)(LNR_WIRE_MAX_PAYLOAD_SIZE + 1U);
  TEST_CHECK(lnr_validate_packet_header(&header) == LNR_WIRE_STATUS_BAD_LENGTH);
  header.payload_len = (uint16_t)sizeof(payload);
  TEST_CHECK(lnr_encode_packet(&header, payload, sizeof(payload), bytes, 4U, &size) ==
             LNR_WIRE_STATUS_BUFFER_TOO_SMALL);
  return 0;
}
