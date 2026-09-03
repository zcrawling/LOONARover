#ifndef LOONAR_CONTROL_CONTROL_RX_H
#define LOONAR_CONTROL_CONTROL_RX_H

#include <stddef.h>
#include <stdint.h>

#include "loonar/wire/control_messages.h"
#include "loonar/wire/stream_parser.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
  LNR_CONTROL_EVENT_NONE = 0,
  LNR_CONTROL_EVENT_HEALTH,
  LNR_CONTROL_EVENT_MOTION
} LnrControlEventType;

typedef struct {
  LnrControlEventType type;
  uint32_t sequence;
  uint32_t received_at_ms;
  union {
    LnrMpuHealth health;
    LnrMotionCommand motion;
  } data;
} LnrControlEvent;

typedef enum {
  LNR_CONTROL_RX_NONE = 0,
  LNR_CONTROL_RX_EVENT,
  LNR_CONTROL_RX_REJECTED,
  LNR_CONTROL_RX_INVALID_ARGUMENT
} LnrControlRxResult;

typedef struct {
  LnrStreamParser parser;
  uint32_t rejected_messages;
} LnrControlRx;

void lnr_control_rx_init(LnrControlRx *rx);
LnrControlRxResult lnr_control_rx_push(LnrControlRx *rx,
                                      const uint8_t *data,
                                      size_t size,
                                      uint32_t now_ms,
                                      size_t *consumed,
                                      LnrControlEvent *event);
void lnr_control_rx_expire(LnrControlRx *rx, uint32_t now_ms);
uint32_t lnr_control_rx_error_count(const LnrControlRx *rx);

#ifdef __cplusplus
}
#endif

#endif
