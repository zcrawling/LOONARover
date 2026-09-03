#pragma once

#include "cfe.h"
#include <stdint.h>

/* Mission may override these values if its global MID allocation changes. */
#define LOONAR_STOP_CMD_MID_VALUE          0x19A0
#define LOONAR_MANUAL_CMD_MID_VALUE        0x19A1
#define LOONAR_AUTO_CMD_MID_VALUE          0x19A2
#define LOONAR_PAYLOAD_CMD_MID_VALUE       0x19A3
#define LOONAR_REACTION_CMD_MID_VALUE      0x19A4
#define LOONAR_PAYLOAD_EXEC_CMD_MID_VALUE  0x19A5
#define LOONAR_REACTION_EXEC_CMD_MID_VALUE 0x19A6
#define LOONAR_COMMAND_RESULT_TLM_MID_VALUE 0x09A0
#define LOONAR_GATEWAY_STATUS_TLM_MID_VALUE 0x09A1
#define LOONAR_VEHICLE_STATUS_TLM_MID_VALUE 0x09A2
#define LOONAR_MCU_STATUS_TLM_MID_VALUE     0x09A3
#define LOONAR_DEVICE_STATUS_TLM_MID_VALUE  0x09A4
#define LOONAR_EVENT_TLM_MID_VALUE          0x09A5

#define LOONAR_ACTIVITY_PARAMETER_MAX 64
#define LOONAR_EVENT_SOURCE_MAX 24
#define LOONAR_EVENT_TEXT_MAX 128
#define LOONAR_DEVICE_COUNT 7

typedef enum
{
    LOONAR_MODE_AUTO = 1,
    LOONAR_MODE_MANUAL = 2,
    LOONAR_MODE_STOP = 3,
    LOONAR_MODE_PAYLOAD = 4,
    LOONAR_MODE_REACTION = 5
} LOONAR_Mode_t;

typedef struct
{
    CFE_MSG_CommandHeader_t CommandHeader;
    uint32_t GroundSequence;
} LOONAR_NoArgsCmd_t;

typedef struct
{
    CFE_MSG_CommandHeader_t CommandHeader;
    uint32_t GroundSequence;
    double LinearMps;
    double AngularRadps;
} LOONAR_ManualCmd_t;

typedef struct
{
    CFE_MSG_CommandHeader_t CommandHeader;
    uint32_t GroundSequence;
    uint64_t RequestId;
    uint16_t Opcode;
    uint16_t ParameterLength;
    uint8_t Parameters[LOONAR_ACTIVITY_PARAMETER_MAX];
} LOONAR_ActivityCmd_t;

typedef struct
{
    CFE_MSG_TelemetryHeader_t TelemetryHeader;
    uint32_t GroundSequence;
    uint16_t CommandType;
    uint8_t CfsReceived;
    uint8_t AdapterForwarded;
    uint8_t CurrentMode;
    uint8_t ResultCode;
} LOONAR_CommandResultTlm_t;

typedef struct
{
    CFE_MSG_TelemetryHeader_t TelemetryHeader;
    uint8_t Mode;
    uint8_t LastSource;
    uint8_t HasLastCommand;
    uint8_t Reason;
    double LastLinearMps;
    double LastAngularRadps;
} LOONAR_GatewayStatusTlm_t;

/* valid_flags tells the receiver which optional numeric fields are meaningful. */
typedef struct
{
    CFE_MSG_TelemetryHeader_t TelemetryHeader;
    uint64_t TimestampMs;
    uint32_t ValidFlags;
    double BatteryVoltage;
    double BatteryPercent;
    double OdomX;
    double OdomY;
    double OdomYaw;
    double LinearMps;
    double AngularRadps;
    double ImuRoll;
    double ImuPitch;
    double ImuYaw;
} LOONAR_VehicleStatusTlm_t;

typedef struct
{
    CFE_MSG_TelemetryHeader_t TelemetryHeader;
    uint64_t TimestampMs;
    uint64_t UptimeMs;
    double BoardTemperatureC;
    uint16_t McuState;
    uint32_t InhibitFlags;
    double AppliedLinearMps;
    double AppliedAngularRadps;
    uint32_t RxErrorCount;
} LOONAR_McuStatusTlm_t;

typedef enum
{
    LOONAR_DEVICE_IMU = 0,
    LOONAR_DEVICE_MOTOR = 1,
    LOONAR_DEVICE_PAYLOAD_SENSOR = 2,
    LOONAR_DEVICE_LIDAR = 3,
    LOONAR_DEVICE_CAMERA = 4,
    LOONAR_DEVICE_MCU_LINK = 5,
    LOONAR_DEVICE_WIFI = 6
} LOONAR_DeviceId_t;

typedef enum
{
    LOONAR_DEVICE_UNKNOWN = 0,
    LOONAR_DEVICE_CONNECTED = 1,
    LOONAR_DEVICE_DISCONNECTED = 2,
    LOONAR_DEVICE_ERROR = 3
} LOONAR_DeviceState_t;

typedef struct
{
    uint8_t State;
    uint64_t LastUpdateMs;
} LOONAR_DeviceEntry_t;

typedef struct
{
    CFE_MSG_TelemetryHeader_t TelemetryHeader;
    uint64_t TimestampMs;
    LOONAR_DeviceEntry_t Device[LOONAR_DEVICE_COUNT];
} LOONAR_DeviceStatusTlm_t;

typedef struct
{
    CFE_MSG_TelemetryHeader_t TelemetryHeader;
    uint64_t TimestampMs;
    uint8_t Severity;
    uint32_t Code;
    char Source[LOONAR_EVENT_SOURCE_MAX];
    char Text[LOONAR_EVENT_TEXT_MAX];
} LOONAR_EventTlm_t;

enum
{
    LOONAR_RESULT_OK = 0,
    LOONAR_RESULT_BAD_PAYLOAD = 1,
    LOONAR_RESULT_GATEWAY_DISCONNECTED = 2,
    LOONAR_RESULT_NOT_IMPLEMENTED = 3,
    LOONAR_RESULT_INTERNAL_ERROR = 4
};
