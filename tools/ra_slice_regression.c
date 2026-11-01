/* Host reproduction of frame slicing with a Tetris DS definition (GameID 9878).
 * This preserves the OLD slice loop as a failure demonstration. The current
 * production evaluator is exercised directly by ra_reader_test.c. No timing measurement. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "rc_runtime.h"
#include "rcheevos/rc_internal.h"

static uint32_t lines;
static int upstream_awards;
static uint32_t peek(uint32_t address, uint32_t size, void *unused) {
    (void)size; (void)unused;
    if (address == 0x076a2c) return 2;
    if (address == 0x17dd38) return lines;
    return 0;
}
static void event(const rc_runtime_event_t *e) {
    if (e->type == RC_RUNTIME_EVENT_ACHIEVEMENT_TRIGGERED && e->id == 230047) upstream_awards++;
}
static int sliced_frame(rc_runtime_t *r, unsigned slice, unsigned parts) {
    int awards = 0;
    int32_t i;
    rc_update_memref_values(r->memrefs, peek, NULL);
    for (i = (int32_t)r->trigger_count - 1; i >= 0; --i) {
        rc_trigger_t *t = r->triggers[i].trigger;
        int old, state;
        if (!t || r->triggers[i].invalid_memref || (unsigned)i % parts != slice) continue;
        old = t->state;
        state = rc_evaluate_trigger(t, peek, NULL, NULL);
        if (state == RC_TRIGGER_STATE_RESET) state = t->state;
        if (state != old && state == RC_TRIGGER_STATE_TRIGGERED && r->triggers[i].id == 230047) awards++;
    }
    return awards;
}
int main(void) {
    /* First three staged Tetris definitions; the target is at index 2. */
    const char *definitions[] = {
        "0xH076a2c=2_0xH07b3b0=0_0xH07b3b1=0_0xH07b3b2=0_B:d0xX17dd38_0xX17dd38=2",
        "0xH076a2c=2_0xH07b3b0=0_0xH07b3b1=0_0xH07b3b2=0_B:d0xX17dd38_0xX17dd38=3",
        "0xH076a2c=2_0xH07b3b0=0_0xH07b3b1=0_0xH07b3b2=0_B:d0xX17dd38_0xX17dd38=4"
    };
    rc_runtime_t whole, sliced;
    int sliced_awards = 0, frame, i;
    rc_runtime_init(&whole);
    rc_runtime_init(&sliced);
    for (i = 0; i < 3; i++) {
        if (rc_runtime_activate_achievement(&whole, 230045 + i, definitions[i], NULL, 0) != 0 ||
            rc_runtime_activate_achievement(&sliced, 230045 + i, definitions[i], NULL, 0) != 0) return 2;
    }
    /* Index two runs on slice 2. Frame 5 changes the value for one frame only. */
    for (frame = 0; frame < 12; frame++) {
        lines = frame == 5 ? 4 : 0;
        rc_runtime_do_frame(&whole, event, peek, NULL, NULL);
        sliced_awards += sliced_frame(&sliced, frame % 4, 4);
    }
    printf("Tetris 230047, artificial one-frame change: whole=%d sliced=%d\n", upstream_awards, sliced_awards);
    rc_runtime_destroy(&whole);
    rc_runtime_destroy(&sliced);
    return !(upstream_awards == 1 && sliced_awards == 0);
}
