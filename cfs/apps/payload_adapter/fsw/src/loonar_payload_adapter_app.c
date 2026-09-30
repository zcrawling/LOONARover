#include "cfe.h"
#include "loonar_cfs_messages.h"

#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

#define PA_PIPE_DEPTH 8
#define PA_DEFAULT_SOCKET "/run/loonar/payload-pca.sock"

typedef struct
{
    uint32 RunStatus;
    CFE_SB_PipeId_t Pipe;
    int SocketFd;
    char SocketPath[sizeof(((struct sockaddr_un *)0)->sun_path)];
} PA_AppData_t;

static PA_AppData_t PA;

static void PA_Put16(uint8_t *p, uint16_t value)
{
    p[0] = (uint8_t)value;
    p[1] = (uint8_t)(value >> 8U);
}

static void PA_Put64(uint8_t *p, uint64_t value)
{
    unsigned shift;
    for (shift = 0; shift < 64; shift += 8)
        *p++ = (uint8_t)(value >> shift);
}

static void PA_Close(void)
{
    if (PA.SocketFd >= 0)
        close(PA.SocketFd);
    PA.SocketFd = -1;
}

static bool PA_Connect(void)
{
    struct sockaddr_un address;
    int flags;
    if (PA.SocketFd >= 0)
        return true;
    PA.SocketFd = socket(AF_UNIX, SOCK_SEQPACKET, 0);
    if (PA.SocketFd < 0)
        return false;
    memset(&address, 0, sizeof(address));
    address.sun_family = AF_UNIX;
    strncpy(address.sun_path, PA.SocketPath, sizeof(address.sun_path) - 1);
    if (connect(PA.SocketFd, (struct sockaddr *)&address, sizeof(address)) < 0)
    {
        PA_Close();
        return false;
    }
    flags = fcntl(PA.SocketFd, F_GETFL, 0);
    if (flags < 0 || fcntl(PA.SocketFd, F_SETFL, flags | O_NONBLOCK) < 0)
    {
        PA_Close();
        return false;
    }
    return true;
}

static void PA_Event(const char *text, uint8_t severity, uint32_t code)
{
    LOONAR_EventTlm_t message;
    CFE_TIME_SysTime_t now = CFE_TIME_GetTime();
    memset(&message, 0, sizeof(message));
    CFE_MSG_Init(CFE_MSG_PTR(message.TelemetryHeader),
                 CFE_SB_ValueToMsgId(LOONAR_EVENT_TLM_MID_VALUE), sizeof(message));
    message.TimestampMs = (uint64_t)now.Seconds * 1000U + now.Subseconds / 4294967U;
    message.Severity = severity;
    message.Code = code;
    strncpy(message.Source, "payload-pca", sizeof(message.Source) - 1);
    strncpy(message.Text, text, sizeof(message.Text) - 1);
    CFE_SB_TransmitMsg(CFE_MSG_PTR(message.TelemetryHeader), true);
}

static void PA_Command(const LOONAR_ActivityCmd_t *command)
{
    uint8_t bytes[12 + LOONAR_ACTIVITY_PARAMETER_MAX];
    size_t total;
    if (command->Opcode != 1U && command->Opcode != 2U)
    {
        PA_Event("ERROR,0,COMMAND,opcode_must_be_1_or_2", 2, 0x5002);
        return;
    }
    if (!PA_Connect())
    {
        PA_Event("ERROR,0,TRANSPORT,payload_service_offline", 2, 0x5003);
        return;
    }
    PA_Put64(bytes, command->RequestId);
    PA_Put16(bytes + 8, command->Opcode);
    PA_Put16(bytes + 10, command->ParameterLength);
    if (command->ParameterLength > 0)
        memcpy(bytes + 12, command->Parameters, command->ParameterLength);
    total = 12U + command->ParameterLength;
    if (send(PA.SocketFd, bytes, total, MSG_NOSIGNAL) != (ssize_t)total)
    {
        PA_Close();
        PA_Event("ERROR,0,TRANSPORT,send_failed", 2, 0x5004);
    }
}

static void PA_Read(void)
{
    char text[LOONAR_EVENT_TEXT_MAX];
    ssize_t count;
    for (;;)
    {
        count = recv(PA.SocketFd, text, sizeof(text) - 1, 0);
        if (count < 0 && (errno == EAGAIN || errno == EWOULDBLOCK))
            return;
        if (count < 0 && errno == EINTR)
            continue;
        if (count <= 0)
        {
            PA_Close();
            return;
        }
        text[count] = '\0';
        PA_Event(text, strncmp(text, "ERROR,", 6) == 0 ? 2 : 0,
                 strncmp(text, "PCA,", 4) == 0 ? 0x5001 : 0x5000);
    }
}

static CFE_Status_t PA_Init(void)
{
    const char *configured = getenv("LOONAR_PAYLOAD_PCA_SOCKET");
    CFE_Status_t status;
    memset(&PA, 0, sizeof(PA));
    PA.SocketFd = -1;
    PA.RunStatus = CFE_ES_RunStatus_APP_RUN;
    if (configured == NULL || configured[0] == '\0')
        configured = PA_DEFAULT_SOCKET;
    if (strlen(configured) >= sizeof(PA.SocketPath))
        return CFE_ES_BAD_ARGUMENT;
    strcpy(PA.SocketPath, configured);
    status = CFE_EVS_Register(NULL, 0, CFE_EVS_EventFilter_BINARY);
    if (status != CFE_SUCCESS)
        return status;
    status = CFE_SB_CreatePipe(&PA.Pipe, PA_PIPE_DEPTH, "LNR_PAYLOAD");
    if (status != CFE_SUCCESS)
        return status;
    status = CFE_SB_Subscribe(CFE_SB_ValueToMsgId(LOONAR_PAYLOAD_EXEC_CMD_MID_VALUE), PA.Pipe);
    if (status == CFE_SUCCESS)
        CFE_EVS_SendEvent(1, CFE_EVS_EventType_INFORMATION,
                          "LOONAR PayloadAdapter socket=%s", PA.SocketPath);
    return status;
}

void LNR_PayloadMain(void)
{
    CFE_SB_Buffer_t *buffer;
    CFE_Status_t status = PA_Init();
    if (status != CFE_SUCCESS)
        PA.RunStatus = CFE_ES_RunStatus_APP_ERROR;
    while (CFE_ES_RunLoop(&PA.RunStatus))
    {
        while (CFE_SB_ReceiveBuffer(&buffer, PA.Pipe, CFE_SB_POLL) == CFE_SUCCESS)
            PA_Command((const LOONAR_ActivityCmd_t *)buffer);
        if (PA_Connect())
            PA_Read();
        OS_TaskDelay(10);
    }
    PA_Close();
    CFE_ES_ExitApp(PA.RunStatus);
}
