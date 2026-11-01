#!/usr/bin/env python3
"""Exercise production RA key waiting and compositor/evaluation ordering."""
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
menu = (root / 'retail/cardenginei/arm9_igm/source/inGameMenu.c').read_text()
start = menu.index('static u16 raWaitKeys(')
key_function = menu[start:menu.index('\n}', start) + 2]
runtime = (root / 'retail/cardenginei/arm9_ra/source/cardengine.c').read_text()
tick_function = runtime[runtime.index('void ra_wram_tick('):]

pre = r'''
#include <stdio.h>
#include <stdlib.h>
#include "ra.h"
#include "locations.h"
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"FAIL popup flow: %s\n",#x);exit(1); } } while(0)
#define KEY_A 1
#define KEY_B 2
#define KEY_DOWN 128
static u16 input, script[8];
static unsigned waits, scans;
#define KEYS input
static unsigned scanline(void) {
    if (++scans & 1) return 191;
    input=0; /* held entry key released on next simulated frame */
    return 192;
}
#define REG_VCOUNT scanline()
static void mySwiDelay(int n) { (void)n; }
static void waitKeys(u16 keys) {
    (void)keys;CHECK(waits<8);input=script[waits++];
}
static u32 stateMagic, frames;
static u8 mpuBits, watchCount;
static raWatch watches[RA_WATCH_MAX];
#define __bss_start fakeBssStart
#define __bss_end fakeBssEnd
static char fakeBssStart[1], fakeBssEnd[1];
static char order[16];static unsigned events;
static void event(char c) { CHECK(events<sizeof(order));order[events++]=c; }
static u8 ra_startup(char* a,char* b,char* c) { (void)a;(void)b;(void)c;return RA_STAGE_ALLOC; }
static u32 ra_heap_size(void) { return 4096; }
static u32 ra_heap_used(void) { return 0; }
static u32 ra_heap_break(void) { return 0; }
static u32 ra_heap_top(void) { return 0; }
static u32 ra_malloc_probe(void) { return 1; }
static u32 ra_sbrk_probe(void) { return 1; }
static void ra_install_defaults(raSnapshot* s) { (void)s;watchCount=1; }
static u8 ra_icache_claim(u32 address) { (void)address;return 1; }
static void ra_watch_eval(raWatch* w) { w->status=RA_WATCH_OK;event('W'); }
static u32 trigger, seenTrigger;
static void ra_rc_tick(raSnapshot* s) { event('R');s->rcTriggered=++trigger; }
static const void* ra_rc_text(void) { return NULL; }
static void ra_overlay_tick(u32 count,const void* text) { (void)text;seenTrigger=count;event('O'); }
static void ra_popup_publish(raSnapshot* s) { (void)s;event('P'); }
u32 raOverlayShows, raOverlayDenied, raOverlayEvicted, raOverlayDeniedNoLayer;
volatile u32 raGfxReady;
u32 raOverlayRedrawn, raOverlayDispcnt, raOverlayWindow;
u8 raOverlayState, raOverlaySpriteOam, raOverlaySpriteSlot, raOverlayVramCnt[9];
u16 raOverlaySavedInk, raOverlaySavedShadow, raOverlayBgCnt, raOverlayVramEverOn;
'''
main = r'''
int main(void) {
    /* Entering with A held must wait for release, ignore status-only wakes
     * and unrelated buttons, then return the actual new press. */
    input=KEY_A;script[0]=0;script[1]=KEY_DOWN;script[2]=KEY_A;
    CHECK(raWaitKeys(KEY_A|KEY_B)==KEY_A && waits==3 && scans>=2);
    input=KEY_DOWN;waits=scans=0;script[0]=0;script[1]=KEY_DOWN;
    CHECK(raWaitKeys(KEY_A|KEY_B|KEY_DOWN)==KEY_DOWN && waits==2 && scans>=2);
    input=0;waits=0;script[0]=0;script[1]=KEY_B;
    CHECK(raWaitKeys(KEY_B)==KEY_B && waits==2);
    raSnapshot snapshot={0};snapshot.rcTriggered=999;
    ra_wram_tick(&snapshot);
    CHECK(events==3 && order[0]=='W' && order[1]=='R' && order[2]=='P');
    CHECK(snapshot.rcTriggered==1); /* first evaluation initializes it */
    events=0;ra_wram_tick(&snapshot);
    CHECK(events==4 && order[0]=='O' && order[1]=='W' && order[2]=='R' && order[3]=='P');
    CHECK(seenTrigger==1 && snapshot.rcTriggered==2);
    events=0;ra_wram_tick(&snapshot);CHECK(order[0]=='O' && seenTrigger==2);
    puts("PASSED production popup flow: fresh keys, status wakes, graphics before evaluation");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='ra-popup-flow-') as directory:
    out = Path(directory)
    (out / 'nds').mkdir()
    (out / 'nds/ndstypes.h').write_text(
        '#include <stdint.h>\n#include <stdbool.h>\n'
        'typedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;'
        'typedef int8_t s8;typedef int16_t s16;typedef int32_t s32;'
        'typedef volatile uint8_t vu8;typedef volatile uint16_t vu16;typedef volatile uint32_t vu32;')
    source = out / 'test.c'
    source.write_text(pre + key_function + '\n' + tick_function + main)
    subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu99', '-O1',
                    '-Wno-pointer-to-int-cast', '-Wno-int-to-pointer-cast',
                    '-I' + str(out), '-I' + str(root / 'retail/common/include'),
                    str(source), '-o', str(out / 'test')], check=True)
    subprocess.run([str(out / 'test')], check=True)
