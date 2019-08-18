#include "bitfield.h"

uint64_t bt_bitfield_read_le_wrapper(const uint8_t *ptr, int start, int length)
{
    uint64_t val;

    bt_bitfield_read_le(ptr, uint8_t, start, length, &val);

    return val;
}