#ifndef LOONAR_WIRE_PACKET_H
#define LOONAR_WIRE_PACKET_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define LNR_WIRE_SYNC UINT16_C(0xA55A)
#define LNR_WIRE_VERSION UINT8_C(1)
#define LNR_WIRE_HEADER_SIZE ((size_t)10)
#define LNR_WIRE_CRC_SIZE ((size_t)4)
#define LNR_WIRE_MAX_PAYLOAD_SIZE ((size_t)32)
#define LNR_WIRE_MAX_PACKET_SIZE \
  (LNR_WIRE_HEADER_SIZE + LNR_WIRE_MAX_PAYLOAD_SIZE + LNR_WIRE_CRC_SIZE)

typedef enum {
  LNR_WIRE_STATUS_OK = 0,
  LNR_WIRE_STATUS_INVALID_ARGUMENT,
  LNR_WIRE_STATUS_BUFFER_TOO_SMALL,
  LNR_WIRE_STATUS_INCOMPLETE,
  LNR_WIRE_STATUS_BAD_SYNC,
  LNR_WIRE_STATUS_BAD_VERSION,
  LNR_WIRE_STATUS_BAD_LENGTH,
  LNR_WIRE_STATUS_BAD_CRC,
  LNR_WIRE_STATUS_BAD_PAYLOAD
} LnrWireStatus;

typedef struct {
  uint8_t msg_id;
  uint16_t payload_len;
  uint32_t sequence;
} LnrPacketHeader;

typedef struct {
  LnrPacketHeader header;
  const uint8_t *payload;
  size_t payload_size;
  size_t raw_size;
} LnrPacketView;

LnrWireStatus lnr_validate_packet_header(const LnrPacketHeader *header);
LnrWireStatus lnr_decode_packet_header(const uint8_t *data,
                                       size_t size,
                                       LnrPacketHeader *header);
LnrWireStatus lnr_encode_packet(const LnrPacketHeader *header,
                                const uint8_t *payload,
                                size_t payload_size,
                                uint8_t *output,
                                size_t output_capacity,
                                size_t *output_size);
LnrWireStatus lnr_decode_complete_packet(const uint8_t *data,
                                         size_t size,
                                         LnrPacketView *packet);
const char *lnr_wire_status_string(LnrWireStatus status);

#ifdef __cplusplus
}
#endif

#endif
