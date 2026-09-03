#include "loonar/control/freertos_app.h"

#include <string.h>

#include "FreeRTOS.h"
#include "queue.h"
#include "task.h"

#include "loonar/control/control_core.h"
#include "loonar/control/control_rx.h"
#include "loonar/control/control_tx.h"
#include "loonar/control/controller_tbd.h"
#include "loonar/wire/packet.h"

#define CONTROL_PERIOD_MS UINT32_C(10)
#define STATUS_PERIOD_MS UINT32_C(50)
#define RX_PERIOD_MS UINT32_C(1)
#define TASK_STACK_WORDS ((uint32_t)512)

typedef struct {
  LnrControlHal hal;
  LnrControlRx rx;
  LnrControlCore core;
  LnrControllerTbd controller;
  QueueHandle_t health_queue;
  QueueHandle_t motion_queue;
  QueueHandle_t status_queue;
  QueueHandle_t error_queue;
  TaskHandle_t rx_task;
  TaskHandle_t control_task;
  TaskHandle_t tx_task;
  StaticQueue_t health_queue_storage;
  StaticQueue_t motion_queue_storage;
  StaticQueue_t status_queue_storage;
  StaticQueue_t error_queue_storage;
  uint8_t health_queue_bytes[sizeof(LnrControlEvent)];
  uint8_t motion_queue_bytes[sizeof(LnrControlEvent)];
  uint8_t status_queue_bytes[sizeof(LnrMcuStatus)];
  uint8_t error_queue_bytes[sizeof(uint32_t)];
  StaticTask_t rx_task_storage;
  StaticTask_t control_task_storage;
  StaticTask_t tx_task_storage;
  StackType_t rx_stack[TASK_STACK_WORDS];
  StackType_t control_stack[TASK_STACK_WORDS];
  StackType_t tx_stack[TASK_STACK_WORDS];
  bool started;
} LnrControlApp;

static LnrControlApp app;

static uint32_t next_sequence(uint32_t sequence) {
  sequence += 1U;
  return sequence == 0U ? 1U : sequence;
}

static void publish_rx_error_count(void) {
  const uint32_t count = lnr_control_rx_error_count(&app.rx);
  (void)xQueueOverwrite(app.error_queue, &count);
}

static void dispatch_event(const LnrControlEvent *event) {
  if (event->type == LNR_CONTROL_EVENT_HEALTH) {
    (void)xQueueOverwrite(app.health_queue, event);
  } else if (event->type == LNR_CONTROL_EVENT_MOTION) {
    (void)xQueueOverwrite(app.motion_queue, event);
  }
}

static void rx_task_main(void *argument) {
  uint8_t bytes[64] = {0U};
  TickType_t last_wake = xTaskGetTickCount();
  (void)argument;
  for (;;) {
    size_t received = 0U;
    do {
      size_t offset = 0U;
      received = app.hal.uart_read(bytes, sizeof(bytes));
      while (offset < received) {
        size_t consumed = 0U;
        LnrControlEvent event;
        const LnrControlRxResult result = lnr_control_rx_push(
            &app.rx, bytes + offset, received - offset, app.hal.monotonic_ms(), &consumed,
            &event);
        offset += consumed;
        if (result == LNR_CONTROL_RX_EVENT) {
          dispatch_event(&event);
        }
        if (consumed == 0U) {
          break;
        }
      }
    } while (received == sizeof(bytes));
    lnr_control_rx_expire(&app.rx, app.hal.monotonic_ms());
    publish_rx_error_count();
    vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(RX_PERIOD_MS));
  }
}

static void control_task_main(void *argument) {
  TickType_t last_wake = xTaskGetTickCount();
  uint32_t last_status_ms = 0U;
  uint32_t rx_error_count = 0U;
  (void)argument;
  for (;;) {
    LnrControlEvent event;
    LnrControlOutput output;
    LnrMotorDuty motor_duty;
    LnrMcuStatus status;
    const uint32_t now_ms = app.hal.monotonic_ms();
    const int32_t temp_mdeg_c = app.hal.board_temp_mdeg_c();

    if (xQueueReceive(app.health_queue, &event, 0U) == pdPASS) {
      lnr_control_core_on_health(&app.core, event.received_at_ms);
    }
    if (xQueueReceive(app.motion_queue, &event, 0U) == pdPASS) {
      lnr_control_core_on_motion(&app.core, event.sequence, &event.data.motion);
    }
    (void)xQueueReceive(app.error_queue, &rx_error_count, 0U);

    output = lnr_control_core_step(&app.core, now_ms, temp_mdeg_c);
    motor_duty = lnr_controller_tbd_step(&app.controller, output.linear_velocity_mps,
                                         output.yaw_rate_radps);
    app.hal.apply_motor_duty(motor_duty.left_duty, motor_duty.right_duty);

    if ((uint32_t)(now_ms - last_status_ms) >= STATUS_PERIOD_MS) {
      lnr_control_core_make_status(&app.core, now_ms, temp_mdeg_c, rx_error_count, &status);
      (void)xQueueOverwrite(app.status_queue, &status);
      last_status_ms = now_ms;
    }
    vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(CONTROL_PERIOD_MS));
  }
}

static void tx_task_main(void *argument) {
  uint32_t sequence = 0U;
  uint8_t packet[LNR_WIRE_MAX_PACKET_SIZE] = {0U};
  (void)argument;
  for (;;) {
    LnrMcuStatus status;
    size_t packet_size = 0U;
    (void)xQueueReceive(app.status_queue, &status, portMAX_DELAY);
    sequence = next_sequence(sequence);
    if (lnr_control_tx_encode_status(&status, sequence, packet, sizeof(packet), &packet_size) ==
        LNR_WIRE_STATUS_OK) {
      (void)app.hal.uart_write(packet, packet_size);
    }
  }
}

static bool hal_is_complete(const LnrControlHal *hal) {
  return hal != NULL && hal->monotonic_ms != NULL && hal->board_temp_mdeg_c != NULL &&
         hal->uart_start != NULL && hal->uart_read != NULL && hal->uart_write != NULL &&
         hal->apply_motor_duty != NULL;
}

bool lnr_control_freertos_start(const LnrControlHal *hal) {
  if (!hal_is_complete(hal) || app.started) {
    return false;
  }
  memset(&app, 0, sizeof(app));
  app.hal = *hal;
  lnr_control_rx_init(&app.rx);
  lnr_control_core_init(&app.core);
  lnr_controller_tbd_init(&app.controller);

  app.health_queue = xQueueCreateStatic(1U, sizeof(LnrControlEvent), app.health_queue_bytes,
                                        &app.health_queue_storage);
  app.motion_queue = xQueueCreateStatic(1U, sizeof(LnrControlEvent), app.motion_queue_bytes,
                                        &app.motion_queue_storage);
  app.status_queue = xQueueCreateStatic(1U, sizeof(LnrMcuStatus), app.status_queue_bytes,
                                        &app.status_queue_storage);
  app.error_queue = xQueueCreateStatic(1U, sizeof(uint32_t), app.error_queue_bytes,
                                       &app.error_queue_storage);
  if (app.health_queue == NULL || app.motion_queue == NULL || app.status_queue == NULL ||
      app.error_queue == NULL || !app.hal.uart_start()) {
    return false;
  }

  app.rx_task = xTaskCreateStatic(rx_task_main, "control-rx", TASK_STACK_WORDS, NULL, 4U,
                                  app.rx_stack, &app.rx_task_storage);
  app.control_task = xTaskCreateStatic(control_task_main, "controller", TASK_STACK_WORDS, NULL,
                                       3U, app.control_stack, &app.control_task_storage);
  app.tx_task = xTaskCreateStatic(tx_task_main, "control-tx", TASK_STACK_WORDS, NULL, 2U,
                                  app.tx_stack, &app.tx_task_storage);
  app.started = app.rx_task != NULL && app.control_task != NULL && app.tx_task != NULL;
  return app.started;
}
