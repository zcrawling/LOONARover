#include "cfe.h"
#include "loonar_cfs_messages.h"
#include "loonar_ground_wire.h"

#include <errno.h>
#include <fcntl.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

#define VA_PIPE_DEPTH 32
#define VA_GATEWAY_MAGIC 0x4C4E5247U
#define VA_GATEWAY_VERSION 1U
#define VA_GATEWAY_HEADER 12U
#define VA_GATEWAY_STATUS_TYPE 7U
#define VA_GATEWAY_VEHICLE_STATUS_TYPE 9U
#define VA_GATEWAY_SOCKET "/run/loonar/vehicle-gateway/cfs.sock"

typedef struct {
    uint32 RunStatus;
    CFE_SB_PipeId_t Pipe;
    int GatewayFd;
    uint8_t Mode;
    char GatewayPath[sizeof(((struct sockaddr_un *) 0)->sun_path)];
    LOONAR_GatewayStatusTlm_t LastStatus;
    bool HasStatus;
    uint16_t StatusTicks;
} VA_AppData_t;
static VA_AppData_t VA;

static void
VA_Put16(
    uint8_t *p, uint16_t v
    ){
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8U);
}
static void
VA_Put32(
    uint8_t *p, uint32_t v
    ){
    unsigned s;
    for (s = 0; s < 32; s += 8)
        *p++ = (uint8_t)(v >> s);
}
static uint16_t
VA_Get16(
    const uint8_t *p
    ){
    return (uint16_t)p[0] | ((uint16_t)p[1] << 8U);
}
static uint32_t
VA_Get32(
    const uint8_t *p
    ){
    uint32_t v = 0;
    unsigned s;
    for (s = 0; s < 32; s += 8)
        v |= (uint32_t)(*p++) << s;
    return v;
}
static uint64_t
VA_Get64(
    const uint8_t *p
    ){
    uint64_t v = 0;
    unsigned s;
    for (s = 0; s < 64; s += 8)
        v |= (uint64_t)(*p++) << s;
    return v;
}
static void
VA_PutDouble(
    uint8_t *p, double value
    ){
    uint64_t bits;
    unsigned s;
    memcpy(&bits, &value, sizeof(bits));
    for (s = 0; s < 64; s += 8)
        *p++ = (uint8_t)(bits >> s);
}
static double
VA_GetDouble(
    const uint8_t *p
    ){
    uint64_t bits = 0;
    double value;
    unsigned s;
    for (s = 0; s < 64; s += 8)
        bits |= (uint64_t)(*p++) << s;
    memcpy(&value, &bits, sizeof(value));
    return value;
}
static void
VA_Close(
    void
    ){
    if (VA.GatewayFd >= 0)
        close(VA.GatewayFd);
    VA.GatewayFd = -1;
}
static bool
VA_SendPacket(
    uint16_t type, const uint8_t *payload, uint32_t length
    ){
    uint8_t bytes[64];
    size_t total = VA_GATEWAY_HEADER + (size_t)length;
    if (VA.GatewayFd < 0||total > sizeof(bytes))
        return false;
    VA_Put32(bytes, VA_GATEWAY_MAGIC);
    VA_Put16(bytes + 4, VA_GATEWAY_VERSION);
    VA_Put16(bytes + 6, type);
    VA_Put32(bytes + 8, length);
    if (length > 0)
        memcpy(bytes + VA_GATEWAY_HEADER, payload, length);
    if (send(VA.GatewayFd, bytes, total, MSG_NOSIGNAL) != (ssize_t)total)
    {
        VA_Close();
        return false;
    }
    return true;
}
static bool
VA_Connect(
    void
    ){
    struct sockaddr_un address;
    int flags;
    if (VA.GatewayFd >= 0)
        return true;
    VA.GatewayFd = socket(AF_UNIX, SOCK_SEQPACKET, 0);
    if (VA.GatewayFd < 0)
        return false;
    memset(&address, 0, sizeof(address));
    address.sun_family = AF_UNIX;
    strncpy(address.sun_path, VA.GatewayPath, sizeof(address.sun_path) - 1);
    if (connect(VA.GatewayFd, (struct sockaddr *)&address, sizeof(address)) < 0)
    {
        VA_Close();
        return false;
    }
    flags = fcntl(VA.GatewayFd, F_GETFL, 0);
    if (flags < 0||fcntl(VA.GatewayFd, F_SETFL, flags | O_NONBLOCK) < 0)
    {
        VA_Close();
        return false;
    }
    return VA_SendPacket(1, NULL, 0);
}

static void
VA_Result(
    uint32_t sequence, uint16_t command, bool forwarded, uint8_t result
    ){
    LOONAR_CommandResultTlm_t msg;
    memset(&msg, 0, sizeof(msg));
    CFE_MSG_Init(CFE_MSG_PTR(msg.TelemetryHeader), CFE_SB_ValueToMsgId(LOONAR_COMMAND_RESULT_TLM_MID_VALUE), sizeof(msg));
    msg.GroundSequence = sequence;
    msg.CommandType = command;
    msg.CfsReceived = 1;
    msg.AdapterForwarded = forwarded?1:0;
    msg.CurrentMode = VA.Mode;
    msg.ResultCode = result;
    CFE_SB_TransmitMsg(CFE_MSG_PTR(msg.TelemetryHeader), true);
}
static bool
VA_Select(
    uint16_t type, uint8_t mode
    ){
    bool sent = VA_Connect()&&VA_SendPacket(type, NULL, 0);
    if (sent)
        VA.Mode = mode;
    return sent;
}
static bool
VA_Stop(
    void
    ){
    return VA_Select(3, LOONAR_MODE_STOP);
}
static void
VA_Manual(
    const LOONAR_ManualCmd_t *cmd
    ){
    uint8_t payload[17];
    bool sent;
    payload[0] = 2;
    VA_PutDouble(payload + 1, cmd->LinearMps);
    VA_PutDouble(payload + 9, cmd->AngularRadps);
    sent = VA_Connect()&&VA_SendPacket(2, payload, sizeof(payload));
    if (sent)
        VA.Mode = LOONAR_MODE_MANUAL;
    VA_Result(cmd->GroundSequence, 2, sent, sent?LOONAR_RESULT_OK:LOONAR_RESULT_GATEWAY_DISCONNECTED);
}
static void
VA_Activity(
    const LOONAR_ActivityCmd_t *cmd, bool reaction
    ){
    bool stopped = VA_Stop();
    bool selected = stopped&&VA_Select(reaction?6:5, reaction?LOONAR_MODE_REACTION:LOONAR_MODE_PAYLOAD);
    bool routed = false;
    uint8_t result;
    if (selected)
    {
        LOONAR_ActivityCmd_t exec = *cmd;
        CFE_MSG_Init(CFE_MSG_PTR(exec.CommandHeader), CFE_SB_ValueToMsgId(reaction?LOONAR_REACTION_EXEC_CMD_MID_VALUE:LOONAR_PAYLOAD_EXEC_CMD_MID_VALUE), sizeof(exec));
        routed = CFE_SB_TransmitMsg(CFE_MSG_PTR(exec.CommandHeader), true) == CFE_SUCCESS;
    }
    if (!selected)
        result = LOONAR_RESULT_GATEWAY_DISCONNECTED;
    else if (!routed)
        result = LOONAR_RESULT_INTERNAL_ERROR;
    else if (reaction)
        result = LOONAR_RESULT_NOT_IMPLEMENTED;
    else result = LOONAR_RESULT_OK;
    VA_Result(cmd->GroundSequence, reaction?LOONAR_GL_REACTION_COMMAND:LOONAR_GL_PAYLOAD_COMMAND, routed, result);
}

static void
VA_Command(
    const CFE_SB_Buffer_t *buffer
    ){
    CFE_SB_MsgId_t id;
    CFE_MSG_GetMsgId(&buffer->Msg, &id);
    if (CFE_SB_MsgId_Equal(id, CFE_SB_ValueToMsgId(LOONAR_STOP_CMD_MID_VALUE)))
    {
        const LOONAR_NoArgsCmd_t *m = (const LOONAR_NoArgsCmd_t *)buffer;
        bool sent = VA_Stop();
        VA_Result(m->GroundSequence, 1, sent, sent?LOONAR_RESULT_OK:LOONAR_RESULT_GATEWAY_DISCONNECTED);
    }
    else if (CFE_SB_MsgId_Equal(id, CFE_SB_ValueToMsgId(LOONAR_MANUAL_CMD_MID_VALUE)))
        VA_Manual((const LOONAR_ManualCmd_t *)buffer);
    else if (CFE_SB_MsgId_Equal(id, CFE_SB_ValueToMsgId(LOONAR_AUTO_CMD_MID_VALUE)))
    {
        const LOONAR_NoArgsCmd_t *m = (const LOONAR_NoArgsCmd_t *)buffer;
        bool sent = VA_Select(4, LOONAR_MODE_AUTO);
        VA_Result(m->GroundSequence, 3, sent, sent?LOONAR_RESULT_OK:LOONAR_RESULT_GATEWAY_DISCONNECTED);
    }
    else if (CFE_SB_MsgId_Equal(id, CFE_SB_ValueToMsgId(LOONAR_PAYLOAD_CMD_MID_VALUE)))
        VA_Activity((const LOONAR_ActivityCmd_t *)buffer, false);
    else if (CFE_SB_MsgId_Equal(id, CFE_SB_ValueToMsgId(LOONAR_REACTION_CMD_MID_VALUE)))
        VA_Activity((const LOONAR_ActivityCmd_t *)buffer, true);
}

static void
VA_PublishStatus(
    void
    ){
    if (VA.GatewayFd >= 0&&VA.HasStatus)
        CFE_SB_TransmitMsg(CFE_MSG_PTR(VA.LastStatus.TelemetryHeader), true);
}
static void
VA_ReadGateway(
    void
    ){
    uint8_t bytes[256];
    ssize_t n;
    for (;;)
    {
        n = recv(VA.GatewayFd, bytes, sizeof(bytes), 0);
        if (n < 0&&(errno == EAGAIN||errno == EWOULDBLOCK))
            return;
        if (n < 0&&errno == EINTR)
            continue;
        if (n <= 0)
        {
            VA_Close();
            return;
        }
        if ((size_t)n == VA_GATEWAY_HEADER + 19U&&VA_Get32(bytes) == VA_GATEWAY_MAGIC&&VA_Get16(bytes + 4) == VA_GATEWAY_VERSION&&VA_Get16(bytes + 6) == VA_GATEWAY_STATUS_TYPE&&VA_Get32(bytes + 8) == 19)
        {
            const uint8_t *p = bytes + VA_GATEWAY_HEADER;
            memset(&VA.LastStatus, 0, sizeof(VA.LastStatus));
            CFE_MSG_Init(CFE_MSG_PTR(VA.LastStatus.TelemetryHeader), CFE_SB_ValueToMsgId(LOONAR_GATEWAY_STATUS_TLM_MID_VALUE), sizeof(VA.LastStatus));
            VA.LastStatus.Mode = p[0];
            VA.LastStatus.LastSource = p[1];
            VA.LastStatus.HasLastCommand = p[1] != 0;
            VA.LastStatus.LastLinearMps = VA_GetDouble(p + 2);
            VA.LastStatus.LastAngularRadps = VA_GetDouble(p + 10);
            VA.LastStatus.Reason = p[18];
            VA.Mode = VA.LastStatus.Mode;
            VA.HasStatus = true;
            VA.StatusTicks = 0;
            VA_PublishStatus();
        }
        else if ((size_t)n == VA_GATEWAY_HEADER + 92U&&VA_Get32(bytes) == VA_GATEWAY_MAGIC&&VA_Get16(bytes + 4) == VA_GATEWAY_VERSION&&VA_Get16(bytes + 6) == VA_GATEWAY_VEHICLE_STATUS_TYPE&&VA_Get32(bytes + 8) == 92U)
        {
            const uint8_t *p = bytes + VA_GATEWAY_HEADER;
            LOONAR_VehicleStatusTlm_t msg;
            memset(&msg, 0, sizeof(msg));
            CFE_MSG_Init(CFE_MSG_PTR(msg.TelemetryHeader), CFE_SB_ValueToMsgId(LOONAR_VEHICLE_STATUS_TLM_MID_VALUE), sizeof(msg));
            msg.TimestampMs = VA_Get64(p);
            msg.ValidFlags = VA_Get32(p + 8);
            msg.BatteryVoltage = VA_GetDouble(p + 12);
            msg.BatteryPercent = VA_GetDouble(p + 20);
            msg.OdomX = VA_GetDouble(p + 28);
            msg.OdomY = VA_GetDouble(p + 36);
            msg.OdomYaw = VA_GetDouble(p + 44);
            msg.LinearMps = VA_GetDouble(p + 52);
            msg.AngularRadps = VA_GetDouble(p + 60);
            msg.ImuRoll = VA_GetDouble(p + 68);
            msg.ImuPitch = VA_GetDouble(p + 76);
            msg.ImuYaw = VA_GetDouble(p + 84);
            CFE_SB_TransmitMsg(CFE_MSG_PTR(msg.TelemetryHeader), true);
        }
    }
}

static CFE_Status_t
VA_Init(
    void
    ){
    static const uint32_t mids[] = {
        LOONAR_STOP_CMD_MID_VALUE, LOONAR_MANUAL_CMD_MID_VALUE, LOONAR_AUTO_CMD_MID_VALUE, LOONAR_PAYLOAD_CMD_MID_VALUE, LOONAR_REACTION_CMD_MID_VALUE
    };
    const char *configured_path = getenv("LOONAR_GATEWAY_SOCKET");
    size_t i;
    CFE_Status_t status;
    memset(&VA, 0, sizeof(VA));
    if (configured_path == NULL||configured_path[0] == '\0')
        configured_path = VA_GATEWAY_SOCKET;
    if (strlen(configured_path) >= sizeof(VA.GatewayPath))
        return CFE_ES_BAD_ARGUMENT;
    strcpy(VA.GatewayPath, configured_path);
    VA.GatewayFd = -1;
    VA.Mode = LOONAR_MODE_STOP;
    VA.RunStatus = CFE_ES_RunStatus_APP_RUN;
    status = CFE_EVS_Register(NULL, 0, CFE_EVS_EventFilter_BINARY);
    if (status != CFE_SUCCESS)
        return status;
    status = CFE_SB_CreatePipe(&VA.Pipe, VA_PIPE_DEPTH, "LNR_VEH");
    if (status != CFE_SUCCESS)
        return status;
    for (i = 0; i < sizeof(mids) / sizeof(mids[0]); ++i)
    {
        status = CFE_SB_Subscribe(CFE_SB_ValueToMsgId(mids[i]), VA.Pipe);
        if (status != CFE_SUCCESS)
            return status;
    }
    CFE_EVS_SendEvent(1, CFE_EVS_EventType_INFORMATION, "LOONAR VehicleAdapter gateway=%s", VA.GatewayPath);
    return CFE_SUCCESS;
}

void
LNR_VehicleMain(
    void
    ){
    CFE_SB_Buffer_t *buffer;
    CFE_Status_t status = VA_Init();
    if (status != CFE_SUCCESS)
        VA.RunStatus = CFE_ES_RunStatus_APP_ERROR;
    while (CFE_ES_RunLoop(&VA.RunStatus))
    {
        while (CFE_SB_ReceiveBuffer(&buffer, VA.Pipe, CFE_SB_POLL) == CFE_SUCCESS)
            VA_Command(buffer);
        if (VA_Connect())
            VA_ReadGateway();
        if (++VA.StatusTicks >= 100)
        {
            VA.StatusTicks = 0;
            VA_PublishStatus();
        }
        OS_TaskDelay(10);
    }
    VA_Close();
    CFE_ES_ExitApp(VA.RunStatus);
}
