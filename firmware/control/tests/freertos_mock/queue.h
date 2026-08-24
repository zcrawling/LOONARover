#ifndef QUEUE_H
#define QUEUE_H

#include "FreeRTOS.h"

typedef void *QueueHandle_t;

QueueHandle_t xQueueCreateStatic(UBaseType_t length,
                                 UBaseType_t item_size,
                                 uint8_t *storage,
                                 StaticQueue_t *queue_storage);
BaseType_t xQueueOverwrite(QueueHandle_t queue, const void *item);
BaseType_t xQueueReceive(QueueHandle_t queue, void *item, TickType_t wait_ticks);

#endif
