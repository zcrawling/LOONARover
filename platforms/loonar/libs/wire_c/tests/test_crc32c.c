#include <stdint.h>
#include <string.h>

#include "loonar/wire/crc32c.h"
#include "test_support.h"

int main(void) {
  static const uint8_t standard_vector[] = "123456789";
  TEST_CHECK(lnr_crc32c(standard_vector, strlen((const char *)standard_vector)) ==
             UINT32_C(0xE3069283));
  TEST_CHECK(lnr_crc32c(NULL, 0U) == UINT32_C(0));
  TEST_CHECK(lnr_crc32c(NULL, 1U) == UINT32_C(0));
  return 0;
}

