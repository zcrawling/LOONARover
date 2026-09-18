#include "loonar/wire/byte_codec.h"

#include <string.h>

typedef char LnrFloatMustBe32Bits[(sizeof(float) == sizeof(uint32_t)) ? 1 : -1];

static bool writer_has(const LnrWriter *writer, size_t size) {
  return writer != NULL && writer->offset <= writer->capacity &&
         size <= writer->capacity - writer->offset &&
         (size == 0U || writer->data != NULL);
}

static bool reader_has(const LnrReader *reader, size_t size) {
  return reader != NULL && reader->offset <= reader->size &&
         size <= reader->size - reader->offset &&
         (size == 0U || reader->data != NULL);
}

void lnr_writer_init(LnrWriter *writer, uint8_t *data, size_t capacity) {
  if (writer != NULL) {
    writer->data = data;
    writer->capacity = capacity;
    writer->offset = 0U;
  }
}

void lnr_reader_init(LnrReader *reader, const uint8_t *data, size_t size) {
  if (reader != NULL) {
    reader->data = data;
    reader->size = size;
    reader->offset = 0U;
  }
}

size_t lnr_writer_size(const LnrWriter *writer) {
  return writer == NULL ? 0U : writer->offset;
}

size_t lnr_writer_remaining(const LnrWriter *writer) {
  if (writer == NULL || writer->offset > writer->capacity) {
    return 0U;
  }
  return writer->capacity - writer->offset;
}

size_t lnr_reader_remaining(const LnrReader *reader) {
  if (reader == NULL || reader->offset > reader->size) {
    return 0U;
  }
  return reader->size - reader->offset;
}

bool lnr_write_u8(LnrWriter *writer, uint8_t value) {
  if (!writer_has(writer, 1U)) {
    return false;
  }
  writer->data[writer->offset] = value;
  writer->offset += 1U;
  return true;
}

bool lnr_write_u16_le(LnrWriter *writer, uint16_t value) {
  if (!writer_has(writer, 2U)) {
    return false;
  }
  writer->data[writer->offset] = (uint8_t)(value & UINT16_C(0x00FF));
  writer->data[writer->offset + 1U] = (uint8_t)((value >> 8U) & UINT16_C(0x00FF));
  writer->offset += 2U;
  return true;
}

bool lnr_write_u32_le(LnrWriter *writer, uint32_t value) {
  size_t index = 0U;
  if (!writer_has(writer, 4U)) {
    return false;
  }
  for (index = 0U; index < 4U; ++index) {
    writer->data[writer->offset + index] =
        (uint8_t)((value >> (uint32_t)(index * 8U)) & UINT32_C(0xFF));
  }
  writer->offset += 4U;
  return true;
}

bool lnr_write_u64_le(LnrWriter *writer, uint64_t value) {
  size_t index = 0U;
  if (!writer_has(writer, 8U)) {
    return false;
  }
  for (index = 0U; index < 8U; ++index) {
    writer->data[writer->offset + index] =
        (uint8_t)((value >> (uint64_t)(index * 8U)) & UINT64_C(0xFF));
  }
  writer->offset += 8U;
  return true;
}

bool lnr_write_i32_le(LnrWriter *writer, int32_t value) {
  uint32_t bits = 0U;
  memcpy(&bits, &value, sizeof(bits));
  return lnr_write_u32_le(writer, bits);
}

bool lnr_write_i64_le(LnrWriter *writer, int64_t value) {
  uint64_t bits = 0U;
  memcpy(&bits, &value, sizeof(bits));
  return lnr_write_u64_le(writer, bits);
}

bool lnr_write_f32_le(LnrWriter *writer, float value) {
  uint32_t bits = 0U;
  memcpy(&bits, &value, sizeof(bits));
  return lnr_write_u32_le(writer, bits);
}

bool lnr_write_bytes(LnrWriter *writer, const uint8_t *data, size_t size) {
  if (!writer_has(writer, size) || (size > 0U && data == NULL)) {
    return false;
  }
  if (size > 0U) {
    memcpy(writer->data + writer->offset, data, size);
    writer->offset += size;
  }
  return true;
}

bool lnr_read_u8(LnrReader *reader, uint8_t *value) {
  if (!reader_has(reader, 1U) || value == NULL) {
    return false;
  }
  *value = reader->data[reader->offset];
  reader->offset += 1U;
  return true;
}

bool lnr_read_u16_le(LnrReader *reader, uint16_t *value) {
  if (!reader_has(reader, 2U) || value == NULL) {
    return false;
  }
  *value = (uint16_t)((uint16_t)reader->data[reader->offset] |
                      ((uint16_t)reader->data[reader->offset + 1U] << 8U));
  reader->offset += 2U;
  return true;
}

bool lnr_read_u32_le(LnrReader *reader, uint32_t *value) {
  size_t index = 0U;
  uint32_t result = 0U;
  if (!reader_has(reader, 4U) || value == NULL) {
    return false;
  }
  for (index = 0U; index < 4U; ++index) {
    result |= (uint32_t)reader->data[reader->offset + index]
              << (uint32_t)(index * 8U);
  }
  reader->offset += 4U;
  *value = result;
  return true;
}

bool lnr_read_u64_le(LnrReader *reader, uint64_t *value) {
  size_t index = 0U;
  uint64_t result = 0U;
  if (!reader_has(reader, 8U) || value == NULL) {
    return false;
  }
  for (index = 0U; index < 8U; ++index) {
    result |= (uint64_t)reader->data[reader->offset + index]
              << (uint64_t)(index * 8U);
  }
  reader->offset += 8U;
  *value = result;
  return true;
}

bool lnr_read_i32_le(LnrReader *reader, int32_t *value) {
  uint32_t bits = 0U;
  if (value == NULL || !lnr_read_u32_le(reader, &bits)) {
    return false;
  }
  memcpy(value, &bits, sizeof(bits));
  return true;
}

bool lnr_read_i64_le(LnrReader *reader, int64_t *value) {
  uint64_t bits = 0U;
  if (value == NULL || !lnr_read_u64_le(reader, &bits)) {
    return false;
  }
  memcpy(value, &bits, sizeof(bits));
  return true;
}

bool lnr_read_f32_le(LnrReader *reader, float *value) {
  uint32_t bits = 0U;
  if (value == NULL || !lnr_read_u32_le(reader, &bits)) {
    return false;
  }
  memcpy(value, &bits, sizeof(bits));
  return true;
}

bool lnr_read_bytes(LnrReader *reader, uint8_t *data, size_t size) {
  if (!reader_has(reader, size) || (size > 0U && data == NULL)) {
    return false;
  }
  if (size > 0U) {
    memcpy(data, reader->data + reader->offset, size);
    reader->offset += size;
  }
  return true;
}

