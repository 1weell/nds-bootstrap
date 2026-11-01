/* Research only. No TwlBg hook, shared-memory mapping or hardware access. */
#ifndef RA_POSTCOMPOSE_H
#define RA_POSTCOMPOSE_H
#include <stddef.h>
#include <stdint.h>

enum raFrameLayout { RA_ROWS_RGB = 0, RA_CTR_BGR = 1 };

/* Copy a complete, stable frame into a disjoint, privately owned output.
 * The caller must keep DMA away from BOTH buffers until this returns, then
 * publish output only when the display can accept it. This API cannot establish
 * that ownership or synchronization on hardware.
 * strip is the existing 256x16, tiled 4bpp ra_text_render output (2048 bytes).
 * No implicit physical/virtual address conversion and no VRAM borrowing.
 * source_stride/output_stride: bytes per row (allows pitch > width*3, e.g. 512*3=1536).
 * Returns -1 before writing anything for unsupported/overlapping arguments.
 */
int ra_postcompose(const uint8_t *source, size_t source_size,
                   uint8_t *output, size_t output_size,
                   unsigned width, unsigned height, enum raFrameLayout layout,
                   const uint32_t *strip, unsigned y, int active,
                   unsigned source_stride, unsigned output_stride);
#endif
