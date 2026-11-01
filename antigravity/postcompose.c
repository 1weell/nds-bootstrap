/* GPL-3.0, as the parent project. Research, deliberately not in release builds. */
#include "postcompose.h"
#include <string.h>

static int overlaps(const void *a, size_t an, const void *b, size_t bn) {
    uintptr_t x = (uintptr_t)a, z = (uintptr_t)b;
    return x <= z ? z - x < an : x - z < bn;
}

int ra_postcompose(const uint8_t *source, size_t source_size,
                   uint8_t *output, size_t output_size,
                   unsigned width, unsigned height, enum raFrameLayout layout,
                   const uint32_t *strip, unsigned y, int active) {
    size_t bytes;
    unsigned row, col;
    if (!source || !output || width < 256 || width > 400 ||
        height < 16 || height > 240 ||
        (layout != RA_ROWS_RGB && layout != RA_CTR_BGR)) return -1;
    bytes = (size_t)width * height * 3;
    if (source_size < bytes || output_size < bytes ||
        overlaps(source, bytes, output, bytes) ||
        (active && (!strip || y > height - 16 ||
                    (uintptr_t)strip % sizeof(uint32_t) ||
                    overlaps(strip, 2048, output, bytes)))) return -1;
    memcpy(output, source, bytes);
    if (!active) return 0;
    for (row = 0; row < 16; ++row) {
        for (col = 0; col < 256; ++col) {
            unsigned word = ((row / 8) * 32 + col / 8) * 8 + row % 8;
            unsigned ink = (strip[word] >> ((col % 8) * 4)) & 15;
            size_t offset;
            uint8_t colour;
            /* Fixed dark backdrop remains readable over white game content.
             * RA_TEXT_INK=1, RA_TEXT_SHADOW=2. No game palette is consulted. */
            colour = ink == 1 ? 255 : ink == 2 ? 0 : 24;
            if (layout == RA_ROWS_RGB)
                offset = ((size_t)(row + y) * width + (width - 256) / 2 + col) * 3;
            else
                offset = ((size_t)((width - 256) / 2 + col) * height +
                          height - 1 - (row + y)) * 3;
            output[offset] = output[offset + 1] = output[offset + 2] = colour;
        }
    }
    return 0;
}
