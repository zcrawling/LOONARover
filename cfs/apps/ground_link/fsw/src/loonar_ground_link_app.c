#include "cfe.h"
#include "loonar_cfs_messages.h"
#include "loonar_ground_wire.h"

#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

#define GL_PORT 7443
#define GL_PIPE_DEPTH 32
#define GL_RX_CAPACITY (2U * LOONAR_GL_MAX_FRAME)

typedef struct
{
    uint32 RunStatus;
    CFE_SB_PipeId_t Pipe;
    int Listener;
    int Client;
    uint8_t Rx[GL_RX_CAPACITY];
    size_t RxUsed;
    uint8_t CurrentMode;
} GL_AppData_t;
static GL_AppData_t GL;

static void
GL_CloseClient(
    void
    ){
    if (GL.Client >= 0)
        close(GL.Client);
    GL.Client = -1;
    GL.RxUsed = 0;
}
static bool
GL_SendAll(
    const uint8_t *data, size_t size
    ){
    size_t at = 0;
    while (at < size)
    {
        ssize_t n = send(GL.Client, data + at, size - at, MSG_NOSIGNAL);
        if (n < 0&&errno == EINTR)
            continue;
        if (n <= 0)
            return false;
        at += (size_t)n;
    }
    return true;
}
static bool
GL_SendFrame(
    uint16_t type, uint32_t sequence, const uint8_t *payload, uint32_t length
    ){
    uint8_t frame[LOONAR_GL_MAX_FRAME];
    size_t size;
    if (GL.Client < 0)
        return false;
    size = LOONAR_GL_Encode(frame, sizeof(frame), type, sequence, payload, length);
    return size > 0&&GL_SendAll(frame, size);
}

static bool
GL_PublishNoArgs(
    uint32_t mid, uint32_t sequence
    ){
    LOONAR_NoArgsCmd_t msg;
    memset(&msg, 0, sizeof(msg));
    CFE_MSG_Init(CFE_MSG_PTR(msg.CommandHeader), CFE_SB_ValueToMsgId(mid), sizeof(msg));
    msg.GroundSequence = sequence;
    return CFE_SB_TransmitMsg(CFE_MSG_PTR(msg.CommandHeader), true) == CFE_SUCCESS;
}
static bool
GL_PublishManual(
    const LOONAR_GL_FrameView_t *frame
    ){
    LOONAR_ManualCmd_t msg;
    if (frame->PayloadLength != 16)
    {
        return false;
    }
    memset(&msg, 0, sizeof(msg));
    CFE_MSG_Init(CFE_MSG_PTR(msg.CommandHeader), CFE_SB_ValueToMsgId(LOONAR_MANUAL_CMD_MID_VALUE), sizeof(msg));
    msg.GroundSequence = frame->Sequence;
    msg.LinearMps = LOONAR_GL_ReadDouble(frame->Payload);
    msg.AngularRadps = LOONAR_GL_ReadDouble(frame->Payload + 8);
    return CFE_SB_TransmitMsg(CFE_MSG_PTR(msg.CommandHeader), true) == CFE_SUCCESS;
}
static bool
GL_PublishActivity(
    const LOONAR_GL_FrameView_t *frame, uint32_t mid
    ){
    LOONAR_ActivityCmd_t msg;
    uint16_t length;
    if (frame->PayloadLength < 12)
        return false;
    length = LOONAR_GL_ReadU16(frame->Payload + 10);
    if (length > LOONAR_ACTIVITY_PARAMETER_MAX||frame->PayloadLength != 12U + (uint32_t)length)
        return false;
    memset(&msg, 0, sizeof(msg));
    CFE_MSG_Init(CFE_MSG_PTR(msg.CommandHeader), CFE_SB_ValueToMsgId(mid), sizeof(msg));
    msg.GroundSequence = frame->Sequence;
    msg.RequestId = LOONAR_GL_ReadU64(frame->Payload);
    msg.Opcode = LOONAR_GL_ReadU16(frame->Payload + 8);
    msg.ParameterLength = length;
    memcpy(msg.Parameters, frame->Payload + 12, length);
    return CFE_SB_TransmitMsg(CFE_MSG_PTR(msg.CommandHeader), true) == CFE_SUCCESS;
}
static void
GL_ReportBadCommand(
    const LOONAR_GL_FrameView_t *frame
    ){
    LOONAR_CommandResultTlm_t msg;
    memset(&msg, 0, sizeof(msg));
    CFE_MSG_Init(CFE_MSG_PTR(msg.TelemetryHeader), CFE_SB_ValueToMsgId(LOONAR_COMMAND_RESULT_TLM_MID_VALUE), sizeof(msg));
    msg.GroundSequence = frame->Sequence;
    msg.CommandType = frame->Type;
    msg.CfsReceived = 1;
    msg.CurrentMode = GL.CurrentMode;
    msg.ResultCode = LOONAR_RESULT_BAD_PAYLOAD;
    CFE_SB_TransmitMsg(CFE_MSG_PTR(msg.TelemetryHeader), true);
}
static void
GL_Dispatch(
    const LOONAR_GL_FrameView_t *frame
    ){
    bool accepted = false;
    switch (frame->Type){
    case LOONAR_GL_STOP_COMMAND: accepted = frame->PayloadLength == 0&&GL_PublishNoArgs(LOONAR_STOP_CMD_MID_VALUE, frame->Sequence);
        break;
    case LOONAR_GL_MANUAL_COMMAND: accepted = GL_PublishManual(frame);
        break;
    case LOONAR_GL_AUTO_COMMAND: accepted = frame->PayloadLength == 0&&GL_PublishNoArgs(LOONAR_AUTO_CMD_MID_VALUE, frame->Sequence);
        break;
    case LOONAR_GL_PAYLOAD_COMMAND: accepted = GL_PublishActivity(frame, LOONAR_PAYLOAD_CMD_MID_VALUE);
        break;
    case LOONAR_GL_REACTION_COMMAND: accepted = GL_PublishActivity(frame, LOONAR_REACTION_CMD_MID_VALUE);
        break;
    default: break;
    }
    if (!accepted)
        GL_ReportBadCommand(frame);
}

static void
GL_ServiceNetwork(
    void
    ){
    if (GL.Client < 0)
    {
        GL.Client = accept(GL.Listener, NULL, NULL);
        if (GL.Client >= 0)
        {
            int flags = fcntl(GL.Client, F_GETFL, 0);
            if (flags >= 0)
                fcntl(GL.Client, F_SETFL, flags | O_NONBLOCK);
        }
        return;
    }
    for (;;)
    {
        ssize_t n;
        if (GL.RxUsed == sizeof(GL.Rx))
        {
            GL_CloseClient();
            return;
        }
        n = recv(GL.Client, GL.Rx + GL.RxUsed, sizeof(GL.Rx) - GL.RxUsed, 0);
        if (n < 0&&(errno == EAGAIN||errno == EWOULDBLOCK))
            break;
        if (n < 0&&errno == EINTR)
            continue;
        if (n <= 0)
        {
            GL_CloseClient();
            return;
        }
        GL.RxUsed += (size_t)n;
    }
    while (GL.RxUsed > 0)
    {
        LOONAR_GL_FrameView_t frame;
        size_t consumed = 0;
        int result = LOONAR_GL_DecodeOne(GL.Rx, GL.RxUsed, &frame, &consumed);
        if (result == 0)
            break;
        if (result < 0)
        {
            GL_CloseClient();
            return;
        }
        GL_Dispatch(&frame);
        memmove(GL.Rx, GL.Rx + consumed, GL.RxUsed - consumed);
        GL.RxUsed -= consumed;
    }
}

static size_t
GL_BoundedLength(
    const char *text, size_t maximum
    ){
    size_t length = 0;
    while (length < maximum&&text[length] != '\0')
        ++length;
    return length;
}
static void
GL_ForwardTelemetry(
    const CFE_SB_Buffer_t *buffer
    ){
    CFE_SB_MsgId_t id;
    uint8_t payload[LOONAR_GL_MAX_PAYLOAD];
    CFE_MSG_GetMsgId(&buffer->Msg, &id);
    if (CFE_SB_MsgId_Equal(id, CFE_SB_ValueToMsgId(LOONAR_COMMAND_RESULT_TLM_MID_VALUE)))
    {
        const LOONAR_CommandResultTlm_t *m = (const LOONAR_CommandResultTlm_t *)buffer;
        LOONAR_GL_WriteU32(payload, m->GroundSequence);
        LOONAR_GL_WriteU16(payload + 4, m->CommandType);
        payload[6] = m->CfsReceived;
        payload[7] = m->AdapterForwarded;
        payload[8] = m->CurrentMode;
        payload[9] = m->ResultCode;
        if (!GL_SendFrame(LOONAR_GL_COMMAND_RESULT, m->GroundSequence, payload, 10))
            GL_CloseClient();
    }
    else if (CFE_SB_MsgId_Equal(id, CFE_SB_ValueToMsgId(LOONAR_GATEWAY_STATUS_TLM_MID_VALUE)))
    {
        const LOONAR_GatewayStatusTlm_t *m = (const LOONAR_GatewayStatusTlm_t *)buffer;
        GL.CurrentMode = m->Mode;
        payload[0] = m->Mode;
        payload[1] = m->LastSource;
        payload[2] = m->HasLastCommand;
        payload[3] = m->Reason;
        LOONAR_GL_WriteDouble(payload + 4, m->LastLinearMps);
        LOONAR_GL_WriteDouble(payload + 12, m->LastAngularRadps);
        if (!GL_SendFrame(LOONAR_GL_GATEWAY_STATUS, 0, payload, 20))
            GL_CloseClient();
    }
    else if (CFE_SB_MsgId_Equal(id, CFE_SB_ValueToMsgId(LOONAR_VEHICLE_STATUS_TLM_MID_VALUE)))
    {
        const LOONAR_VehicleStatusTlm_t *m = (const LOONAR_VehicleStatusTlm_t *)buffer;
        size_t at = 0, i;
        LOONAR_GL_WriteU64(payload + at, m->TimestampMs);
        at += 8;
        LOONAR_GL_WriteU32(payload + at, m->ValidFlags);
        at += 4;
        for (i = 0; i < 10; ++i)
        {
            const double values[10] = {
                m->BatteryVoltage, m->BatteryPercent, m->OdomX, m->OdomY, m->OdomYaw, m->LinearMps, m->AngularRadps, m->ImuRoll, m->ImuPitch, m->ImuYaw
            };
            LOONAR_GL_WriteDouble(payload + at, values[i]);
            at += 8;
        }
        if (!GL_SendFrame(LOONAR_GL_VEHICLE_STATUS, 0, payload, (uint32_t)at))
            GL_CloseClient();
    }
    else if (CFE_SB_MsgId_Equal(id, CFE_SB_ValueToMsgId(LOONAR_MCU_STATUS_TLM_MID_VALUE)))
    {
        const LOONAR_McuStatusTlm_t *m = (const LOONAR_McuStatusTlm_t *)buffer;
        size_t at = 0;
        LOONAR_GL_WriteU64(payload + at, m->TimestampMs);
        at += 8;
        LOONAR_GL_WriteU64(payload + at, m->UptimeMs);
        at += 8;
        LOONAR_GL_WriteDouble(payload + at, m->BoardTemperatureC);
        at += 8;
        LOONAR_GL_WriteU16(payload + at, m->McuState);
        at += 2;
        LOONAR_GL_WriteU32(payload + at, m->InhibitFlags);
        at += 4;
        LOONAR_GL_WriteDouble(payload + at, m->AppliedLinearMps);
        at += 8;
        LOONAR_GL_WriteDouble(payload + at, m->AppliedAngularRadps);
        at += 8;
        LOONAR_GL_WriteU32(payload + at, m->RxErrorCount);
        at += 4;
        if (!GL_SendFrame(LOONAR_GL_MCU_STATUS, 0, payload, (uint32_t)at))
            GL_CloseClient();
    }
    else if (CFE_SB_MsgId_Equal(id, CFE_SB_ValueToMsgId(LOONAR_DEVICE_STATUS_TLM_MID_VALUE)))
    {
        const LOONAR_DeviceStatusTlm_t *m = (const LOONAR_DeviceStatusTlm_t *)buffer;
        size_t at = 0, i;
        LOONAR_GL_WriteU64(payload + at, m->TimestampMs);
        at += 8;
        payload[at++] = LOONAR_DEVICE_COUNT;
        for (i = 0; i < LOONAR_DEVICE_COUNT; ++i)
        {
            payload[at++] = m->Device[i].State;
            LOONAR_GL_WriteU64(payload + at, m->Device[i].LastUpdateMs);
            at += 8;
        }
        if (!GL_SendFrame(LOONAR_GL_DEVICE_STATUS, 0, payload, (uint32_t)at))
            GL_CloseClient();
    }
    else if (CFE_SB_MsgId_Equal(id, CFE_SB_ValueToMsgId(LOONAR_EVENT_TLM_MID_VALUE)))
    {
        const LOONAR_EventTlm_t *m = (const LOONAR_EventTlm_t *)buffer;
        size_t at = 0, source_length = GL_BoundedLength(m->Source, LOONAR_EVENT_SOURCE_MAX), text_length = GL_BoundedLength(m->Text, LOONAR_EVENT_TEXT_MAX);
        LOONAR_GL_WriteU64(payload + at, m->TimestampMs);
        at += 8;
        payload[at++] = m->Severity;
        LOONAR_GL_WriteU32(payload + at, m->Code);
        at += 4;
        payload[at++] = (uint8_t)source_length;
        LOONAR_GL_WriteU16(payload + at, (uint16_t)text_length);
        at += 2;
        memcpy(payload + at, m->Source, source_length);
        at += source_length;
        memcpy(payload + at, m->Text, text_length);
        at += text_length;
        if (!GL_SendFrame(LOONAR_GL_EVENT, 0, payload, (uint32_t)at))
            GL_CloseClient();
    }
}

static CFE_Status_t
GL_Init(
    void
    ){
    static const uint32_t telemetry_mids[] = {
        LOONAR_COMMAND_RESULT_TLM_MID_VALUE, LOONAR_GATEWAY_STATUS_TLM_MID_VALUE, LOONAR_VEHICLE_STATUS_TLM_MID_VALUE, LOONAR_MCU_STATUS_TLM_MID_VALUE, LOONAR_DEVICE_STATUS_TLM_MID_VALUE, LOONAR_EVENT_TLM_MID_VALUE
    };
    struct sockaddr_in address;
    int one = 1, flags;
    size_t i;
    CFE_Status_t status;
    memset(&GL, 0, sizeof(GL));
    GL.Listener = -1;
    GL.Client = -1;
    GL.CurrentMode = LOONAR_MODE_STOP;
    GL.RunStatus = CFE_ES_RunStatus_APP_RUN;
    status = CFE_EVS_Register(NULL, 0, CFE_EVS_EventFilter_BINARY);
    if (status != CFE_SUCCESS)
        return status;
    status = CFE_SB_CreatePipe(&GL.Pipe, GL_PIPE_DEPTH, "LNR_GROUND");
    if (status != CFE_SUCCESS)
        return status;
    for (i = 0; i < sizeof(telemetry_mids) / sizeof(telemetry_mids[0]); ++i)
    {
        status = CFE_SB_Subscribe(CFE_SB_ValueToMsgId(telemetry_mids[i]), GL.Pipe);
        if (status != CFE_SUCCESS)
            return status;
    }
    GL.Listener = socket(AF_INET, SOCK_STREAM, 0);
    if (GL.Listener < 0)
        return CFE_STATUS_EXTERNAL_RESOURCE_FAIL;
    setsockopt(GL.Listener, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));
    memset(&address, 0, sizeof(address));
    address.sin_family = AF_INET;
    address.sin_port = htons(GL_PORT);
    address.sin_addr.s_addr = htonl(INADDR_ANY);
    if (bind(GL.Listener, (struct sockaddr *)&address, sizeof(address)) < 0||listen(GL.Listener, 1) < 0)
        return CFE_STATUS_EXTERNAL_RESOURCE_FAIL;
    flags = fcntl(GL.Listener, F_GETFL, 0);
    if (flags < 0||fcntl(GL.Listener, F_SETFL, flags | O_NONBLOCK) < 0)
        return CFE_STATUS_EXTERNAL_RESOURCE_FAIL;
    CFE_EVS_SendEvent(1, CFE_EVS_EventType_INFORMATION, "LOONAR GroundLink listening on TCP %d", GL_PORT);
    return CFE_SUCCESS;
}

void
LNR_GroundMain(
    void
    ){
    CFE_SB_Buffer_t *buffer;
    CFE_Status_t status = GL_Init();
    if (status != CFE_SUCCESS)
        GL.RunStatus = CFE_ES_RunStatus_APP_ERROR;
    while (CFE_ES_RunLoop(&GL.RunStatus))
    {
        while (CFE_SB_ReceiveBuffer(&buffer, GL.Pipe, CFE_SB_POLL) == CFE_SUCCESS)
            GL_ForwardTelemetry(buffer);
        GL_ServiceNetwork();
        OS_TaskDelay(10);
    }
    GL_CloseClient();
    if (GL.Listener >= 0)
        close(GL.Listener);
    CFE_ES_ExitApp(GL.RunStatus);
}
