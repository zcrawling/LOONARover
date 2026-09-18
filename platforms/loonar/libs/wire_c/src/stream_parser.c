#include "loonar/wire/stream_parser.h"

#include <stdbool.h>
#include <string.h>

static void saturating_increment(uint32_t *value) {
  if (*value != UINT32_MAX) {
    *value += 1U;
  }
}

static void add_discarded(LnrStreamParser *parser, size_t count) {
  const uint32_t room = UINT32_MAX - parser->stats.discarded_bytes;
  const uint32_t amount = count > (size_t)room ? room : (uint32_t)count;
  parser->stats.discarded_bytes += amount;
}

static void drop_prefix(LnrStreamParser *parser, size_t count) {
  if (count >= parser->buffer_size) {
    add_discarded(parser, parser->buffer_size);
    parser->buffer_size = 0U;
    parser->partial_started_us = 0U;
    return;
  }
  memmove(parser->buffer, parser->buffer + count, parser->buffer_size - count);
  parser->buffer_size -= count;
  add_discarded(parser, count);
}

static size_t find_sync(const uint8_t *data, size_t size) {
  size_t index = 0U;
  if (size < 2U) {
    return SIZE_MAX;
  }
  for (index = 0U; index + 1U < size; ++index) {
    if (data[index] == UINT8_C(0x5A) && data[index + 1U] == UINT8_C(0xA5)) {
      return index;
    }
  }
  return SIZE_MAX;
}

static bool extract_packet(LnrStreamParser *parser,
                           uint64_t now_us,
                           LnrPacketView *packet) {
  for (;;) {
    size_t sync_index = 0U;
    size_t expected_size = 0U;
    LnrPacketHeader header;
    LnrWireStatus status = LNR_WIRE_STATUS_OK;

    if (parser->buffer_size < 2U) {
      return false;
    }
    sync_index = find_sync(parser->buffer, parser->buffer_size);
    if (sync_index == SIZE_MAX) {
      const bool keep_sync_prefix = parser->buffer[parser->buffer_size - 1U] == UINT8_C(0x5A);
      const size_t discard = parser->buffer_size - (keep_sync_prefix ? 1U : 0U);
      drop_prefix(parser, discard);
      return false;
    }
    if (sync_index > 0U) {
      drop_prefix(parser, sync_index);
    }
    if (parser->buffer_size < LNR_WIRE_HEADER_SIZE) {
      return false;
    }

    status = lnr_decode_packet_header(parser->buffer, parser->buffer_size, &header);
    if (status != LNR_WIRE_STATUS_OK) {
      saturating_increment(&parser->stats.frame_errors);
      drop_prefix(parser, 1U);
      continue;
    }
    expected_size = LNR_WIRE_HEADER_SIZE + (size_t)header.payload_len + LNR_WIRE_CRC_SIZE;
    if (parser->buffer_size < expected_size) {
      return false;
    }

    status = lnr_decode_complete_packet(parser->buffer, expected_size, packet);
    if (status == LNR_WIRE_STATUS_BAD_CRC) {
      saturating_increment(&parser->stats.crc_errors);
      drop_prefix(parser, 1U);
      continue;
    }
    if (status != LNR_WIRE_STATUS_OK) {
      saturating_increment(&parser->stats.frame_errors);
      drop_prefix(parser, 1U);
      continue;
    }

    memcpy(parser->last_packet, parser->buffer, expected_size);
    parser->last_packet_size = expected_size;
    drop_prefix(parser, expected_size);
    if (parser->buffer_size > 0U) {
      parser->partial_started_us = now_us;
    }
    (void)lnr_decode_complete_packet(parser->last_packet, parser->last_packet_size, packet);
    saturating_increment(&parser->stats.packets);
    return true;
  }
}

void lnr_parser_init(LnrStreamParser *parser, uint64_t partial_timeout_us) {
  if (parser != NULL) {
    memset(parser, 0, sizeof(*parser));
    parser->partial_timeout_us =
        partial_timeout_us == 0U ? LNR_DEFAULT_PARTIAL_TIMEOUT_US : partial_timeout_us;
  }
}

LnrParseResult lnr_parser_push(LnrStreamParser *parser,
                               const uint8_t *data,
                               size_t size,
                               uint64_t now_us,
                               size_t *consumed,
                               LnrPacketView *packet) {
  if (parser == NULL || consumed == NULL || packet == NULL || (size > 0U && data == NULL)) {
    return LNR_PARSE_INVALID_ARGUMENT;
  }
  *consumed = 0U;
  if (extract_packet(parser, now_us, packet)) {
    return LNR_PARSE_PACKET;
  }

  while (*consumed < size) {
    if (parser->buffer_size == LNR_STREAM_BUFFER_CAPACITY) {
      saturating_increment(&parser->stats.overflows);
      drop_prefix(parser, 1U);
    }
    if (parser->buffer_size == 0U) {
      parser->partial_started_us = now_us;
    }
    parser->buffer[parser->buffer_size] = data[*consumed];
    parser->buffer_size += 1U;
    *consumed += 1U;
    if (extract_packet(parser, now_us, packet)) {
      return LNR_PARSE_PACKET;
    }
  }
  return LNR_PARSE_NONE;
}

void lnr_parser_expire_partial(LnrStreamParser *parser, uint64_t now_us) {
  if (parser == NULL || parser->buffer_size == 0U || now_us < parser->partial_started_us) {
    return;
  }
  if (now_us - parser->partial_started_us >= parser->partial_timeout_us) {
    saturating_increment(&parser->stats.partial_timeouts);
    drop_prefix(parser, parser->buffer_size);
  }
}

const LnrParserStats *lnr_parser_stats(const LnrStreamParser *parser) {
  return parser == NULL ? NULL : &parser->stats;
}
