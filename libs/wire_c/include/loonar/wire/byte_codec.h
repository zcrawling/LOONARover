#ifndef LOONAR_WIRE_BYTE_CODEC_H
#define LOONAR_WIRE_BYTE_CODEC_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
  uint8_t *data;
  size_t capacity;
  size_t offset;
} LnrWriter;

typedef struct {
  const uint8_t *data;
  size_t size;
  size_t offset;
} LnrReader;

void lnr_writer_init(LnrWriter *writer, uint8_t *data, size_t capacity);
void lnr_reader_init(LnrReader *reader, const uint8_t *data, size_t size);

size_t lnr_writer_size(const LnrWriter *writer);
size_t lnr_writer_remaining(const LnrWriter *writer);
size_t lnr_reader_remaining(const LnrReader *reader);

bool lnr_write_u8(LnrWriter *writer, uint8_t value);
bool lnr_write_u16_le(LnrWriter *writer, uint16_t value);
bool lnr_write_u32_le(LnrWriter *writer, uint32_t value);
bool lnr_write_u64_le(LnrWriter *writer, uint64_t value);
bool lnr_write_i32_le(LnrWriter *writer, int32_t value);
bool lnr_write_i64_le(LnrWriter *writer, int64_t value);
bool lnr_write_f32_le(LnrWriter *writer, float value);
bool lnr_write_bytes(LnrWriter *writer, const uint8_t *data, size_t size);

bool lnr_read_u8(LnrReader *reader, uint8_t *value);
bool lnr_read_u16_le(LnrReader *reader, uint16_t *value);
bool lnr_read_u32_le(LnrReader *reader, uint32_t *value);
bool lnr_read_u64_le(LnrReader *reader, uint64_t *value);
bool lnr_read_i32_le(LnrReader *reader, int32_t *value);
bool lnr_read_i64_le(LnrReader *reader, int64_t *value);
bool lnr_read_f32_le(LnrReader *reader, float *value);
bool lnr_read_bytes(LnrReader *reader, uint8_t *data, size_t size);

#ifdef __cplusplus
}
#endif

#endif

