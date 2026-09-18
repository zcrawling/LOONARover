#include "loonar_ground_wire.h"
#include <assert.h>
#include <string.h>

int main(void)
{
    uint8_t bytes[LOONAR_GL_MAX_FRAME];
    const uint8_t payload[] = {1, 2, 3};
    LOONAR_GL_FrameView_t frame;
    size_t consumed = 0;
    size_t size = LOONAR_GL_Encode(bytes, sizeof(bytes), 4, 99, payload, sizeof(payload));
    assert(size == LOONAR_GL_HEADER_SIZE + sizeof(payload));
    assert(LOONAR_GL_DecodeOne(bytes, 5, &frame, &consumed) == 0);
    assert(LOONAR_GL_DecodeOne(bytes, size, &frame, &consumed) == 1);
    assert(frame.Type == 4 && frame.Sequence == 99 && frame.PayloadLength == sizeof(payload));
    assert(memcmp(frame.Payload, payload, sizeof(payload)) == 0 && consumed == size);
    bytes[0] = 0;
    assert(LOONAR_GL_DecodeOne(bytes, size, &frame, &consumed) == -1);
    return 0;
}
