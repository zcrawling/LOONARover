#ifndef LOONAR_CONTROL_FREERTOS_APP_H
#define LOONAR_CONTROL_FREERTOS_APP_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
  uint32_t (*monotonic_ms)(void);
  int32_t (*board_temp_mdeg_c)(void);
  bool (*uart_start)(void);
  size_t (*uart_read)(uint8_t *output, size_t capacity);
  bool (*uart_write)(const uint8_t *data, size_t size);
  void (*apply_motor_duty)(float left_duty, float right_duty);
} LnrControlHal;

bool lnr_control_freertos_start(const LnrControlHal *hal);

#ifdef __cplusplus
}
#endif

#endif
