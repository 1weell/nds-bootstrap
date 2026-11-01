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
                   const uint32_t *strip, unsigned y, int active,
                   unsigned source_stride, unsigned output_stride) {
    size_t source_bytes = (size_t)source_stride * height;
    size_t output_bytes;
    unsigned row, col;
    if (!source || !output || width < 256 || width > 400 ||
        height < 16 || height > 240 ||
        (layout != RA_ROWS_RGB && layout != RA_CTR_BGR)) return -1;
    if (layout == RA_ROWS_RGB) {
        output_bytes = (size_t)output_stride * height;
    } else {
        /* RA_CTR_BGR: column-major, output_stride is column stride = height * 3 */
        output_bytes = (size_t)output_stride * width;
    }
    if (source_size < source_bytes || output_size < output_bytes ||
        overlaps(source, source_bytes, output, output_bytes) ||
        (active && (!strip || y > height - 16 ||
                    (uintptr_t)strip % sizeof(uint32_t) ||
                    overlaps(strip, 2048, output, output_bytes)))) return -1;
    /* Copy source (row-major) to output (layout-dependent). */
    if (layout == RA_ROWS_RGB) {
        for (row = 0; row < height; ++row) {
            memcpy(output + row * output_stride,
                   source + row * source_stride,
                   width * 3);
        }
    } else {
        /* RA_CTR_BGR: output is column-major. Transpose: source row -> output column. */
        for (row = 0; row < height; ++row) {
            for (col = 0; col < width; ++col) {
                size_t src_off = row * source_stride + col * 3;
                size_t dst_off = col * output_stride + (height - 1 - row) * 3;
                output[dst_off] = source[src_off];
                output[dst_off + 1] = source[src_off + 1];
                output[dst_off + 2] = source[src_off + 2];
            }
        }
    }
    if (!active) return 0;
    for (row = 0; row < 16; ++row) {
        for (col = 0; col < 256; ++col) {
            unsigned word = ((row / 8) * 32 + col / 8) * 8 + row % 8;
            unsigned ink = (strip[word] >> ((col % 8) * 4)) & 15;
            size_t offset;
            uint8_t colour;
            colour = ink == 1 ? 255 : ink == 2 ? 0 : 24;
            if (layout == RA_ROWS_RGB)
                offset = (size_t)(row + y) * output_stride + ((width - 256) / 2 + col) * 3;
            else
                offset = (size_t)((width - 256) / 2 + col) * output_stride +
                          (height - 1 - (row + y)) * 3;
            output[offset] = output[offset + 1] = output[offset + 2] = colour;
        }
    }
    return 0;
}
