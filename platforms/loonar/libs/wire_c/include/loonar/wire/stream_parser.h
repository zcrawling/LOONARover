#ifndef LOONAR_WIRE_STREAM_PARSER_H
#define LOONAR_WIRE_STREAM_PARSER_H

#include <stddef.h>
#include <stdint.h>

#include "loonar/wire/packet.h"

#ifdef __cplusplus
extern "C" {
#endif

#define LNR_STREAM_BUFFER_CAPACITY (LNR_WIRE_MAX_PACKET_SIZE * (size_t)2)
#define LNR_DEFAULT_PARTIAL_TIMEOUT_US UINT64_C(20000)

typedef enum {
  LNR_PARSE_NONE = 0,
  LNR_PARSE_PACKET,
  LNR_PARSE_INVALID_ARGUMENT
} LnrParseResult;

typedef struct {
  uint32_t packets;
  uint32_t frame_errors;
  uint32_t crc_errors;
  uint32_t overflows;
  uint32_t partial_timeouts;
  uint32_t discarded_bytes;
} LnrParserStats;

typedef struct {
  uint8_t buffer[LNR_STREAM_BUFFER_CAPACITY];
  size_t buffer_size;
  uint8_t last_packet[LNR_WIRE_MAX_PACKET_SIZE];
  size_t last_packet_size;
  uint64_t partial_started_us;
  uint64_t partial_timeout_us;
  LnrParserStats stats;
} LnrStreamParser;

void lnr_parser_init(LnrStreamParser *parser, uint64_t partial_timeout_us);
LnrParseResult lnr_parser_push(LnrStreamParser *parser,
                               const uint8_t *data,
                               size_t size,
                               uint64_t now_us,
                               size_t *consumed,
                               LnrPacketView *packet);
void lnr_parser_expire_partial(LnrStreamParser *parser, uint64_t now_us);
const LnrParserStats *lnr_parser_stats(const LnrStreamParser *parser);

#ifdef __cplusplus
}
#endif

#endif

