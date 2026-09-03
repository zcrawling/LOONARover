#include "loonar_ground_wire.h"
#include <string.h>

uint16_t
LOONAR_GL_ReadU16(
    const uint8_t *p
    ){
    return (uint16_t)p[0] | ((uint16_t)p[1] << 8U);
}
uint32_t
LOONAR_GL_ReadU32(
    const uint8_t *p
    ){
    uint32_t v = 0;
    unsigned s;
    for (s = 0; s < 32; s += 8)
        v |= (uint32_t)(*p++) << s;
    return v;
}
uint64_t
LOONAR_GL_ReadU64(
    const uint8_t *p
    ){
    uint64_t v = 0;
    unsigned s;
    for (s = 0; s < 64; s += 8)
        v |= (uint64_t)(*p++) << s;
    return v;
}
double
LOONAR_GL_ReadDouble(
    const uint8_t *p
    ){
    uint64_t bits = LOONAR_GL_ReadU64(p);
    double v;
    memcpy(&v, &bits, sizeof(v));
    return v;
}
void
LOONAR_GL_WriteU16(
    uint8_t *p, uint16_t v
    ){
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8U);
}
void
LOONAR_GL_WriteU32(
    uint8_t *p, uint32_t v
    ){
    unsigned s;
    for (s = 0; s < 32; s += 8)
        *p++ = (uint8_t)(v >> s);
}
void
LOONAR_GL_WriteU64(
    uint8_t *p, uint64_t v
    ){
    unsigned s;
    for (s = 0; s < 64; s += 8)
        *p++ = (uint8_t)(v >> s);
}
void
LOONAR_GL_WriteDouble(
    uint8_t *p, double v
    ){
    uint64_t bits;
    memcpy(&bits, &v, sizeof(bits));
    LOONAR_GL_WriteU64(p, bits);
}

int
LOONAR_GL_DecodeOne(
    const uint8_t *data, size_t size, LOONAR_GL_FrameView_t *frame, size_t *consumed
    ){
    uint32_t length;
    if (data == NULL||frame == NULL||consumed == NULL)
        return -1;
    *consumed = 0;
    if (size < LOONAR_GL_HEADER_SIZE)
        return 0;
    length = LOONAR_GL_ReadU32(data + 12);
    if (LOONAR_GL_ReadU32(data) != LOONAR_GL_MAGIC||LOONAR_GL_ReadU16(data + 4) != LOONAR_GL_VERSION||length > LOONAR_GL_MAX_PAYLOAD)
        return -1;
    if (size < LOONAR_GL_HEADER_SIZE + (size_t)length)
        return 0;
    frame->Type = LOONAR_GL_ReadU16(data + 6);
    frame->Sequence = LOONAR_GL_ReadU32(data + 8);
    frame->Payload = data + LOONAR_GL_HEADER_SIZE;
    frame->PayloadLength = length;
    *consumed = LOONAR_GL_HEADER_SIZE + (size_t)length;
    return 1;
}
size_t
LOONAR_GL_Encode(
    uint8_t *out, size_t capacity, uint16_t type, uint32_t sequence, const uint8_t *payload, uint32_t length
    ){
    if (out == NULL||length > LOONAR_GL_MAX_PAYLOAD||capacity < LOONAR_GL_HEADER_SIZE + (size_t)length||(length > 0&&payload == NULL))
        return 0;
    LOONAR_GL_WriteU32(out, LOONAR_GL_MAGIC);
    LOONAR_GL_WriteU16(out + 4, LOONAR_GL_VERSION);
    LOONAR_GL_WriteU16(out + 6, type);
    LOONAR_GL_WriteU32(out + 8, sequence);
    LOONAR_GL_WriteU32(out + 12, length);
    if (length > 0)
        memcpy(out + LOONAR_GL_HEADER_SIZE, payload, length);
    return LOONAR_GL_HEADER_SIZE + (size_t)length;
}
