#include "loonar/wire/packet.h"

#include "loonar/wire/byte_codec.h"
#include "loonar/wire/crc32c.h"

LnrWireStatus lnr_validate_packet_header(const LnrPacketHeader *header) {
  if (header == NULL) {
    return LNR_WIRE_STATUS_INVALID_ARGUMENT;
  }
  if ((size_t)header->payload_len > LNR_WIRE_MAX_PAYLOAD_SIZE) {
    return LNR_WIRE_STATUS_BAD_LENGTH;
  }
  return LNR_WIRE_STATUS_OK;
}

LnrWireStatus lnr_decode_packet_header(const uint8_t *data,
                                       size_t size,
                                       LnrPacketHeader *header) {
  LnrReader reader;
  uint16_t sync = 0U;
  uint8_t version = 0U;

  if (data == NULL || header == NULL) {
    return LNR_WIRE_STATUS_INVALID_ARGUMENT;
  }
  if (size < LNR_WIRE_HEADER_SIZE) {
    return LNR_WIRE_STATUS_INCOMPLETE;
  }

  lnr_reader_init(&reader, data, size);
  if (!lnr_read_u16_le(&reader, &sync) || !lnr_read_u8(&reader, &version) ||
      !lnr_read_u8(&reader, &header->msg_id) ||
      !lnr_read_u16_le(&reader, &header->payload_len) ||
      !lnr_read_u32_le(&reader, &header->sequence)) {
    return LNR_WIRE_STATUS_INCOMPLETE;
  }
  if (sync != LNR_WIRE_SYNC) {
    return LNR_WIRE_STATUS_BAD_SYNC;
  }
  if (version != LNR_WIRE_VERSION) {
    return LNR_WIRE_STATUS_BAD_VERSION;
  }
  return lnr_validate_packet_header(header);
}

LnrWireStatus lnr_encode_packet(const LnrPacketHeader *header,
                                const uint8_t *payload,
                                size_t payload_size,
                                uint8_t *output,
                                size_t output_capacity,
                                size_t *output_size) {
  LnrWriter writer;
  uint32_t crc = 0U;
  size_t required = 0U;
  LnrWireStatus status = LNR_WIRE_STATUS_OK;

  if (header == NULL || output == NULL || output_size == NULL ||
      (payload_size > 0U && payload == NULL)) {
    return LNR_WIRE_STATUS_INVALID_ARGUMENT;
  }
  *output_size = 0U;
  status = lnr_validate_packet_header(header);
  if (status != LNR_WIRE_STATUS_OK) {
    return status;
  }
  if ((size_t)header->payload_len != payload_size) {
    return LNR_WIRE_STATUS_BAD_LENGTH;
  }
  required = LNR_WIRE_HEADER_SIZE + payload_size + LNR_WIRE_CRC_SIZE;
  if (output_capacity < required) {
    return LNR_WIRE_STATUS_BUFFER_TOO_SMALL;
  }

  lnr_writer_init(&writer, output, output_capacity);
  if (!lnr_write_u16_le(&writer, LNR_WIRE_SYNC) ||
      !lnr_write_u8(&writer, LNR_WIRE_VERSION) ||
      !lnr_write_u8(&writer, header->msg_id) ||
      !lnr_write_u16_le(&writer, header->payload_len) ||
      !lnr_write_u32_le(&writer, header->sequence) ||
      !lnr_write_bytes(&writer, payload, payload_size)) {
    return LNR_WIRE_STATUS_BUFFER_TOO_SMALL;
  }
  crc = lnr_crc32c(output, LNR_WIRE_HEADER_SIZE + payload_size);
  if (!lnr_write_u32_le(&writer, crc)) {
    return LNR_WIRE_STATUS_BUFFER_TOO_SMALL;
  }
  *output_size = lnr_writer_size(&writer);
  return LNR_WIRE_STATUS_OK;
}

LnrWireStatus lnr_decode_complete_packet(const uint8_t *data,
                                         size_t size,
                                         LnrPacketView *packet) {
  LnrPacketHeader header;
  LnrReader crc_reader;
  uint32_t encoded_crc = 0U;
  uint32_t computed_crc = 0U;
  size_t required = 0U;
  LnrWireStatus status = LNR_WIRE_STATUS_OK;

  if (data == NULL || packet == NULL) {
    return LNR_WIRE_STATUS_INVALID_ARGUMENT;
  }
  status = lnr_decode_packet_header(data, size, &header);
  if (status != LNR_WIRE_STATUS_OK) {
    return status;
  }
  required = LNR_WIRE_HEADER_SIZE + (size_t)header.payload_len + LNR_WIRE_CRC_SIZE;
  if (size < required) {
    return LNR_WIRE_STATUS_INCOMPLETE;
  }
  if (size != required) {
    return LNR_WIRE_STATUS_BAD_LENGTH;
  }

  lnr_reader_init(&crc_reader, data + required - LNR_WIRE_CRC_SIZE, LNR_WIRE_CRC_SIZE);
  if (!lnr_read_u32_le(&crc_reader, &encoded_crc)) {
    return LNR_WIRE_STATUS_INCOMPLETE;
  }
  computed_crc = lnr_crc32c(data, required - LNR_WIRE_CRC_SIZE);
  if (encoded_crc != computed_crc) {
    return LNR_WIRE_STATUS_BAD_CRC;
  }

  packet->header = header;
  packet->payload = data + LNR_WIRE_HEADER_SIZE;
  packet->payload_size = (size_t)header.payload_len;
  packet->raw_size = required;
  return LNR_WIRE_STATUS_OK;
}

const char *lnr_wire_status_string(LnrWireStatus status) {
  switch (status) {
    case LNR_WIRE_STATUS_OK:
      return "OK";
    case LNR_WIRE_STATUS_INVALID_ARGUMENT:
      return "INVALID_ARGUMENT";
    case LNR_WIRE_STATUS_BUFFER_TOO_SMALL:
      return "BUFFER_TOO_SMALL";
    case LNR_WIRE_STATUS_INCOMPLETE:
      return "INCOMPLETE";
    case LNR_WIRE_STATUS_BAD_SYNC:
      return "BAD_SYNC";
    case LNR_WIRE_STATUS_BAD_VERSION:
      return "BAD_VERSION";
    case LNR_WIRE_STATUS_BAD_LENGTH:
      return "BAD_LENGTH";
    case LNR_WIRE_STATUS_BAD_CRC:
      return "BAD_CRC";
    case LNR_WIRE_STATUS_BAD_PAYLOAD:
      return "BAD_PAYLOAD";
    default:
      return "UNKNOWN";
  }
}
