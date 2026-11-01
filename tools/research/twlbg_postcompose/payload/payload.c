/* GPL-3.0. Exact-image ARM11 candidate: synthetic popup, no RA transport yet. */
#include <stddef.h>
#include <stdint.h>
#include "postcompose.h"
#include "ra_text.h"

#define FRAME_BYTES (320u * 240u * 3u)
#define VRAM_BEGIN 0x1f000000u
#define VRAM_END 0x1f4fd800u
#define VRAM_MAPPED_END 0x1f600000u

typedef uint32_t (*Present)(uint32_t, uint32_t, uint32_t, uint32_t,
                            uint32_t, uint32_t, uint32_t);
typedef uint32_t (*Allocate)(uint32_t, uint32_t, uint32_t, uint32_t);
typedef int32_t (*StoreCache)(uint32_t, uint32_t);
extern int32_t ra_invalidate(uint32_t address, uint32_t size);

struct Diagnostics {
    uint32_t magic, version, calls, eligible, copied, shown, skipped, error;
    uint32_t buffers[3], last_source, last_output, last_format, last_stride;
    uint32_t observed_a, observed_b, allocations, allocation_failed;
};
volatile struct Diagnostics ra_diagnostics;
static uint32_t surface_reason;

#ifdef RA_DIAGNOSTIC
static uint32_t diagnostic_frames, diagnostic_owned, diagnostic_saved, diagnostic_color, diagnostic_status;
static uint32_t diagnostic_calls, diagnostic_idle_frames;

/* A temporary, bounded hardware diagnostic. Only the LCD blank-color register
   is touched; no unknown framebuffer is read. Preserve firmware blanking and
   restore our previous value only while our own last write still owns it. */
uint32_t ra_signal_frame(uint32_t handle) {
    volatile uint32_t *blank = (volatile uint32_t *)(uintptr_t)0x1ed02a04;
    uint32_t frame = diagnostic_frames, color = 0;
    diagnostic_frames = frame >= 1199 ? 0 : frame + 1;
    volatile struct Diagnostics *d = &ra_diagnostics;
    if (diagnostic_calls != d->calls) {
        diagnostic_calls = d->calls;
        diagnostic_idle_frames = 0;
    } else if (diagnostic_idle_frames < 1000) {
        diagnostic_idle_frames++;
    }
    if (diagnostic_owned && *blank != diagnostic_color) diagnostic_owned = 0;
    if (frame >= 60 && frame < 120) color = 0x01ff0000; /* blue: callback alive */
    if (frame >= 180 && frame < 300) {
        if (!d->last_source) color = 0x01ffffff; /* white: no bottom present */
        else if (d->shown && !d->error) color = diagnostic_idle_frames >= 120 ?
                    0x01ffffff : 0x0100ff00; /* white: no recent presentation; green: recent */
        else if (d->error == 8) color = 0x01ffff00; /* cyan: busy GPU queue */
        else if (d->error == 1) {
            /* Distinguish surface gates using saturated colors. */
            color = surface_reason == 1 ? 0x010000ff : /* red: stride */
                    surface_reason == 2 ? ((d->last_format & 7) == 2 ? 0x010000ff :
                                           (d->last_format & 7) == 0 ? 0x01ffffff :
                                           (d->last_format & 7) == 3 ? 0x0100ffff :
                                           (d->last_format & 7) == 4 ? 0x01ff00ff :
                                           0x010080ff) : /* format detail */
                    surface_reason == 3 ? 0x01ffff00 : /* cyan: source address */
                    surface_reason == 4 ? 0x0100ffff : /* yellow: object address */
                    surface_reason == 5 ? 0x01ff00ff : /* magenta: object fields */
                    surface_reason == 6 ? 0x01ffffff : /* white: object bounds */
                    0x010080ff;
        } else if (d->error == 9) color = 0x010080ff;
        else if (d->error >= 5) color = 0x01ff00ff; /* magenta: cache/composer */
        else if (d->error >= 2) color = 0x010000ff; /* red: allocation */
        else color = 0x0100ffff; /* yellow: no active episode reached */
        if (frame == 180 || !diagnostic_status) diagnostic_status = color;
        color = diagnostic_status;
    } else {
        diagnostic_status = 0;
    }
    if (color) {
        if (!diagnostic_owned && !(*blank & 0x01000000)) {
            diagnostic_saved = *blank;
            diagnostic_owned = 1;
        }
        if (diagnostic_owned) {
            *blank = color;
            diagnostic_color = color;
        }
    } else if (diagnostic_owned) {
        if (*blank == diagnostic_color) *blank = diagnostic_saved;
        diagnostic_owned = 0;
    }
    typedef uint32_t (*Signal)(uint32_t);
    return ((Signal)(uintptr_t)0x1182e4)(handle);
}
#endif

/* No libc or dynamic linker is needed by this module. */
void *memcpy(void *destination, const void *source, size_t size) {
    uint8_t *d = destination;
    const uint8_t *s = source;
    if (!(((uintptr_t)d | (uintptr_t)s) & 3)) {
        while (size >= 4) {
            *(uint32_t *)d = *(const uint32_t *)s;
            d += 4;
            s += 4;
            size -= 4;
        }
    }
    while (size--) *d++ = *s++;
    return destination;
}

static uint32_t read32(uint32_t address) {
    return *(volatile uint32_t *)(uintptr_t)address;
}

static int vram_span(uint32_t address, uint32_t length) {
    return address >= VRAM_BEGIN && address <= VRAM_END &&
           length <= VRAM_END - address;
}

/* Readable GPU surfaces can occupy the reserved tail outside the allocator. */
static int vram_readable_span(uint32_t address, uint32_t length) {
    return address >= VRAM_BEGIN && address <= VRAM_MAPPED_END &&
           length <= VRAM_MAPPED_END - address;
}

static int object_span(uint32_t address) {
    return (address >= 0x00100000u && address <= 0x00154000u - 24u) ||
           vram_readable_span(address, 24);
}

static int overlaps(uint32_t a, uint32_t b, uint32_t size) {
    return a <= b ? b - a < size : a - b < size;
}

static int source_valid(uint32_t address, uint32_t stride, uint32_t format) {
    uint32_t object = read32(0x0012cb68u);
    surface_reason = 0;
    /* Accept both linear stride (720) and Morton pitch 512 (1536 bytes).
     * Hardware LGY config uses pitch 512 for 320x240 mode.
     * Format bit 12 (0x1000) indicates Morton swizzle.
     */
    if (stride != 720 && stride != 1536) { surface_reason = 1; return 0; }
    if ((format & 7) != 1) { surface_reason = 2; return 0; }
    if ((address & 31) || !vram_readable_span(address, FRAME_BYTES)) { surface_reason = 3; return 0; }
    if (!object_span(object)) { surface_reason = 4; return 0; }
    uint32_t base = read32(object + 4), width = read32(object + 12);
    uint32_t height = read32(object + 16);
    /* Accept width 240 (rotated) or 320 (native), height 320+ */
    if (read32(object + 8) != 0x8051 || (width != 240 && width != 320) || height < 320 || height > 1024)
        { surface_reason = 5; return 0; }
    uint32_t bytes = width * height * 3;
    if (!vram_readable_span(base, bytes) || address < base || address - base > bytes - FRAME_BYTES) {
        surface_reason = 6; return 0;
    }
    return 1;
}

static uint32_t physical(uint32_t address) {
    return address - 0x07000000u;
}

uint32_t ra_present(uint32_t screen, uint32_t index, uint32_t left,
                    uint32_t right, uint32_t stride, uint32_t format,
                    uint32_t select) {
    Present original = (Present)(uintptr_t)0x001088c1;
    volatile struct Diagnostics *d = &ra_diagnostics;
    if (!d->magic) { d->magic = 0x31574c54; d->version = 1; }
    d->calls++;
    if (screen != 1) return original(screen, index, left, right, stride, format, select);
    d->last_source = left;
    d->last_format = format;
    d->last_stride = stride;
    /* The only patched caller follows the original GPU queue wait. Retain a
       runtime idle guard, and refuse unsupported surfaces before reading. */
    uint32_t reject = *(volatile uint8_t *)(uintptr_t)0x0012ca51 ? 8 :
                      (right && right != left) ? 9 :
                      !source_valid(left, stride, format) ? 1 : 0;
    if (reject) {
        d->skipped++;
        d->error = reject;
        return original(screen, index, left, right, stride, format, select);
    }
    uint32_t frame = d->eligible++;
    if (frame >= 1199) d->eligible = 0;
    d->error = 0;
    /* Repeat the two episodes every 1200 eligible frames: TWiLight Menu and
       the launched game share one TwlBg lifetime. This is never a RA event. */
    int active = (frame >= 60 && frame < 240) || (frame >= 600 && frame < 780);
    if (!active) return original(screen, index, left, right, stride, format, select);
    /* Allocator ID tag must be idle: avoid replacing Nintendo texture IDs. */
    if (read32(0x001279f8) != 0 || d->allocation_failed) {
        d->error = 2;
        return original(screen, index, left, right, stride, format, select);
    }
    Allocate allocate = (Allocate)(uintptr_t)0x001055bd;
    for (unsigned i = 0; i < 3; ++i) {
        if (!d->buffers[i]) {
            uint32_t p = allocate(0x20000, 0x101, 0, FRAME_BYTES);
            if (!vram_span(p, FRAME_BYTES) || (p & 31)) {
                d->allocation_failed = 1;
                d->error = 3;
                return original(screen, index, left, right, stride, format, select);
            }
            d->buffers[i] = p;
            d->allocations++;
        }
    }
    uint32_t a = read32(0x1ef00568), b = read32(0x1ef0056c), output = 0;
    d->observed_a = a;
    d->observed_b = b;
    for (unsigned i = 0; i < 3; ++i) {
        uint32_t p = d->buffers[i], pa = physical(p);
        /* Exclude BOTH LCD address slots, including a pending selection. */
        if (!overlaps(pa, a, FRAME_BYTES) && !overlaps(pa, b, FRAME_BYTES) &&
            !overlaps(p, left, FRAME_BYTES)) { output = p; break; }
    }
    if (!output) {
        d->skipped++;
        d->error = 4;
        return original(screen, index, left, right, stride, format, select);
    }
    if (ra_invalidate(left, FRAME_BYTES) < 0) {
        d->error = 5;
        return original(screen, index, left, right, stride, format, select);
    }
    const uint32_t *strip = ra_text_render("RA TWL TEST", "ARM11 - POPUP SINTETICO");
    /* Source stride from hardware; output stride = height*3 = 720 for RA_CTR_BGR column-major. */
    if (ra_postcompose((const uint8_t *)(uintptr_t)left, FRAME_BYTES,
                       (uint8_t *)(uintptr_t)output, FRAME_BYTES,
                       320, 240, RA_CTR_BGR, strip, 208, 1,
                       stride, 720u) != 0) {
        d->error = 6;
        return original(screen, index, left, right, stride, format, select);
    }
#ifdef RA_VISUAL_OUTPUT
    /* Temporary visibility probe: show solid magenta through our owned output,
       never through the LCD blanking register or a game-owned buffer. */
    uint8_t *probe = (uint8_t *)(uintptr_t)output;
    for (uint32_t i = 0; i < FRAME_BYTES; i += 3) {
        probe[i] = 255; probe[i + 1] = 0; probe[i + 2] = 255;
    }
#endif
    StoreCache store = (StoreCache)(uintptr_t)0x001043bd;
    if (store(output, FRAME_BYTES) < 0) {
        d->error = 7;
        return original(screen, index, left, right, stride, format, select);
    }
    d->copied++;
    d->shown++;
    d->last_output = output;
    d->error = 0;
    return original(screen, index, output, right ? output : 0, stride, format, select);
}
