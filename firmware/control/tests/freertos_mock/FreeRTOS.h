#ifndef FREERTOS_H
#define FREERTOS_H

#include <stddef.h>
#include <stdint.h>

typedef int BaseType_t;
typedef unsigned int UBaseType_t;
typedef uint32_t TickType_t;
typedef uint32_t StackType_t;
typedef struct {
  uintptr_t opaque;
} StaticTask_t;
typedef struct {
  uintptr_t opaque;
} StaticQueue_t;

#define pdTRUE 1
#define pdFALSE 0
#define pdPASS 1
#define portMAX_DELAY UINT32_MAX
#define pdMS_TO_TICKS(ms) ((TickType_t)(ms))
#define portYIELD_FROM_ISR(value) ((void)(value))

#endif
