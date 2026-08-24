#ifndef TASK_H
#define TASK_H

#include "FreeRTOS.h"

typedef void *TaskHandle_t;
typedef void (*TaskFunction_t)(void *);

TaskHandle_t xTaskCreateStatic(TaskFunction_t task,
                               const char *name,
                               uint32_t stack_depth,
                               void *argument,
                               UBaseType_t priority,
                               StackType_t *stack,
                               StaticTask_t *task_storage);
TickType_t xTaskGetTickCount(void);
void vTaskDelayUntil(TickType_t *previous_wake, TickType_t increment);
uint32_t ulTaskNotifyTake(BaseType_t clear_on_exit, TickType_t wait_ticks);
void vTaskNotifyGiveFromISR(TaskHandle_t task, BaseType_t *higher_priority_woken);

#endif
