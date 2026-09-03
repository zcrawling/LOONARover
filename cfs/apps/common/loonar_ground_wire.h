#pragma once
#include <stddef.h>
#include <stdint.h>

#define LOONAR_GL_MAGIC 0x314B4E4CU
#define LOONAR_GL_VERSION 1U
#define LOONAR_GL_HEADER_SIZE 16U
#define LOONAR_GL_MAX_PAYLOAD 512U
#define LOONAR_GL_MAX_FRAME (LOONAR_GL_HEADER_SIZE + LOONAR_GL_MAX_PAYLOAD)

#define LOONAR_GL_STOP_COMMAND 0x0001U
#define LOONAR_GL_MANUAL_COMMAND 0x0002U
#define LOONAR_GL_AUTO_COMMAND 0x0003U
#define LOONAR_GL_PAYLOAD_COMMAND 0x0004U
#define LOONAR_GL_REACTION_COMMAND 0x0005U
#define LOONAR_GL_COMMAND_RESULT 0x8001U
#define LOONAR_GL_GATEWAY_STATUS 0x8002U
#define LOONAR_GL_VEHICLE_STATUS 0x8003U
#define LOONAR_GL_MCU_STATUS 0x8004U
#define LOONAR_GL_DEVICE_STATUS 0x8005U
#define LOONAR_GL_EVENT 0x8006U

typedef struct
{
    uint16_t Type;
    uint32_t Sequence;
    const uint8_t *Payload;
    uint32_t PayloadLength;
} LOONAR_GL_FrameView_t;

int LOONAR_GL_DecodeOne(const uint8_t *data, size_t size, LOONAR_GL_FrameView_t *frame, size_t *consumed);
size_t LOONAR_GL_Encode(uint8_t *out, size_t capacity, uint16_t type, uint32_t sequence,
                        const uint8_t *payload, uint32_t payload_length);
uint16_t LOONAR_GL_ReadU16(const uint8_t *p);
uint32_t LOONAR_GL_ReadU32(const uint8_t *p);
uint64_t LOONAR_GL_ReadU64(const uint8_t *p);
double LOONAR_GL_ReadDouble(const uint8_t *p);
void LOONAR_GL_WriteU16(uint8_t *p, uint16_t value);
void LOONAR_GL_WriteU32(uint8_t *p, uint32_t value);
void LOONAR_GL_WriteU64(uint8_t *p, uint64_t value);
void LOONAR_GL_WriteDouble(uint8_t *p, double value);
