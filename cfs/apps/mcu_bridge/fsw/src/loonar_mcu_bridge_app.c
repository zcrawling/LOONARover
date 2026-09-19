/* Local ingress only; each role expires independently when its backend stops.
 */
#include "cfe.h"
#include "loonar_cfs_messages.h"
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>

static uint64_t MB_Millis(void) {
  struct timespec now;
  clock_gettime(CLOCK_MONOTONIC, &now);
  return (uint64_t)now.tv_sec * 1000 + (uint64_t)now.tv_nsec / 1000000;
}
static void MB_Put32(uint8_t *p, uint32_t v) {
  unsigned i;
  for (i = 0; i < 4; ++i)
    p[i] = (uint8_t)(v >> (8 * i));
}
static uint32_t MB_Get32(const uint8_t *p) {
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) |
         ((uint32_t)p[3] << 24);
}
void LNR_McuMain(void) {
  uint32 run = CFE_ES_RunStatus_APP_RUN;
  int fd = -1, i;
  struct sockaddr_un address;
  uint8_t raw[129];
  LOONAR_McuV2Tlm_t message[2];
  uint64_t seen[2] = {0, 0}, published = 0;
  const char *path = getenv("LOONAR_MCU_HEALTH_SOCKET");
  if (!path || !*path)
    path = "/run/loonar/mcu/health.sock";
  CFE_EVS_Register(NULL, 0, CFE_EVS_EventFilter_BINARY);
  memset(message, 0, sizeof(message));
  memset(&address, 0, sizeof(address));
  if (strlen(path) >= sizeof(address.sun_path))
    goto failed;
  address.sun_family = AF_UNIX;
  strcpy(address.sun_path, path);
  fd = socket(AF_UNIX, SOCK_DGRAM, 0);
  if (fd < 0 || fcntl(fd, F_SETFL, O_NONBLOCK) < 0)
    goto failed;
  /* RuntimeDirectory belongs to the service; do not bind in a public /tmp path.
   */
  if (unlink(path) < 0 && errno != ENOENT)
    goto failed;
  if (bind(fd, (struct sockaddr *)&address, sizeof(address)) < 0 ||
      chmod(path, 0660) < 0)
    goto failed;
  for (i = 0; i < 2; ++i) {
    CFE_MSG_Init(CFE_MSG_PTR(message[i].TelemetryHeader),
                 CFE_SB_ValueToMsgId(LOONAR_MCU_V2_TLM_MID_VALUE),
                 sizeof(message[i]));
    memcpy(message[i].Wire, "MCU2", 4);
    message[i].Wire[4] = (uint8_t)(i + 1);
    message[i].Wire[6] = 2;
    MB_Put32(message[i].Wire + 32, 0xffffffffU);
  }
  while (CFE_ES_RunLoop(&run)) {
    uint64_t now = MB_Millis();
    for (i = 0; i < 32; ++i) {
      ssize_t n = recv(fd, raw, sizeof(raw), 0);
      int role;
      if (n < 0)
        break;
      if (n != 128 || memcmp(raw, "MCU2", 4) || raw[4] < 1 || raw[4] > 2 ||
          raw[5] > 1 || raw[6] != 2 || raw[7] != 0)
        continue;
      role = raw[4] - 1;
      memcpy(message[role].Wire, raw, 128);
      seen[role] = now;
    }
    if (now - published >= 200) {
      for (i = 0; i < 2; ++i) {
        LOONAR_McuV2Tlm_t out = message[i];
        uint64_t delta = seen[i] ? now - seen[i] : 0xffffffffU;
        uint64_t age = (uint64_t)MB_Get32(out.Wire + 32) + delta;
        if (age > 0xffffffffU)
          age = 0xffffffffU;
        MB_Put32(out.Wire + 32, (uint32_t)age);
        if (age >= 500 || !seen[i])
          out.Wire[5] = 0;
        CFE_SB_TimeStampMsg(CFE_MSG_PTR(out.TelemetryHeader));
        CFE_SB_TransmitMsg(CFE_MSG_PTR(out.TelemetryHeader), true);
      }
      published = now;
    }
    OS_TaskDelay(20);
  }
  close(fd);
  unlink(path);
  CFE_ES_ExitApp(run);
  return;
failed:
  if (fd >= 0)
    close(fd);
  CFE_EVS_SendEvent(1, CFE_EVS_EventType_ERROR, "MCU ingress init failed: %s",
                    path);
  CFE_ES_ExitApp(CFE_ES_RunStatus_APP_ERROR);
}
