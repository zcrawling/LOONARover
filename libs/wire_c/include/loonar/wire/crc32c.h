#ifndef LOONAR_WIRE_CRC32C_H
#define LOONAR_WIRE_CRC32C_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

uint32_t lnr_crc32c(const uint8_t *data, size_t size);

#ifdef __cplusplus
}
#endif

#endif

