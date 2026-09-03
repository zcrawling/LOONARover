#ifndef LOONAR_CONTROL_CONTROL_TX_H
#define LOONAR_CONTROL_CONTROL_TX_H

#include <stddef.h>
#include <stdint.h>

#include "loonar/wire/control_messages.h"

#ifdef __cplusplus
extern "C" {
#endif

LnrWireStatus lnr_control_tx_encode_status(const LnrMcuStatus *status,
                                           uint32_t sequence,
                                           uint8_t *output,
                                           size_t output_capacity,
                                           size_t *output_size);

#ifdef __cplusplus
}
#endif

#endif
