#include <stdbool.h>
#include <stdint.h>

#include "loonar/interface_ids.h"
#include "loonar/wire/packet.h"
#include "loonar/wire/stream_parser.h"
#include "test_support.h"

#define SOAK_PACKET_COUNT UINT32_C(30000)
#define RANDOM_BYTE_COUNT ((size_t)200000)

static size_t make_packet(uint32_t sequence, uint8_t *output) {
  const uint8_t payload[4] = {(uint8_t)(sequence & UINT32_C(0xFF)),
                              (uint8_t)((sequence >> 8U) & UINT32_C(0xFF)),
                              (uint8_t)((sequence >> 16U) & UINT32_C(0xFF)),
                              (uint8_t)((sequence >> 24U) & UINT32_C(0xFF))};
  LnrPacketHeader header = {(uint8_t)LNR_MSG_MPU_HEALTH, (uint16_t)sizeof(payload), sequence};
  size_t output_size = 0U;
  if (lnr_encode_packet(&header, payload, sizeof(payload), output, LNR_WIRE_MAX_PACKET_SIZE,
                        &output_size) != LNR_WIRE_STATUS_OK) {
    return 0U;
  }
  return output_size;
}

static int feed_bytes(LnrStreamParser *parser,
                      const uint8_t *data,
                      size_t size,
                      uint64_t now_us,
                      uint32_t expected_sequence,
                      bool expect_packet) {
  size_t offset = 0U;
  bool observed = false;
  while (offset < size) {
    size_t consumed = 0U;
    LnrPacketView packet;
    const size_t chunk = ((offset + (size_t)expected_sequence) % 7U) + 1U;
    const size_t available = size - offset;
    const size_t offered = chunk < available ? chunk : available;
    const LnrParseResult result =
        lnr_parser_push(parser, data + offset, offered, now_us, &consumed, &packet);
    TEST_CHECK(consumed <= offered);
    TEST_CHECK(consumed > 0U || result == LNR_PARSE_PACKET);
    offset += consumed;
    if (result == LNR_PARSE_PACKET) {
      TEST_CHECK(!observed);
      TEST_CHECK(packet.header.sequence == expected_sequence);
      observed = true;
    } else {
      TEST_CHECK(result == LNR_PARSE_NONE);
    }
  }
  TEST_CHECK(observed == expect_packet);
  return 0;
}

int main(void) {
  uint8_t packet[LNR_WIRE_MAX_PACKET_SIZE] = {0U};
  const uint8_t garbage[] = {0x00U, 0x5AU, 0x00U};
  uint32_t sequence = 0U;
  uint32_t random_state = UINT32_C(0xC0FFEE01);
  size_t packet_size = 0U;
  size_t random_index = 0U;
  LnrStreamParser parser;

  lnr_parser_init(&parser, LNR_DEFAULT_PARTIAL_TIMEOUT_US);
  for (sequence = 1U; sequence <= SOAK_PACKET_COUNT; ++sequence) {
    packet_size = make_packet(sequence, packet);
    TEST_CHECK(packet_size > 0U);
    if (sequence % UINT32_C(997) == 0U) {
      TEST_CHECK(feed_bytes(&parser, garbage, sizeof(garbage), (uint64_t)sequence * UINT64_C(2000),
                            sequence, false) == 0);
    }
    TEST_CHECK(feed_bytes(&parser, packet, packet_size, (uint64_t)sequence * UINT64_C(2000),
                          sequence, true) == 0);
  }
  TEST_CHECK(lnr_parser_stats(&parser)->packets == SOAK_PACKET_COUNT);
  TEST_CHECK(lnr_parser_stats(&parser)->crc_errors == 0U);
  TEST_CHECK(lnr_parser_stats(&parser)->overflows == 0U);

  lnr_parser_init(&parser, LNR_DEFAULT_PARTIAL_TIMEOUT_US);
  for (random_index = 0U; random_index < RANDOM_BYTE_COUNT; ++random_index) {
    size_t consumed = 0U;
    LnrPacketView parsed_packet;
    LnrParseResult result;
    uint8_t random_byte = 0U;
    random_state = random_state * UINT32_C(1664525) + UINT32_C(1013904223);
    random_byte = (uint8_t)(random_state >> 24U);
    result = lnr_parser_push(&parser, &random_byte, 1U, (uint64_t)random_index, &consumed,
                             &parsed_packet);
    TEST_CHECK(consumed == 1U);
    TEST_CHECK(result == LNR_PARSE_NONE || result == LNR_PARSE_PACKET);
    TEST_CHECK(parser.buffer_size <= LNR_STREAM_BUFFER_CAPACITY);
  }
  lnr_parser_expire_partial(&parser,
                            (uint64_t)RANDOM_BYTE_COUNT + LNR_DEFAULT_PARTIAL_TIMEOUT_US);
  TEST_CHECK(parser.buffer_size == 0U);
  return 0;
}
