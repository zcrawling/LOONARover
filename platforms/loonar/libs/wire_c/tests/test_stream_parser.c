#include <stdint.h>
#include <string.h>

#include "loonar/interface_ids.h"
#include "loonar/wire/packet.h"
#include "loonar/wire/stream_parser.h"
#include "test_support.h"

static size_t make_packet(uint32_t sequence, uint8_t value, uint8_t *output) {
  LnrPacketHeader header = {(uint8_t)LNR_MSG_MPU_HEALTH, 1U, sequence};
  size_t output_size = 0U;
  if (lnr_encode_packet(&header, &value, 1U, output, LNR_WIRE_MAX_PACKET_SIZE,
                        &output_size) != LNR_WIRE_STATUS_OK) {
    return 0U;
  }
  return output_size;
}

int main(void) {
  uint8_t first[LNR_WIRE_MAX_PACKET_SIZE] = {0U};
  uint8_t second[LNR_WIRE_MAX_PACKET_SIZE] = {0U};
  uint8_t combined[LNR_WIRE_MAX_PACKET_SIZE * 2U] = {0U};
  uint8_t corrupt[LNR_WIRE_MAX_PACKET_SIZE] = {0U};
  const uint8_t garbage[] = {0x00U, 0xA5U, 0x5AU, 0x01U, 0x5AU};
  size_t first_size = make_packet(1U, 0x11U, first);
  size_t second_size = make_packet(2U, 0x22U, second);
  size_t index = 0U;
  size_t consumed = 0U;
  LnrPacketView packet;
  LnrStreamParser parser;
  LnrParseResult result = LNR_PARSE_NONE;

  TEST_CHECK(first_size > 0U && second_size > 0U);
  lnr_parser_init(&parser, 100U);
  for (index = 0U; index < first_size; ++index) {
    result = lnr_parser_push(&parser, first + index, 1U, (uint64_t)index + 1U, &consumed,
                             &packet);
    TEST_CHECK(consumed == 1U);
    if (index + 1U < first_size) {
      TEST_CHECK(result == LNR_PARSE_NONE);
    }
  }
  TEST_CHECK(result == LNR_PARSE_PACKET);
  TEST_CHECK(packet.header.sequence == 1U && packet.payload[0] == 0x11U);

  memcpy(combined, first, first_size);
  memcpy(combined + first_size, second, second_size);
  lnr_parser_init(&parser, 100U);
  result = lnr_parser_push(&parser, combined, first_size + second_size, 10U, &consumed, &packet);
  TEST_CHECK(result == LNR_PARSE_PACKET && consumed == first_size);
  TEST_CHECK(packet.header.sequence == 1U);
  result = lnr_parser_push(&parser, combined + consumed, first_size + second_size - consumed, 10U,
                           &index, &packet);
  TEST_CHECK(result == LNR_PARSE_PACKET && index == second_size);
  TEST_CHECK(packet.header.sequence == 2U);

  lnr_parser_init(&parser, 100U);
  result = lnr_parser_push(&parser, garbage, sizeof(garbage), 20U, &consumed, &packet);
  TEST_CHECK(result == LNR_PARSE_NONE);
  result = lnr_parser_push(&parser, first, first_size, 21U, &consumed, &packet);
  TEST_CHECK(result == LNR_PARSE_PACKET && packet.header.sequence == 1U);

  memcpy(corrupt, first, first_size);
  corrupt[LNR_WIRE_HEADER_SIZE] ^= UINT8_C(0x40);
  lnr_parser_init(&parser, 100U);
  memcpy(combined, corrupt, first_size);
  memcpy(combined + first_size, second, second_size);
  result = lnr_parser_push(&parser, combined, first_size + second_size, 30U, &consumed, &packet);
  TEST_CHECK(result == LNR_PARSE_PACKET);
  TEST_CHECK(packet.header.sequence == 2U);
  TEST_CHECK(lnr_parser_stats(&parser)->crc_errors == 1U);

  lnr_parser_init(&parser, 50U);
  result = lnr_parser_push(&parser, first, 5U, 100U, &consumed, &packet);
  TEST_CHECK(result == LNR_PARSE_NONE && parser.buffer_size == 5U);
  lnr_parser_expire_partial(&parser, 150U);
  TEST_CHECK(parser.buffer_size == 0U);
  TEST_CHECK(lnr_parser_stats(&parser)->partial_timeouts == 1U);
  return 0;
}
