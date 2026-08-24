#include <math.h>
#include <stdint.h>
#include <string.h>

#include "loonar/wire/byte_codec.h"
#include "test_support.h"

int main(void) {
  uint8_t buffer[31] = {0U};
  const uint8_t expected_prefix[] = {0xABU, 0x34U, 0x12U, 0xEFU, 0xCDU, 0xABU, 0x89U};
  LnrWriter writer;
  LnrReader reader;
  uint8_t u8 = 0U;
  uint16_t u16 = 0U;
  uint32_t u32 = 0U;
  uint64_t u64 = 0U;
  int32_t i32 = 0;
  int64_t i64 = 0;
  float f32 = 0.0F;

  lnr_writer_init(&writer, buffer, sizeof(buffer));
  TEST_CHECK(lnr_write_u8(&writer, UINT8_C(0xAB)));
  TEST_CHECK(lnr_write_u16_le(&writer, UINT16_C(0x1234)));
  TEST_CHECK(lnr_write_u32_le(&writer, UINT32_C(0x89ABCDEF)));
  TEST_CHECK(lnr_write_u64_le(&writer, UINT64_C(0x0123456789ABCDEF)));
  TEST_CHECK(lnr_write_i32_le(&writer, INT32_C(-1234567)));
  TEST_CHECK(lnr_write_i64_le(&writer, INT64_C(-1234567890123)));
  TEST_CHECK(lnr_write_f32_le(&writer, 1.5F));
  TEST_CHECK(lnr_writer_size(&writer) == sizeof(buffer));
  TEST_CHECK(memcmp(buffer, expected_prefix, sizeof(expected_prefix)) == 0);
  TEST_CHECK(!lnr_write_u8(&writer, 0U));

  lnr_reader_init(&reader, buffer, sizeof(buffer));
  TEST_CHECK(lnr_read_u8(&reader, &u8) && u8 == UINT8_C(0xAB));
  TEST_CHECK(lnr_read_u16_le(&reader, &u16) && u16 == UINT16_C(0x1234));
  TEST_CHECK(lnr_read_u32_le(&reader, &u32) && u32 == UINT32_C(0x89ABCDEF));
  TEST_CHECK(lnr_read_u64_le(&reader, &u64) && u64 == UINT64_C(0x0123456789ABCDEF));
  TEST_CHECK(lnr_read_i32_le(&reader, &i32) && i32 == INT32_C(-1234567));
  TEST_CHECK(lnr_read_i64_le(&reader, &i64) && i64 == INT64_C(-1234567890123));
  TEST_CHECK(lnr_read_f32_le(&reader, &f32) && fabsf(f32 - 1.5F) < 0.0001F);
  TEST_CHECK(lnr_reader_remaining(&reader) == 0U);
  TEST_CHECK(!lnr_read_u8(&reader, &u8));

  lnr_writer_init(&writer, NULL, 0U);
  TEST_CHECK(lnr_write_bytes(&writer, NULL, 0U));
  TEST_CHECK(!lnr_write_u16_le(&writer, 1U));
  return 0;
}

