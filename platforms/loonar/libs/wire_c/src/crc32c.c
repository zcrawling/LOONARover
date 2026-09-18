#include "loonar/wire/crc32c.h"

uint32_t lnr_crc32c(const uint8_t *data, size_t size) {
  uint32_t crc = UINT32_C(0xFFFFFFFF);
  size_t index = 0U;
  unsigned bit = 0U;

  if (data == NULL && size > 0U) {
    return 0U;
  }

  for (index = 0U; index < size; ++index) {
    crc ^= (uint32_t)data[index];
    for (bit = 0U; bit < 8U; ++bit) {
      const uint32_t mask = (uint32_t)(0U - (crc & UINT32_C(1)));
      crc = (crc >> 1U) ^ (UINT32_C(0x82F63B78) & mask);
    }
  }
  return crc ^ UINT32_C(0xFFFFFFFF);
}

